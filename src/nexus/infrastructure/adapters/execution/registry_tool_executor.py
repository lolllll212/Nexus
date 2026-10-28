"""
ToolExecutor adapter - dispatches tool calls.

Built-in tools run natively; self-generated tools are called over HTTP
at their deployed endpoint. If a tool has no endpoint, it runs in the sandbox.
"""

from __future__ import annotations

import json
from typing import Any

from nexus.domain.exceptions import ToolNotFoundError
from nexus.domain.ports.autonomy import AutonomyPolicy
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry

_APPROVAL_GATED_TOOLS = (
    "run_shell",
    "write_file",
    "edit_file",
    "delete_file",
    "create_directory",
    "create_repository",
    "write_files",
    "batch_edit_files",
    "move_path",
    "copy_path",
    "delete_directory",
)

# The chat workspace historically granted one-file tools. Treat those grants as
# equivalent to the newer batch/folder operations so existing approvals remain
# useful; the concrete handlers repeat this check per affected path.
_APPROVAL_ALIASES: dict[str, tuple[str, ...]] = {
    "write_files": ("write_file",),
    "batch_edit_files": ("edit_file",),
    "move_path": ("write_file", "edit_file"),
    "copy_path": ("write_file",),
    "delete_directory": ("delete_file",),
}

_DRY_RUN_APPROVAL_EXEMPT = {"write_files", "batch_edit_files"}


def _as_json_string(value: Any) -> str:
    """Encode structured tool input as JSON, never as a Python repr."""

    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _normalize_params(tool_id: str, raw_params: dict[str, Any]) -> dict[str, Any]:
    params = dict(raw_params or {})

    def use_alias(canonical: str, aliases: tuple[str, ...], default: Any = None) -> None:
        if canonical not in params or params.get(canonical) in (None, ""):
            for alias in aliases:
                if alias in params and params[alias] not in (None, ""):
                    params[canonical] = params.pop(alias)
                    break
            else:
                if default is not None and canonical not in params:
                    params[canonical] = default
        for alias in aliases:
            params.pop(alias, None)

    if tool_id in ("project_scan", "find_files", "directory_tree", "code_diagnostics", "project_checks"):
        use_alias("path", ("dir", "root", "directory", "project_path"), ".")

    if tool_id == "find_files":
        use_alias("pattern", ("glob", "query", "name_pattern"), "*")
        if "extensions" not in params and "extension" in params:
            extension = params.pop("extension")
            params["extensions"] = extension if isinstance(extension, list) else [extension]

    elif tool_id == "directory_tree":
        use_alias("max_depth", ("depth",))
        use_alias("max_entries", ("limit",))

    elif tool_id == "read_files":
        if "paths" not in params:
            value = params.pop("files", None) or params.pop("file", None) or params.pop("path", None)
            if value is not None:
                params["paths"] = value if isinstance(value, list) else [value]
        elif isinstance(params.get("paths"), str):
            params["paths"] = [params["paths"]]
        params.pop("files", None)
        params.pop("file", None)
        params.pop("path", None)

    elif tool_id == "file_outline":
        use_alias("path", ("filename", "file"))

    elif tool_id == "find_symbol":
        use_alias("symbol", ("name", "query"))
        use_alias("path", ("dir", "root", "directory"), ".")
        if "extensions" not in params and "extension" in params:
            extension = params.pop("extension")
            params["extensions"] = extension if isinstance(extension, list) else [extension]

    elif tool_id == "git_diff":
        use_alias("repo_path", ("repo", "root", "directory"), ".")
        use_alias("path", ("pathspec", "file"))

    elif tool_id == "project_checks":
        use_alias("target", ("test_target", "test_path"))

    elif tool_id == "write_files":
        if "files" not in params and "path" in params and "content" in params:
            params["files"] = [{"path": params.pop("path"), "content": params.pop("content")}]
        files = params.get("files")
        if isinstance(files, list):
            normalized_files: list[Any] = []
            for item in files:
                if isinstance(item, dict):
                    item = dict(item)
                    if "path" not in item:
                        item["path"] = item.pop("filename", None) or item.pop("file", None)
                    item.pop("filename", None)
                    item.pop("file", None)
                normalized_files.append(item)
            params["files"] = normalized_files

    elif tool_id == "batch_edit_files":
        if "edits" not in params:
            params["edits"] = (
                params.pop("changes", None)
                or params.pop("replacements", None)
                or params.pop("files", None)
                or []
            )
        edits = params.get("edits")
        if isinstance(edits, list):
            normalized_edits: list[Any] = []
            for item in edits:
                if isinstance(item, dict):
                    item = dict(item)
                    if "path" not in item:
                        item["path"] = item.pop("filename", None) or item.pop("file", None)
                    if "old_text" not in item:
                        item["old_text"] = item.pop("old", None) or item.pop("search", None)
                    if "new_text" not in item:
                        item["new_text"] = item.pop("new", None) or item.pop("replacement", None)
                    for alias in ("filename", "file", "old", "search", "new", "replacement"):
                        item.pop(alias, None)
                normalized_edits.append(item)
            params["edits"] = normalized_edits
        params.pop("changes", None)
        params.pop("replacements", None)
        params.pop("files", None)

    elif tool_id in ("move_path", "copy_path"):
        use_alias("source", ("from", "source_path", "src", "path"))
        use_alias("destination", ("to", "target", "dest", "destination_path", "new_path"))

    elif tool_id == "delete_directory":
        use_alias("path", ("dir", "directory", "folder"))
        # Do not infer recursive=true: deleting a non-empty folder must be
        # stated explicitly by the caller in addition to confirm=true.

    if tool_id == "git_info":
        if "repo_path" not in params:
            params["repo_path"] = params.pop("path", ".")

    elif tool_id == "list_directory":
        if "path" not in params:
            params["path"] = params.pop("dir", ".")
        if "max_entries" not in params and "limit" in params:
            params["max_entries"] = params.pop("limit")
        params.pop("dir", None)

    elif tool_id == "read_file":
        if "path" not in params and "filename" in params:
            params["path"] = params.pop("filename")
        if "start_line" not in params and "from_line" in params:
            params["start_line"] = params.pop("from_line")
        if "start_line" not in params and "start" in params:
            params["start_line"] = params.pop("start")
        if "end_line" not in params and "to_line" in params:
            params["end_line"] = params.pop("to_line")
        if "end_line" not in params and "end" in params:
            params["end_line"] = params.pop("end")
        for alias in ("filename", "from_line", "start", "to_line", "end"):
            params.pop(alias, None)

    elif tool_id in ("write_file", "edit_file", "delete_file", "create_directory"):
        if "path" not in params and "filename" in params:
            params["path"] = params.pop("filename")
        if "path" not in params and "file" in params:
            params["path"] = params.pop("file")
        if tool_id == "edit_file":
            if "old_text" not in params and "old" in params:
                params["old_text"] = params.pop("old")
            if "old_text" not in params and "search" in params:
                params["old_text"] = params.pop("search")
            if "new_text" not in params and "new" in params:
                params["new_text"] = params.pop("new")
            if "new_text" not in params and "replacement" in params:
                params["new_text"] = params.pop("replacement")

    elif tool_id == "create_repository":
        if "name" not in params:
            params["name"] = (
                params.pop("repo_name", None)
                or params.pop("project_name", None)
                or params.pop("repository", None)
                or ""
            )
        if "path" not in params:
            path_value = params.pop("destination", None) or params.pop("target_path", None)
            if path_value:
                params["path"] = path_value
        if "template" not in params:
            template_value = params.pop("stack", None) or params.pop("framework", None)
            if template_value:
                params["template"] = template_value
        if "initialize_git" not in params and "git" in params:
            params["initialize_git"] = params.pop("git")
        if "initial_commit" not in params and "commit" in params:
            params["initial_commit"] = params.pop("commit")
        if "include_ci" not in params and "ci" in params:
            params["include_ci"] = params.pop("ci")
        if "github_remote" not in params and "remote" in params:
            params["github_remote"] = params.pop("remote")
        for alias in ("repo_name", "project_name", "repository", "destination", "target_path", "stack", "framework"):
            params.pop(alias, None)

    elif tool_id == "diff_text":
        if "old_text" not in params and "original" in params:
            params["old_text"] = params.pop("original")
        if "new_text" not in params and "modified" in params:
            params["new_text"] = params.pop("modified")
        params.pop("original", None)
        params.pop("modified", None)

    elif tool_id == "json_query":
        if "json_str" not in params:
            val = params.pop("data") if "data" in params else params.pop("json") if "json" in params else "{}"
            params["json_str"] = _as_json_string(val)
        elif not isinstance(params.get("json_str"), str):
            params["json_str"] = _as_json_string(params["json_str"])
        if "key_path" not in params:
            params["key_path"] = str(
                params.pop("query", None) or params.pop("path", None) or params.pop("key", None) or ""
            )
        params.pop("data", None)
        params.pop("query", None)
        params.pop("json", None)
        params.pop("path", None)

    elif tool_id == "json_transform":
        if "json_str" not in params:
            val = params.pop("data") if "data" in params else params.pop("json") if "json" in params else "{}"
            params["json_str"] = _as_json_string(val)
        elif not isinstance(params.get("json_str"), str):
            params["json_str"] = _as_json_string(params["json_str"])
        if "expression" not in params:
            params["expression"] = str(
                params.pop("query", None)
                or params.pop("expr", None)
                or params.pop("operations", None)
                or "keys(@)"
            )
        params.pop("data", None)
        params.pop("operations", None)
        params.pop("query", None)

    elif tool_id == "run_shell":
        if "command" not in params and "cmd" in params:
            params["command"] = params.pop("cmd")

    elif tool_id == "calculator":
        if "expression" not in params and "expr" in params:
            params["expression"] = params.pop("expr")

    elif tool_id == "web_search":
        if "query" not in params and "q" in params:
            params["query"] = params.pop("q")
        if "max_results" not in params and "limit" in params:
            params["max_results"] = params.pop("limit")
        params.pop("q", None)
        params.pop("limit", None)

    elif tool_id == "http_request":
        if "json_body" not in params and "json" in params:
            params["json_body"] = params.pop("json")
        if "timeout" not in params and "timeout_seconds" in params:
            params["timeout"] = params.pop("timeout_seconds")
        params.pop("json", None)
        params.pop("timeout_seconds", None)

    elif tool_id == "code_search_semantic":
        if "k" not in params and "top_k" in params:
            params["k"] = params.pop("top_k")
        if "k" not in params and "limit" in params:
            params["k"] = params.pop("limit")
        if "path" not in params and "directory" in params:
            params["path"] = params.pop("directory")
        for alias in ("top_k", "limit", "directory"):
            params.pop(alias, None)

    elif tool_id == "find_databases":
        if "path" not in params:
            params["path"] = params.pop("dir", ".")

    elif tool_id == "query_database":
        if "type" not in params:
            params["type"] = "sqlite"
        if "sql" not in params and "query" in params:
            params["sql"] = params.pop("query")
        params.pop("query", None)

    return params


class RegistryBackedToolExecutor(ToolExecutor):
    """Executes tools by looking them up in the registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: Sandbox,
        builtins: dict[str, Any],
        autonomy_policy: AutonomyPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._sandbox = sandbox
        self._builtins = builtins
        self._autonomy_policy = autonomy_policy

    async def execute(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = await self._registry.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)

        params = _normalize_params(tool_id, params)

        errors = tool.input_schema.validate(params)
        if errors:
            return {"error": "; ".join(errors)}

        # Human approval gate on destructive execution tools. Dry-run batch
        # previews are read-only and therefore do not need an approval grant.
        approval_needed = tool_id in _APPROVAL_GATED_TOOLS and not (
            tool_id in _DRY_RUN_APPROVAL_EXEMPT and params.get("dry_run") is True
        )
        if self._autonomy_policy and approval_needed:
            # Prefer authenticated execution context over model-supplied params;
            # schemas reject tenant/actor params for built-in tools anyway.
            from nexus.infrastructure.adapters.execution.extended_tools import get_execution_context

            ctx = get_execution_context()
            tenant_id = str(ctx.get("tenant_id") or params.get("tenant_id", "default"))
            action = f"tool:{tool_id}"
            actor = str(ctx.get("actor") or ctx.get("user_id") or params.get("actor", "user"))
            approved = False
            for candidate_tool in (tool_id, *_APPROVAL_ALIASES.get(tool_id, ())):
                candidate_action = f"tool:{candidate_tool}"
                approved = await self._autonomy_policy.require_approval(
                    candidate_action, actor=actor, tenant_id=tenant_id
                )
                if approved:
                    break
            if not approved:
                return {
                    "error": f"Execution of tool '{tool_id}' requires explicit approval. Action '{action}' not approved.",
                    "approval_required": True,
                    "action": action,
                }

        # Route python execution directly through the configured sandbox (eliminates raw host execution)
        if tool_id == "run_python":
            code = params.get("code", "")
            timeout = params.get("timeout", 30)
            return await self._sandbox.run_code(code, timeout=timeout)

        # Built-in or dynamically registered native handler
        if tool_id in self._builtins:
            return await self._builtins[tool_id](params)

        # Deployed endpoint
        if tool.endpoint:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{tool.endpoint}/execute", json=params) as resp:
                    return await resp.json()

        # Fallback: sandbox execution of its code
        return await self._sandbox.run(tool.code or "", inputs=params)
