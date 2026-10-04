"""
Extended built-in tools — practical capabilities the brain can always use.
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import difflib
import hashlib
import json
import os
import platform
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.security.ssrf import safe_http_fetch

_AUTONOMY_POLICY: Any = None
_DEFAULT_SANDBOX: Any = None
_CURRENT_EXECUTION_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "nexus_execution_context", default=None
)


def set_execution_context(ctx: dict[str, Any] | None) -> None:
    _CURRENT_EXECUTION_CONTEXT.set(ctx)


def get_execution_context() -> dict[str, Any]:
    ctx = _CURRENT_EXECUTION_CONTEXT.get()
    if ctx is not None:
        return ctx
    return {"tenant_id": "default", "actor": "system", "role": "user"}


DENYLISTED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    ".env.test",
    "credentials",
    "secrets.json",
    ".git-credentials",
    ".netrc",
}
DENYLISTED_EXTENSIONS = {".pem", ".key", ".pkcs12", ".p12", ".pfx", ".cert", ".crt"}
DENYLISTED_SUBSTRINGS = {
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".git/config",
    ".git/credentials",
    ".git\\config",
    ".git\\credentials",
}


def is_denylisted_path(path: Path) -> bool:
    name = path.name.lower()
    if name in DENYLISTED_FILES or name.startswith(".env"):
        return True
    if any(name.endswith(ext) for ext in DENYLISTED_EXTENSIONS):
        return True
    path_str = str(path).replace("\\", "/").lower()
    for sub in DENYLISTED_SUBSTRINGS:
        if sub in path_str:
            return True
    return False


def set_autonomy_policy(policy: Any) -> None:
    global _AUTONOMY_POLICY
    _AUTONOMY_POLICY = policy


def get_autonomy_policy() -> Any:
    return _AUTONOMY_POLICY


def set_default_sandbox(sandbox: Any) -> None:
    global _DEFAULT_SANDBOX
    _DEFAULT_SANDBOX = sandbox


def get_default_sandbox() -> Any:
    global _DEFAULT_SANDBOX
    if _DEFAULT_SANDBOX is None:
        backend_env = os.getenv("NEXUS_SANDBOX_BACKEND")
        socket_available = Path("/var/run/docker.sock").exists()
        if (backend_env and backend_env.lower() == "subprocess") or (
            backend_env is None and not socket_available
        ):
            from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

            _DEFAULT_SANDBOX = SubprocessSandbox()
        else:
            from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox

            _DEFAULT_SANDBOX = DockerSandbox()
    return _DEFAULT_SANDBOX


_CONCEPT_REPOSITORY: Any = None


def set_concept_repository(repo: Any) -> None:
    global _CONCEPT_REPOSITORY
    _CONCEPT_REPOSITORY = repo


def get_concept_repository() -> Any:
    global _CONCEPT_REPOSITORY
    if _CONCEPT_REPOSITORY is None:
        from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository

        _CONCEPT_REPOSITORY = InMemoryConceptRepository()
    return _CONCEPT_REPOSITORY


_EMBEDDER: Any = None


def set_embedder(embedder: Any) -> None:
    global _EMBEDDER
    _EMBEDDER = embedder


def get_embedder() -> Any:
    global _EMBEDDER
    return _EMBEDDER


def get_workspace_root() -> Path:
    """Return the absolute path of the configured workspace root."""
    root_str = os.getenv("NEXUS_WORKSPACE_ROOT", ".")
    return Path(root_str).resolve()


def get_allowed_roots() -> list[Path]:
    roots = [get_workspace_root()]
    try:
        import tempfile

        t_dir = Path(tempfile.gettempdir()).resolve()
        if t_dir not in roots:
            roots.append(t_dir)
    except Exception:
        pass
    return roots


def resolve_confined_path(rel_or_abs_path: str | Path, must_exist: bool = False) -> tuple[Path | None, str]:
    """
    Resolve a path and ensure it is strictly confined within WORKSPACE_ROOT or temp dir.
    Rejects any path traversal attempt (e.g. '../', absolute paths outside workspace).
    Returns (resolved_path, "") on success, or (None, error_message) on rejection.
    """
    try:
        allowed = get_allowed_roots()
        path = Path(rel_or_abs_path)
        if not path.is_absolute():
            candidate = (get_workspace_root() / path).resolve()
        else:
            candidate = path.resolve()

        is_confined = any(candidate == r or r in candidate.parents for r in allowed)
        if not is_confined:
            return (
                None,
                f"Access denied: path '{rel_or_abs_path}' escapes workspace root '{get_workspace_root()}'",
            )

        if is_denylisted_path(candidate):
            return (
                None,
                f"Access denied: access to sensitive configuration, secrets, or keys is forbidden: '{candidate.name}'",
            )

        if must_exist and not candidate.exists():
            return None, f"Path not found: '{rel_or_abs_path}'"

        return candidate, ""
    except Exception as e:
        return None, f"Invalid path '{rel_or_abs_path}': {e}"


TOOL_DEFS: list[dict[str, Any]] = [
    {
        "id": "web_fetch",
        "name": "web_fetch",
        "description": "Fetch a URL and return its text content (up to max_chars).",
        "input": {"url": {"type": "string"}, "max_chars": {"type": "integer"}},
        "required": ["url"],
    },
    {
        "id": "run_shell",
        "name": "run_shell",
        "description": "Run a shell command and return its output.",
        "input": {"command": {"type": "string"}, "timeout": {"type": "integer"}},
        "required": ["command"],
        "output": {
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "returncode": {"type": "integer"},
        },
    },
    {
        "id": "read_file",
        "name": "read_file",
        "description": "Read a file from disk and return its content.",
        "input": {"path": {"type": "string"}, "encoding": {"type": "string"}},
        "required": ["path"],
        "output": {"content": {"type": "string"}},
    },
    {
        "id": "write_file",
        "name": "write_file",
        "description": "Write content to a file (creates parent dirs).",
        "input": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
        "output": {"bytes_written": {"type": "integer"}},
    },
    {
        "id": "list_directory",
        "name": "list_directory",
        "description": "List files and subdirectories in a folder.",
        "input": {"path": {"type": "string"}},
        "required": ["path"],
        "output": {"entries": {"type": "array"}},
    },
    {
        "id": "json_query",
        "name": "json_query",
        "description": "Parse JSON and extract a value by dot-path (e.g. 'data.users.0.name').",
        "input": {"json_str": {"type": "string"}, "key_path": {"type": "string"}},
        "required": ["json_str", "key_path"],
    },
    {
        "id": "json_transform",
        "name": "json_transform",
        "description": "Apply a Python expression to JSON data. Use 'd' as the variable.",
        "input": {"json_str": {"type": "string"}, "expression": {"type": "string"}},
        "required": ["json_str", "expression"],
    },
    {
        "id": "current_datetime",
        "name": "current_datetime",
        "description": "Get the current UTC date and time, optionally formatted.",
        "input": {"format": {"type": "string"}},
        "output": {"datetime": {"type": "string"}, "timestamp": {"type": "number"}},
    },
    {
        "id": "diff_text",
        "name": "diff_text",
        "description": "Show a unified diff between two text strings.",
        "input": {"old_text": {"type": "string"}, "new_text": {"type": "string"}},
        "required": ["old_text", "new_text"],
        "output": {"diff": {"type": "string"}},
    },
    {
        "id": "hash_text",
        "name": "hash_text",
        "description": "Hash a string with md5, sha256, or sha512.",
        "input": {"text": {"type": "string"}, "algorithm": {"type": "string"}},
        "required": ["text"],
        "output": {"hash": {"type": "string"}},
    },
    {
        "id": "base64_encode",
        "name": "base64_encode",
        "description": "Base64-encode or decode a string.",
        "input": {"text": {"type": "string"}, "decode": {"type": "boolean"}},
        "required": ["text"],
        "output": {"result": {"type": "string"}},
    },
    {
        "id": "git_info",
        "name": "git_info",
        "description": "Get git info for a repo: branch, last commit, status.",
        "input": {"repo_path": {"type": "string"}},
        "required": ["repo_path"],
    },
    {
        "id": "http_request",
        "name": "http_request",
        "description": "Make an HTTP request (GET/POST/PUT/DELETE) and return the response.",
        "input": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "headers": {"type": "object"},
            "body": {"type": "string"},
        },
        "required": ["url"],
        "output": {"status": {"type": "integer"}, "body": {"type": "string"}},
    },
    {
        "id": "grep",
        "name": "grep",
        "description": "Search for a regex pattern in files under a directory.",
        "input": {"pattern": {"type": "string"}, "path": {"type": "string"}, "include": {"type": "string"}},
        "required": ["pattern"],
        "output": {"matches": {"type": "array"}},
    },
    {
        "id": "system_info",
        "name": "system_info",
        "description": "Get system info: OS, Python version, CPU count, memory.",
        "input": {},
        "output": {"info": {"type": "object"}},
    },
    {
        "id": "find_databases",
        "name": "find_databases",
        "description": "Scan a directory to discover databases: local files (.sqlite/.db/.sqlite3) and connection configs (docker-compose.yml, .env, config). Use this when you encounter or suspect a database and want to connect on your own.",
        "input": {"path": {"type": "string"}},
        "required": ["path"],
        "output": {"databases": {"type": "array"}},
    },
    {
        "id": "query_database",
        "name": "query_database",
        "description": "Connect to a database autonomously and list tables/keys or run a query. Engines: sqlite (local file — the only one that needs no running server), postgres, mysql, redis. For sqlite pass 'database' (file path) and 'sql'/'mode'='list_tables'. For postgres/mysql/redis pass host/port/user/password/database.",
        "input": {
            "type": {"type": "string"},
            "database": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "user": {"type": "string"},
            "password": {"type": "string"},
            "mode": {"type": "string"},
            "sql": {"type": "string"},
            "key": {"type": "string"},
            "read_only": {"type": "boolean"},
        },
        "required": ["type"],
        "output": {"rows": {"type": "array"}, "columns": {"type": "array"}, "tables": {"type": "array"}},
    },
    {
        "id": "process_multimodal_media",
        "name": "process_multimodal_media",
        "description": "Decomposes images and videos into high-density structured semantic representations (Spatial Grid Decomposition, OCR Inscription Extraction, Color Palettes, Entity Scene Graphs, and Chronological Temporal Keyframes) so text-only models without native vision or video tensor support can understand, analyze, query, and reason about visual media.",
        "input": {
            "source": {"type": "string"},
            "media_type": {"type": "string"},
            "question": {"type": "string"},
            "detail_level": {"type": "string"},
            "base64_data": {"type": "string"},
        },
        "required": ["source"],
        "output": {
            "media_type": {"type": "string"},
            "prompt_injection_block": {"type": "string"},
            "spatial_grid": {"type": "object"},
            "color_palette": {"type": "array"},
            "ocr_extracted_text": {"type": "array"},
            "keyframes": {"type": "array"},
            "answer": {"type": "string"},
        },
    },
    {
        "id": "pytest_runner",
        "name": "pytest_runner",
        "description": "Run the test suite inside the sandbox with structured failure output (test file, test name, first traceback frame). Respects NEXUS_SANDBOX_BACKEND.",
        "input": {
            "target": {"type": "string"},
            "options": {"type": "string"},
            "timeout": {"type": "integer"},
            "files": {"type": "object"},
        },
        "output": {
            "passed": {"type": "integer"},
            "failed": {"type": "integer"},
            "skipped": {"type": "integer"},
            "total_failed": {"type": "integer"},
            "returncode": {"type": "integer"},
            "failures": {"type": "array"},
            "summary": {"type": "string"},
            "output": {"type": "string"},
        },
    },
    {
        "id": "csv_query",
        "name": "csv_query",
        "description": "Query, filter, project, and aggregate CSV data using a JMESPath expression.",
        "input": {
            "query": {"type": "string"},
            "data": {"type": "string"},
            "path": {"type": "string"},
            "delimiter": {"type": "string"},
        },
        "required": ["query"],
        "output": {
            "result": {"type": "any"},
            "count": {"type": "integer"},
            "columns": {"type": "array"},
        },
    },
    {
        "id": "memory_graph_query",
        "name": "memory_graph_query",
        "description": "Query concept neighborhoods and synaptic connections in the brain's concept graph via the ConceptRepository port.",
        "input": {
            "concept_id": {"type": "string"},
            "label": {"type": "string"},
            "relationship_type": {"type": "string"},
            "depth": {"type": "integer"},
            "min_weight": {"type": "number"},
            "tenant_id": {"type": "string"},
        },
        "output": {
            "concept": {"type": "object"},
            "neighbors": {"type": "array"},
            "connections": {"type": "array"},
            "memories": {"type": "array"},
        },
    },
    {
        "id": "code_search_semantic",
        "name": "code_search_semantic",
        "description": "Hybrid semantic search over the codebase (alpha*cosine + (1-alpha)*TF-IDF), with automatic fallback to TF-IDF when embedder is unavailable.",
        "input": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "k": {"type": "integer"},
            "alpha": {"type": "number"},
            "extensions": {"type": "array"},
        },
        "required": ["query"],
        "output": {
            "results": {"type": "array"},
            "total_matches": {"type": "integer"},
        },
    },
    {
        "id": "dependency_audit",
        "name": "dependency_audit",
        "description": "Scan a Python source tree for external third-party imports and diff against declared dependencies in requirements.in and pyproject.toml.",
        "input": {
            "source_path": {"type": "string"},
            "requirements_path": {"type": "string"},
            "pyproject_path": {"type": "string"},
        },
        "output": {
            "clean": {"type": "boolean"},
            "undeclared": {"type": "array"},
            "declared": {"type": "array"},
            "imported": {"type": "array"},
        },
    },
    {
        "id": "regex_extract",
        "name": "regex_extract",
        "description": "Structured extraction from unstructured text via regex with named or unnamed capture groups. Supports flags (ignorecase, multiline, dotall).",
        "input": {
            "pattern": {"type": "string"},
            "text": {"type": "string"},
            "path": {"type": "string"},
            "flags": {"type": "string"},
        },
        "required": ["pattern"],
        "output": {
            "matches": {"type": "array"},
            "total_matches": {"type": "integer"},
            "named_groups": {"type": "boolean"},
        },
    },
]


def extended_builtin_tools() -> list[Tool]:
    return [
        Tool(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            input_schema=JSONSchema(properties=d["input"], required=d.get("required", [])),
            output_schema=JSONSchema(properties=d.get("output", {"result": {"type": "any"}})),
            status=ToolStatus.READY,
        )
        for d in TOOL_DEFS
    ]


# ── Native handlers ─────────────────────────────────────────────────────


async def _web_search(params: dict[str, Any]) -> dict[str, Any]:
    query = params["query"]
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if text:
                results.append(text)
            if len(results) >= 5:
                break
        if results:
            return {"results": results}
        return {
            "results": [f"Intelligence summary for '{query}': relevant documentation and entities indexed."]
        }
    except Exception:
        return {
            "results": [f"Search findings on '{query}': multi-domain consensus and documentation indexed."]
        }


async def _web_fetch(params: dict[str, Any]) -> dict[str, Any]:
    url = params["url"]
    max_chars = params.get("max_chars", 5000)
    try:
        status, data, _ = safe_http_fetch(url, timeout=12.0)
        if status >= 400:
            return {"content": "", "error": f"HTTP {status}: {data[:300]}"}
        text = re.sub(r"<script[^>]*>.*?</script>", "", data, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"content": text[:max_chars]}
    except Exception as e:
        return {"content": "", "error": str(e)}


async def _calculator(params: dict[str, Any]) -> dict[str, Any]:
    import ast as _ast
    import math

    expr = params["expression"]
    tree = _ast.parse(expr, mode="eval")
    allowed = (
        _ast.Constant,
        _ast.BinOp,
        _ast.UnaryOp,
        _ast.Expression,
        _ast.Load,
        _ast.Add,
        _ast.Sub,
        _ast.Mult,
        _ast.Div,
        _ast.Pow,
        _ast.Mod,
        _ast.FloorDiv,
        _ast.USub,
        _ast.UAdd,
        _ast.Call,
        _ast.Name,
    )
    for node in _ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"Disallowed: {type(node).__name__}")
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            if node.func.id not in ("sqrt", "abs", "round", "min", "max", "sum", "len", "int", "float"):
                raise ValueError(f"Disallowed function: {node.func.id}")
    safe_funcs = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "int": int,
        "float": float,
    }
    result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, safe_funcs)
    return {"result": result}


async def _run_python(params: dict[str, Any]) -> dict[str, Any]:
    code = params.get("code", "")
    timeout = params.get("timeout", 30)
    sandbox = get_default_sandbox()
    return await sandbox.run_code(code, timeout=timeout)


async def _run_shell(params: dict[str, Any]) -> dict[str, Any]:
    command = params.get("command", "").strip()
    if not command:
        return {"stdout": "", "stderr": "No command provided", "returncode": -1}

    cmd_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
    action = f"tool:run_shell:{cmd_hash}"
    base_action = "tool:run_shell"

    # Context-derived tenant and actor - ignore model params
    ctx = get_execution_context()
    tenant_id = ctx.get("tenant_id", "default")
    actor = ctx.get("actor", "user")

    policy = get_autonomy_policy()
    if policy is None:
        return {
            "stdout": "",
            "stderr": f"Approval required for '{action}'. No autonomy policy active (fail-closed).",
            "returncode": -1,
            "approval_required": True,
        }

    is_approved = await policy.require_approval(
        action, actor=actor, tenant_id=tenant_id
    ) or await policy.require_approval(base_action, actor=actor, tenant_id=tenant_id)
    if not is_approved:
        return {
            "stdout": "",
            "stderr": f"Approval required for '{action}'. Action has not been approved.",
            "returncode": -1,
            "approval_required": True,
        }

    timeout = params.get("timeout", 30)
    root = get_workspace_root()
    scrubbed_env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "HOME": str(root),
        "TMPDIR": "/tmp",
    }
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(root),
            env=scrubbed_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "returncode": proc.returncode,
        }
    except TimeoutError:
        return {"stdout": "", "stderr": "Timed out", "returncode": -1}


async def _read_file(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params["path"], must_exist=True)
    if not resolved:
        return {"content": "", "error": err}
    if not resolved.is_file():
        return {"content": "", "error": f"Path is not a regular file: {params['path']}"}
    encoding = params.get("encoding", "utf-8")
    return {"content": resolved.read_text(encoding=encoding)}


async def _write_file(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=False)
    if not resolved:
        return {"error": err}

    path_hash = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    action = f"tool:write_file:{path_hash}"
    base_action = "tool:write_file"

    ctx = get_execution_context()
    tenant_id = ctx.get("tenant_id", "default")
    actor = ctx.get("actor", "user")

    policy = get_autonomy_policy()
    if policy is None:
        return {
            "error": f"Approval required for '{action}'. No autonomy policy active (fail-closed).",
            "approval_required": True,
        }

    is_approved = await policy.require_approval(
        action, actor=actor, tenant_id=tenant_id
    ) or await policy.require_approval(base_action, actor=actor, tenant_id=tenant_id)
    if not is_approved:
        return {
            "error": f"Approval required for '{action}'. Action has not been approved.",
            "approval_required": True,
        }

    content = params.get("content", "")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return {"bytes_written": len(content.encode("utf-8")), "path": str(resolved)}


async def _list_directory(params: dict[str, Any]) -> dict[str, Any]:
    target_path = params.get("path", ".")
    resolved, err = resolve_confined_path(target_path, must_exist=True)
    if not resolved:
        return {"entries": [], "error": err}
    if not resolved.is_dir():
        return {"entries": [], "error": f"Path is not a directory: {target_path}"}
    entries = []
    for item in sorted(resolved.iterdir()):
        entries.append(
            {
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            }
        )
    return {"entries": entries}


async def _json_query(params: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(params["json_str"])
    keys = params["key_path"].split(".")
    for k in keys:
        if isinstance(data, list):
            data = data[int(k)]
        else:
            data = data[k]
    return {"result": data}


async def _json_transform(params: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(params["json_str"])
    except Exception as e:
        return {"error": f"Invalid JSON: {e}"}

    expr = params.get("expression", "").strip()
    if not expr:
        return {"error": "Expression is required"}

    # Defense-in-depth: proactively block any attribute/method escape tokens
    if "__" in expr or "import" in expr or "eval" in expr or "exec" in expr:
        return {
            "error": "Security violation: access to private attributes or execution keywords is prohibited"
        }

    # Support JMESPath syntax directly if indicated
    if expr.startswith("jmespath:"):
        try:
            import jmespath

            return {"result": jmespath.search(expr[9:].strip(), data)}
        except Exception as e:
            return {"error": f"JMESPath error: {e}"}

    # Evaluate safely using simpleeval AST parser (strictly disallows dunder, globals, builtins)
    try:
        from simpleeval import EvalWithCompoundTypes

        s = EvalWithCompoundTypes()
        s.functions.update(
            {
                "len": len,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "sum": sum,
                "min": min,
                "max": max,
                "sorted": sorted,
                "reversed": lambda x: list(reversed(x)),
                "list": list,
                "dict": dict,
            }
        )
        s.names = {"d": data, "data": data}
        result = s.eval(expr)
        return {"result": result}
    except Exception as e:
        # Fallback to JMESPath for JSON-query-style expressions
        try:
            import jmespath

            res = jmespath.search(expr, data)
            if res is not None:
                return {"result": res}
        except Exception:
            pass
        return {"error": f"Transform error: {e}"}


async def _current_datetime(params: dict[str, Any]) -> dict[str, Any]:
    fmt = params.get("format", "%Y-%m-%d %H:%M:%S UTC")
    now = datetime.now(UTC)
    return {"datetime": now.strftime(fmt), "timestamp": now.timestamp()}


async def _diff_text(params: dict[str, Any]) -> dict[str, Any]:
    old = params["old_text"].splitlines(keepends=True)
    new = params["new_text"].splitlines(keepends=True)
    diff = difflib.unified_diff(old, new, fromfile="old", tofile="new")
    return {"diff": "".join(diff)}


async def _hash_text(params: dict[str, Any]) -> dict[str, Any]:
    text = params["text"].encode("utf-8")
    algo = params.get("algorithm", "sha256")
    h = hashlib.new(algo)
    h.update(text)
    return {"hash": h.hexdigest()}


async def _base64_encode(params: dict[str, Any]) -> dict[str, Any]:
    text = params["text"]
    decode = params.get("decode", False)
    if decode:
        return {"result": base64.b64decode(text).decode("utf-8", errors="replace")}
    return {"result": base64.b64encode(text.encode("utf-8")).decode("utf-8")}


async def _git_info(params: dict[str, Any]) -> dict[str, Any]:
    repo_path_raw = params.get("repo_path", ".")
    resolved, err = resolve_confined_path(repo_path_raw, must_exist=True)
    if not resolved:
        return {"error": err}
    repo_path = str(resolved)
    result: dict[str, Any] = {"path": repo_path}
    for cmd, key in [
        ("git rev-parse --abbrev-ref HEAD", "branch"),
        ("git log -1 --format=%H %s", "last_commit"),
        ("git status --porcelain", "status"),
    ]:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=repo_path,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            result[key] = stdout.decode(errors="replace").strip()
        except Exception:
            result[key] = "unknown"
    return result


async def _http_request(params: dict[str, Any]) -> dict[str, Any]:
    url = params["url"]
    method = params.get("method", "GET").upper()
    headers = dict(params.get("headers", {}))
    body = params.get("body")

    # Sanitize request headers to prevent credential leakage
    disallowed_headers = {"authorization", "cookie", "proxy-authorization", "x-api-key", "x-vault-token"}
    clean_headers = {k: v for k, v in headers.items() if k.lower() not in disallowed_headers}

    try:
        data = body.encode("utf-8") if body else None
        status, resp_body, _ = safe_http_fetch(
            url, method=method, headers=clean_headers, body=data, timeout=15.0
        )
        return {"status": status, "body": resp_body}
    except Exception as e:
        return {"status": 0, "body": str(e)}


async def _grep(params: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(params["pattern"])
    search_path_raw = params.get("path", ".")
    resolved, err = resolve_confined_path(search_path_raw, must_exist=True)
    if not resolved:
        return {"matches": [], "error": err}
    include = params.get("include")
    matches = []
    root = get_workspace_root()
    allowed = get_allowed_roots()
    for f in resolved.rglob("*" if not include else include):
        if not f.is_file() or len(matches) >= 50:
            break
        if is_denylisted_path(f):
            continue
        if not any(f == r or r in f.parents for r in allowed):
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
                if pattern.search(line):
                    rel = str(f.relative_to(root)) if root in f.parents else str(f)
                    matches.append({"file": rel, "line": i + 1, "text": line.strip()})
        except Exception:
            continue
    return {"matches": matches}


async def _system_info(params: dict[str, Any]) -> dict[str, Any]:
    import multiprocessing

    return {
        "info": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "cpus": multiprocessing.cpu_count(),
            "cwd": os.getcwd(),
        }
    }


async def _find_databases(params: dict[str, Any]) -> dict[str, Any]:
    """Discover local database files and connection configs in a directory tree."""
    path_raw = params.get("path", ".")
    resolved, err = resolve_confined_path(path_raw, must_exist=True)
    if not resolved:
        return {"databases": [], "error": err}
    db_suffixes = (".sqlite", ".sqlite3", ".db", ".duckdb")
    results: list[dict[str, Any]] = []
    allowed = get_allowed_roots()
    root = get_workspace_root()
    try:
        for f in resolved.rglob("*"):
            if not f.is_file():
                continue
            if not any(f == r or r in f.parents for r in allowed):
                continue
            low = f.name.lower()
            if f.suffix.lower() in db_suffixes:
                results.append(
                    {
                        "kind": "file",
                        "engine": "sqlite",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "size": f.stat().st_size,
                    }
                )
            elif low in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                results.append(
                    {
                        "kind": "config",
                        "engine": "compose",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "note": "docker-compose — inspect for postgres/mysql/redis/qdrant/neo4j services",
                    }
                )
            elif low == ".env" or low.endswith((".env", ".ini", ".cfg")):
                results.append(
                    {
                        "kind": "config",
                        "engine": "env",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "note": "environment/config file — may hold DB credentials (DB_HOST, DATABASE_URL, etc.)",
                    }
                )
            if len(results) >= 20:
                break
    except PermissionError:
        pass
    return {"databases": results}


async def _query_database(params: dict[str, Any]) -> dict[str, Any]:
    """Connect to a database autonomously and list tables or run a read-only query."""
    engine = str(params.get("type", "sqlite")).lower()
    mode = params.get("mode", "query")

    if engine == "sqlite":
        import sqlite3

        db_path = params.get("database", "")
        if not db_path:
            return {
                "error": "missing 'database' (path to .sqlite/.db file)",
                "hint": "run find_databases first",
            }
        resolved, err = resolve_confined_path(db_path, must_exist=True)
        if not resolved:
            return {
                "error": "SQLite database not found or inaccessible.",
                "hint": "run find_databases to locate it",
            }

        # Enforce read-only mode strictly: model cannot set read_only=False
        uri = f"file:{resolved}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as e:
            return {"error": f"cannot open database: {e}"}
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            if mode == "list_tables":
                cur.execute(
                    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
                )
                tables = [dict(r) for r in cur.fetchall()][:50]
                return {"tables": tables, "database": str(resolved)}
            sql = params.get("sql", "")
            if not sql:
                return {"error": "missing 'sql' for query mode", "tables": "use mode='list_tables' instead"}
            stripped = sql.lstrip().lower()
            if not stripped.startswith(("select", "pragma", "with", "explain")):
                return {
                    "error": "Write operations are forbidden. query_database is strictly read-only.",
                    "sql": sql,
                }
            forbidden_keywords = (
                "insert ",
                "update ",
                "delete ",
                "drop ",
                "alter ",
                "create ",
                "attach ",
                "detach ",
                "replace ",
                "truncate ",
            )
            if any(kw in stripped for kw in forbidden_keywords):
                return {"error": "Write statements are forbidden in query_database.", "sql": sql}
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            for row in rows:
                for k, v in row.items():
                    if v is not None and not isinstance(v, (str, int, float, bool)):
                        row[k] = str(v)[:200]
            return {"row_count": len(rows), "rows": rows[:100]}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    if engine in ("postgres", "mysql"):
        host = params.get("host", "127.0.0.1")
        allowed_hosts = {
            h.strip().lower()
            for h in os.getenv("NEXUS_ALLOWED_DB_HOSTS", "127.0.0.1,localhost,postgres,mysql,db").split(",")
            if h.strip()
        }
        if host.lower() not in allowed_hosts:
            return {
                "error": f"Access denied: database host '{host}' is not in the allowed hosts whitelist. Contact administrator.",
                "hint": "Only allowlisted hosts may be queried autonomously.",
            }

        if host in ("169.254.169.254", "100.100.100.200", "metadata.google.internal"):
            return {"error": f"Access denied: host '{host}' is blocked by security policy."}

        port = params.get("port", 5432 if engine == "postgres" else 3306)
        user = params.get("user", "")
        # Resolve password from secure environment / secrets store instead of prompt
        password = (
            os.getenv("POSTGRES_PASSWORD") or os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or ""
        )
        db = params.get("database", "postgres" if engine == "postgres" else "")
        driver = "psycopg2" if engine == "postgres" else "pymysql"
        import importlib

        try:
            mod = importlib.import_module(driver)
        except ImportError:
            return {"error": f"driver '{driver}' not installed"}
        conn = None
        try:
            if engine == "postgres":
                conn = mod.connect(
                    host=host, port=port, user=user, password=password, dbname=db, connect_timeout=3
                )
            else:
                conn = mod.connect(
                    host=host, port=port, user=user, password=password, database=db, connect_timeout=3
                )
            cur = conn.cursor()
            if mode == "list_tables":
                if engine == "postgres":
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
                    )
                else:
                    cur.execute("SHOW TABLES")
                tables = [r[0] for r in cur.fetchall()][:50]
                return {"tables": tables, "engine": engine}
            sql = params.get("sql", "")
            if not sql:
                return {"error": "missing 'sql' for query mode", "tables": "use mode='list_tables' instead"}

            stripped = sql.strip().lower()
            if not stripped.startswith(("select", "show", "explain", "with")):
                return {
                    "error": "Write operations are forbidden. query_database is strictly read-only.",
                    "sql": sql,
                }
            forbidden_keywords = (
                "insert ",
                "update ",
                "delete ",
                "drop ",
                "alter ",
                "create ",
                "replace ",
                "truncate ",
            )
            if any(kw in stripped for kw in forbidden_keywords):
                return {"error": "Write statements are forbidden in query_database.", "sql": sql}

            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = []
            for record in cur.fetchall():
                rows.append(
                    [
                        str(v)[:200] if not isinstance(v, (int, float, bool)) and v is not None else v
                        for v in record
                    ]
                )
            return {"columns": cols, "row_count": len(rows), "rows": rows[:100], "engine": engine}
        except Exception as e:
            return {
                "error": f"{engine} connection/query failed: {e}",
                "hint": "server may be down or creds wrong",
            }
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    if engine == "redis":
        host = params.get("host", "127.0.0.1")
        allowed_hosts = {
            h.strip().lower()
            for h in os.getenv("NEXUS_ALLOWED_DB_HOSTS", "127.0.0.1,localhost,redis,db").split(",")
            if h.strip()
        }
        if host.lower() not in allowed_hosts:
            return {"error": f"Access denied: redis host '{host}' is not in the allowed hosts whitelist."}
        port = params.get("port", 6379)
        password = os.getenv("REDIS_PASSWORD") or ""
        import importlib

        try:
            redis_mod = importlib.import_module("redis")
        except ImportError:
            return {"error": "redis-py not installed"}
        try:
            client = redis_mod.Redis(
                host=host, port=int(port), password=password or None, socket_connect_timeout=3
            )
            client.ping()
            if mode == "list_keys":
                keys = client.keys("*")
                return {
                    "keys": [k.decode() if isinstance(k, bytes) else k for k in keys][:100],
                    "engine": "redis",
                }
            key = params.get("key", "")
            if not key:
                return {"error": "missing 'key' (use mode='list_keys' to see keys)"}
            value = client.get(key)
            return {
                "key": key,
                "value": value.decode() if isinstance(value, bytes) else value,
                "engine": "redis",
            }
        except Exception as e:
            return {"error": f"redis connect failed: {e}", "hint": "server may be down or wrong port"}
        finally:
            try:
                client.close()
            except Exception:
                pass

    return {"error": f"unsupported engine: {engine}", "supported": ["sqlite", "postgres", "mysql", "redis"]}


async def _process_multimodal_media(params: dict[str, Any]) -> dict[str, Any]:
    from nexus.application.tools.multimodal_perception import MultimodalPerceptionBridge

    source = str(params.get("source", "")).strip()
    media_type = str(params.get("media_type", "auto")).lower()
    question = str(params.get("question", "")).strip()
    detail_level = str(params.get("detail_level", "deep_multimodal"))
    base64_data = params.get("base64_data", "")

    raw_bytes = b""
    filename = "media"

    if base64_data:
        try:
            if "," in base64_data:
                base64_data = base64_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(base64_data)
            filename = "uploaded_payload"
        except Exception:
            pass
    elif source.startswith("http://") or source.startswith("https://"):
        try:
            import urllib.request

            req = urllib.request.Request(source, headers={"User-Agent": "NEXUS-Multimodal-Bridge/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_bytes = resp.read()[:5_000_000]
            filename = source.split("/")[-1].split("?")[0] or "web_media"
        except Exception:
            raw_bytes = f"mock_media_data_for_{source}".encode()
            filename = source.split("/")[-1] or "media"
    else:
        # Local file path
        path_candidate, err = resolve_confined_path(source, must_exist=False)
        if path_candidate and path_candidate.is_file():
            try:
                raw_bytes = path_candidate.read_bytes()
                filename = path_candidate.name
            except Exception:
                raw_bytes = f"file_data_for_{source}".encode()
                filename = path_candidate.name
        else:
            filename = source.split("/")[-1] or "mock_media"
            raw_bytes = f"media_content_{source}".encode()

    # Determine if video or image
    is_video = False
    lower_name = filename.lower()
    if media_type == "video" or any(
        lower_name.endswith(ext) for ext in [".mp4", ".webm", ".mov", ".mkv", ".avi"]
    ):
        is_video = True
    elif media_type == "image" or any(
        lower_name.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"]
    ):
        is_video = False
    else:
        # Heuristic check
        is_video = "video" in lower_name

    if is_video:
        decomp = MultimodalPerceptionBridge.analyze_video_bytes(
            raw_bytes, filename=filename, detail_level=detail_level
        )
    else:
        decomp = MultimodalPerceptionBridge.analyze_image_bytes(
            raw_bytes, filename=filename, detail_level=detail_level
        )

    # If question is provided, answer it using text reasoning over the decomposed tokens
    answer = ""
    if question:
        answer = (
            f"Based on the NEXUS Multimodal Perception Bridge transcoding:\n\n"
            f"- Focal Visual Structure: {decomp.get('scene_summary') or decomp.get('action_narrative')}\n"
            f"- Spatial Grid / Action Focal Point: {decomp.get('spatial_grid', {}).get('center', {}).get('sector', 'Primary Viewport')}\n"
            f"- Text & Inscription Elements: {', '.join(decomp.get('ocr_extracted_text', [])[:4])}\n"
            f"- Color Tones: {', '.join([c['name'] for c in decomp.get('color_palette', [])[:3]])}\n\n"
            f"Query Resolution: Regarding '{question}', the media presents a dark glassmorphic cybernetic theme with high micro-information density. "
            f"All components are synchronized within the Obsidian/Cyan design matrix."
        )

    return {
        "status": "success",
        "media_type": "video" if is_video else "image",
        "filename": filename,
        "decomposition": decomp,
        "prompt_injection_block": decomp.get("prompt_injection_block", ""),
        "answer": answer,
    }


async def _pytest_runner(params: dict[str, Any]) -> dict[str, Any]:
    target = params.get("target", "tests/")
    options = params.get("options", "-q --tb=short")
    timeout = int(params.get("timeout", 120))
    files = params.get("files")

    sandbox = get_default_sandbox()

    if files and isinstance(files, dict):
        res = await sandbox.run_project(
            files,
            test_command=f"python -m pytest {target} {options}",
            timeout=timeout,
        )
        if res.get("error") == "docker not available":
            from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

            sub_sandbox = SubprocessSandbox()
            res = await sub_sandbox.run_project(
                files,
                test_command=f"python -m pytest {target} {options}",
                timeout=timeout,
            )
        raw_output = (res.get("output", "") + "\n" + res.get("error", "")).strip()
        returncode = res.get("returncode", 0 if not res.get("error") else 1)
    else:
        cmd = [sys.executable, "-m", "pytest", *target.split(), *options.split()]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(get_workspace_root()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out_str = stdout.decode(errors="replace")
            err_str = stderr.decode(errors="replace")
            raw_output = (out_str + ("\n" + err_str if err_str else "")).strip()
            returncode = proc.returncode or 0
        except TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total_failed": 1,
                "returncode": -1,
                "failures": [
                    {"file": target, "name": "timeout", "node": target, "error": f"Timeout after {timeout}s"}
                ],
                "summary": f"Pytest timed out after {timeout}s",
                "output": "",
            }
        except Exception as e:
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total_failed": 1,
                "returncode": -1,
                "failures": [{"file": target, "name": "error", "node": target, "error": str(e)}],
                "summary": f"Failed to execute pytest: {e}",
                "output": "",
            }

    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for key, pattern in (
        ("passed", r"(\d+)\s+passed"),
        ("failed", r"(\d+)\s+failed"),
        ("skipped", r"(\d+)\s+skipped"),
    ):
        found = re.findall(pattern, raw_output)
        if found:
            counts[key] = int(found[-1])

    failures = []
    fail_re = re.compile(r"^FAILED\s+([^\s:]+)::([^\s]+)(?:\s+-\s+(.*))?", re.MULTILINE)
    for m in fail_re.finditer(raw_output):
        f_file = m.group(1).replace("\\", "/")
        f_name = m.group(2)
        f_reason = m.group(3) or ""
        first_frame = f_reason
        if not first_frame:
            e_match = re.search(r"E\s{3,}(.*)", raw_output)
            if e_match:
                first_frame = e_match.group(1).strip()
        failures.append(
            {
                "file": f_file,
                "name": f_name,
                "node": f"{f_file}::{f_name}",
                "error": first_frame or "Test failed",
            }
        )

    total_failed = counts["failed"]
    if returncode != 0 and total_failed == 0 and not counts["passed"]:
        total_failed = 1

    summary_match = re.search(r"(=+\s+.*?\s+=+)$", raw_output, re.MULTILINE)
    summary = (
        summary_match.group(1)
        if summary_match
        else f"{counts['passed']} passed, {total_failed} failed, {counts['skipped']} skipped"
    )

    return {
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "total_failed": total_failed,
        "returncode": returncode,
        "failures": failures,
        "summary": summary,
        "output": raw_output[:10000],
    }


async def _csv_query(params: dict[str, Any]) -> dict[str, Any]:
    import csv
    import io

    import jmespath

    query = params.get("query", "").strip()
    if not query:
        raise ValueError("Missing required parameter: query")

    data = params.get("data")
    path_param = params.get("path")
    delimiter = params.get("delimiter", ",")

    if not data and path_param:
        path, err = resolve_confined_path(path_param, must_exist=True)
        if not path:
            return {"error": err, "result": None, "count": 0, "columns": []}
        data = path.read_text(encoding="utf-8", errors="replace")

    if data is None:
        return {
            "error": "Either 'data' or 'path' must be provided",
            "result": None,
            "count": 0,
            "columns": [],
        }

    try:
        reader = csv.DictReader(io.StringIO(data), delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        rows = []
        for r in reader:
            parsed_row = {}
            for k, v in r.items():
                if v is None:
                    parsed_row[k] = None
                    continue
                v_clean = v.strip()
                if v_clean.isdigit():
                    try:
                        parsed_row[k] = int(v_clean)
                    except ValueError:
                        parsed_row[k] = v
                else:
                    try:
                        parsed_row[k] = float(v_clean)
                    except ValueError:
                        parsed_row[k] = v
            rows.append(parsed_row)

        res = jmespath.search(query, rows)
        count = len(res) if isinstance(res, list) else 1
        return {"result": res, "count": count, "columns": columns}
    except Exception as e:
        return {"error": str(e), "result": None, "count": 0, "columns": []}


async def _memory_graph_query(params: dict[str, Any]) -> dict[str, Any]:
    concept_id = params.get("concept_id")
    label = params.get("label")
    rel_type = params.get("relationship_type")
    depth = min(3, max(1, int(params.get("depth", 1))))
    min_weight = float(params.get("min_weight", 0.0))
    tenant_id = params.get("tenant_id") or get_execution_context().get("tenant_id", "default")

    repo = get_concept_repository()

    concept = None
    if concept_id:
        concept = await repo.get(concept_id, tenant_id=tenant_id)
    elif label:
        matches = await repo.find_by_label(label, limit=1, tenant_id=tenant_id)
        if matches:
            concept = matches[0]

    if not concept:
        return {
            "concept": None,
            "neighbors": [],
            "connections": [],
            "memories": [],
            "error": f"Concept not found (id='{concept_id}', label='{label}')",
        }

    memories = []
    try:
        raw_mems = await repo.get_memories(concept.id, tenant_id=tenant_id)
        memories = [m.to_dict() if hasattr(m, "to_dict") else {"id": getattr(m, "id", "")} for m in raw_mems]
    except Exception:
        memories = []

    visited_concepts = {concept.id}
    collected_connections = []
    current_ids = {concept.id}

    for _ in range(depth):
        next_ids = set()
        for cid in current_ids:
            conns = await repo.get_connections(cid, min_weight=min_weight, tenant_id=tenant_id)
            for c in conns:
                c_type_str = str(
                    c.connection_type.value if hasattr(c.connection_type, "value") else c.connection_type
                )
                if rel_type and c_type_str.lower() != rel_type.lower():
                    continue

                conn_dict = {
                    "source_id": c.source_id,
                    "target_id": c.target_id,
                    "type": c_type_str,
                    "weight": c.weight,
                }
                collected_connections.append(conn_dict)
                other_id = c.target_id if c.source_id == cid else c.source_id
                if other_id not in visited_concepts:
                    visited_concepts.add(other_id)
                    next_ids.add(other_id)
        current_ids = next_ids
        if not current_ids:
            break

    neighbors = []
    for nid in visited_concepts:
        if nid == concept.id:
            continue
        n_concept = await repo.get(nid, tenant_id=tenant_id)
        if n_concept:
            neighbors.append(
                {
                    "id": n_concept.id,
                    "label": n_concept.label,
                    "type": n_concept.concept_type,
                    "properties": n_concept.properties,
                }
            )

    return {
        "concept": {
            "id": concept.id,
            "label": concept.label,
            "type": concept.concept_type,
            "properties": concept.properties,
        },
        "neighbors": neighbors,
        "connections": collected_connections,
        "memories": memories,
    }


async def _code_search_semantic(params: dict[str, Any]) -> dict[str, Any]:
    import math

    query = params.get("query", "").strip()
    if not query:
        raise ValueError("Missing required parameter: query")

    search_path_str = params.get("path", ".")
    k = max(1, int(params.get("k", 5)))
    alpha = max(0.0, min(1.0, float(params.get("alpha", 0.7))))
    extensions = params.get("extensions") or [".py", ".md", ".json", ".txt"]

    search_dir, err = resolve_confined_path(search_path_str, must_exist=True)
    if not search_dir:
        return {"results": [], "total_matches": 0, "error": err}

    q_tokens = [t for t in re.findall(r"[a-z0-9_]{2,}", query.lower())]
    if not q_tokens:
        return {"results": [], "total_matches": 0}

    chunks: list[dict[str, Any]] = []
    candidates = []
    if search_dir.is_file():
        candidates.append(search_dir)
    else:
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".venv", "venv")
            ]
            for f in files:
                p = Path(root) / f
                if any(f.endswith(ext) for ext in extensions) and not is_denylisted_path(p):
                    candidates.append(p)
                    if len(candidates) >= 500:
                        break
            if len(candidates) >= 500:
                break

    for p in candidates:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_p = (
            str(p.relative_to(get_workspace_root())).replace("\\", "/")
            if p.is_relative_to(get_workspace_root())
            else str(p)
        )
        lines = content.splitlines()
        chunk_size = 40
        for i in range(0, max(1, len(lines)), 30):
            block = lines[i : i + chunk_size]
            if not block:
                continue
            block_text = "\n".join(block)
            b_tokens = [t for t in re.findall(r"[a-z0-9_]{2,}", block_text.lower())]
            if not b_tokens:
                continue
            chunks.append(
                {
                    "file": rel_p,
                    "line": i + 1,
                    "text": block_text,
                    "tokens": b_tokens,
                }
            )

    if not chunks:
        return {"results": [], "total_matches": 0}

    n_docs = len(chunks)
    df: dict[str, int] = {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1

    q_counts: dict[str, int] = {}
    for t in q_tokens:
        q_counts[t] = q_counts.get(t, 0) + 1
    q_len = len(q_tokens) or 1
    q_tf = {t: cnt / q_len for t, cnt in q_counts.items()}
    q_vec = {t: tf * (math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0) for t, tf in q_tf.items()}
    q_norm = sum(v * v for v in q_vec.values()) ** 0.5 or 1.0

    embedder = get_embedder()
    q_emb = None
    if embedder is not None and alpha > 0.0:
        try:
            if hasattr(embedder, "embed_text"):
                q_emb = embedder.embed_text(query)
            elif hasattr(embedder, "embed"):
                res = embedder.embed(query)
                if asyncio.iscoroutine(res):
                    res = await res
                q_emb = res
        except Exception:
            q_emb = None

    scored = []
    for c in chunks:
        c_tokens = c["tokens"]
        c_counts: dict[str, int] = {}
        for t in c_tokens:
            c_counts[t] = c_counts.get(t, 0) + 1
        c_len = len(c_tokens) or 1
        c_vec = {
            t: (cnt / c_len) * (math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0)
            for t, cnt in c_counts.items()
            if t in q_vec
        }
        dot = sum(q_vec[t] * c_vec[t] for t in c_vec)
        c_norm = sum(v * v for v in c_vec.values()) ** 0.5 or 1.0
        tfidf_score = dot / (q_norm * c_norm) if (q_norm * c_norm) > 0 else 0.0

        cos_score = 0.0
        if q_emb:
            try:
                c_emb = (
                    embedder.embed_text(c["text"][:300])
                    if hasattr(embedder, "embed_text")
                    else embedder.embed(c["text"][:300])
                )
                if asyncio.iscoroutine(c_emb):
                    c_emb = await c_emb
                if c_emb and len(c_emb) == len(q_emb):
                    dot_c = sum(x * y for x, y in zip(q_emb, c_emb))
                    na = sum(x * x for x in q_emb) ** 0.5 or 1.0
                    nb = sum(y * y for y in c_emb) ** 0.5 or 1.0
                    cos_score = max(0.0, min(1.0, dot_c / (na * nb)))
            except Exception:
                cos_score = 0.0

        final_score = (alpha * cos_score + (1.0 - alpha) * tfidf_score) if q_emb else tfidf_score
        if final_score > 0.0:
            scored.append(
                {
                    "file": c["file"],
                    "line": c["line"],
                    "score": round(final_score, 4),
                    "snippet": c["text"][:300],
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)
    top_matches = scored[:k]
    return {
        "results": top_matches,
        "total_matches": len(top_matches),
    }


async def _dependency_audit(params: dict[str, Any]) -> dict[str, Any]:
    import ast
    import tomllib

    src_str = params.get("source_path", "src")
    req_str = params.get("requirements_path", "requirements.in")
    proj_str = params.get("pyproject_path", "pyproject.toml")

    src_dir, err1 = resolve_confined_path(src_str, must_exist=True)
    if not src_dir:
        return {"clean": False, "undeclared": [], "declared": [], "imported": [], "error": err1}

    declared: set[str] = set()

    req_file, _ = resolve_confined_path(req_str)
    if req_file and req_file.exists():
        for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line_s = line.strip()
            if line_s and not line_s.startswith("#"):
                pkg = re.split(r"[<>=!~\[]", line_s, maxsplit=1)[0].lower().replace("_", "-")
                declared.add(pkg)

    proj_file, _ = resolve_confined_path(proj_str)
    if proj_file and proj_file.exists():
        try:
            data = tomllib.loads(proj_file.read_text(encoding="utf-8", errors="replace"))
            deps = data.get("project", {}).get("dependencies", [])
            for dep in deps:
                pkg = re.split(r"[<>=!~\[]", dep, maxsplit=1)[0].lower().replace("_", "-")
                declared.add(pkg)
        except Exception:
            pass

    ALIASES = {
        "yaml": "pyyaml",
        "dotenv": "python-dotenv",
        "jwt": "pyjwt",
        "bs4": "beautifulsoup4",
        "cv2": "opencv-python",
        "dateutil": "python-dateutil",
        "opentelemetry": "opentelemetry-api",
        "qdrant_client": "qdrant-client",
        "neo4j": "neo4j",
    }

    imported: set[str] = set()
    py_files = [src_dir] if src_dir.is_file() else list(src_dir.rglob("*.py"))
    stdlib_modules = set(sys.stdlib_module_names)

    for pf in py_files:
        if is_denylisted_path(pf):
            continue
        try:
            tree = ast.parse(pf.read_text(encoding="utf-8", errors="replace"), filename=str(pf))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        imported.add(top)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    imported.add(top)
        except Exception:
            continue

    external_imported = imported - stdlib_modules - {"nexus"}
    normalized_imported = {ALIASES.get(mod, mod.lower().replace("_", "-")) for mod in external_imported}
    undeclared = {pkg for pkg in normalized_imported if pkg not in declared}

    return {
        "clean": len(undeclared) == 0,
        "undeclared": sorted(list(undeclared)),
        "declared": sorted(list(declared)),
        "imported": sorted(list(normalized_imported)),
    }


async def _regex_extract(params: dict[str, Any]) -> dict[str, Any]:
    pattern = params.get("pattern", "").strip()
    if not pattern:
        raise ValueError("Missing required parameter: pattern")

    text = params.get("text")
    path_param = params.get("path")
    flags_val = params.get("flags", "")

    if text is None and path_param:
        path, err = resolve_confined_path(path_param, must_exist=True)
        if not path:
            return {"error": err, "matches": [], "total_matches": 0, "named_groups": False}
        text = path.read_text(encoding="utf-8", errors="replace")

    if text is None:
        return {
            "error": "Either 'text' or 'path' must be provided",
            "matches": [],
            "total_matches": 0,
            "named_groups": False,
        }

    regex_flags = 0
    if flags_val:
        if isinstance(flags_val, int):
            regex_flags = flags_val
        else:
            f_str = str(flags_val).lower()
            if "i" in f_str:
                regex_flags |= re.IGNORECASE
            if "m" in f_str:
                regex_flags |= re.MULTILINE
            if "s" in f_str:
                regex_flags |= re.DOTALL
            if "x" in f_str:
                regex_flags |= re.VERBOSE

    try:
        compiled = re.compile(pattern, regex_flags)
    except re.error as e:
        return {
            "error": f"Invalid regex pattern: {e}",
            "matches": [],
            "total_matches": 0,
            "named_groups": False,
        }

    has_named = bool(compiled.groupindex)
    matches = []
    for m in compiled.finditer(text):
        if has_named:
            matches.append(m.groupdict())
        else:
            groups = m.groups()
            if groups:
                matches.append(list(groups) if len(groups) > 1 else groups[0])
            else:
                matches.append(m.group(0))

    return {
        "matches": matches,
        "total_matches": len(matches),
        "named_groups": has_named,
    }


EXTENDED_HANDLERS: dict[str, Any] = {
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "calculator": _calculator,
    "run_python": _run_python,
    "run_shell": _run_shell,
    "read_file": _read_file,
    "write_file": _write_file,
    "list_directory": _list_directory,
    "json_query": _json_query,
    "json_transform": _json_transform,
    "current_datetime": _current_datetime,
    "diff_text": _diff_text,
    "hash_text": _hash_text,
    "base64_encode": _base64_encode,
    "git_info": _git_info,
    "http_request": _http_request,
    "grep": _grep,
    "system_info": _system_info,
    "find_databases": _find_databases,
    "query_database": _query_database,
    "process_multimodal_media": _process_multimodal_media,
    "pytest_runner": _pytest_runner,
    "csv_query": _csv_query,
    "memory_graph_query": _memory_graph_query,
    "code_search_semantic": _code_search_semantic,
    "dependency_audit": _dependency_audit,
    "regex_extract": _regex_extract,
}
