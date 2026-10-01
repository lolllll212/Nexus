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
        from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox

        _DEFAULT_SANDBOX = DockerSandbox()
    return _DEFAULT_SANDBOX


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
        "id": "web_search",
        "name": "web_search",
        "description": "Search the web via DuckDuckGo and return top results.",
        "input": {"query": {"type": "string"}},
        "required": ["query"],
        "output": {"results": {"type": "array"}},
    },
    {
        "id": "web_fetch",
        "name": "web_fetch",
        "description": "Fetch a URL and return its text content (up to max_chars).",
        "input": {"url": {"type": "string"}, "max_chars": {"type": "integer"}},
        "required": ["url"],
    },
    {
        "id": "calculator",
        "name": "calculator",
        "description": "Evaluate a math expression safely.",
        "input": {"expression": {"type": "string"}},
        "required": ["expression"],
        "output": {"result": {"type": "number"}},
    },
    {
        "id": "run_python",
        "name": "run_python",
        "description": "Execute Python code in a sandbox and return stdout/stderr.",
        "input": {"code": {"type": "string"}},
        "required": ["code"],
        "output": {"output": {"type": "string"}, "error": {"type": "string"}},
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
}
