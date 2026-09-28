"""
ToolExecutor adapter - dispatches tool calls.

Built-in tools run natively; self-generated tools are called over HTTP
at their deployed endpoint. If a tool has no endpoint, it runs in the sandbox.
"""

from __future__ import annotations

from typing import Any, Dict

from nexus.domain.exceptions import ToolNotFoundError
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry


def _normalize_params(tool_id: str, raw_params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(raw_params or {})

    if tool_id == "git_info":
        if "repo_path" not in params:
            params["repo_path"] = params.pop("path", ".")

    elif tool_id == "list_directory":
        if "path" not in params:
            params["path"] = params.pop("dir", ".")

    elif tool_id == "read_file":
        if "path" not in params and "filename" in params:
            params["path"] = params.pop("filename")

    elif tool_id == "diff_text":
        if "old_text" not in params and "original" in params:
            params["old_text"] = params.pop("original")
        if "new_text" not in params and "modified" in params:
            params["new_text"] = params.pop("modified")
        params.pop("original", None)
        params.pop("modified", None)

    elif tool_id == "json_query":
        if "json_str" not in params:
            val = params.pop("data", None) or params.pop("json", None) or "{}"
            params["json_str"] = val if isinstance(val, str) else str(val)
        if "key_path" not in params:
            params["key_path"] = str(params.pop("query", None) or params.pop("path", None) or params.pop("key", None) or "")
        params.pop("data", None)
        params.pop("query", None)
        params.pop("json", None)
        params.pop("path", None)

    elif tool_id == "json_transform":
        if "json_str" not in params:
            val = params.pop("data", None) or params.pop("json", None) or "{}"
            params["json_str"] = val if isinstance(val, str) else str(val)
        if "expression" not in params:
            params["expression"] = str(params.pop("query", None) or params.pop("expr", None) or params.pop("operations", None) or "keys(@)")
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

    def __init__(self, registry: ToolRegistry, sandbox: Sandbox, builtins: Dict[str, Any]) -> None:
        self._registry = registry
        self._sandbox = sandbox
        self._builtins = builtins

    async def execute(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = await self._registry.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)

        params = _normalize_params(tool_id, params)

        errors = tool.input_schema.validate(params)
        if errors:
            return {"error": "; ".join(errors)}

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
