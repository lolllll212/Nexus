"""
Extended built-in tools — practical capabilities the brain can always use.
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import json
import os
import platform
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema


TOOL_DEFS: List[Dict[str, Any]] = [
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
        "output": {"stdout": {"type": "string"}, "stderr": {"type": "string"}, "returncode": {"type": "integer"}},
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
]


def extended_builtin_tools() -> List[Tool]:
    return [
        Tool(
            id=d["id"], name=d["name"], description=d["description"],
            input_schema=JSONSchema(properties=d["input"], required=d.get("required", [])),
            output_schema=JSONSchema(properties=d.get("output", {"result": {"type": "any"}})),
            status=ToolStatus.READY,
        )
        for d in TOOL_DEFS
    ]


# ── Native handlers ─────────────────────────────────────────────────────


async def _web_search(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params["query"]
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NEXUS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if text:
                results.append(text)
            if len(results) >= 5:
                break
        return {"results": results or ["No results found."]}
    except Exception as e:
        return {"results": [], "error": str(e)}


async def _web_fetch(params: Dict[str, Any]) -> Dict[str, Any]:
    url = params["url"]
    max_chars = params.get("max_chars", 5000)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NEXUS/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", "", data, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"content": text[:max_chars]}
    except Exception as e:
        return {"content": "", "error": str(e)}


async def _calculator(params: Dict[str, Any]) -> Dict[str, Any]:
    import ast as _ast
    import math
    expr = params["expression"]
    tree = _ast.parse(expr, mode="eval")
    allowed = (_ast.Constant, _ast.BinOp, _ast.UnaryOp, _ast.Expression, _ast.Load, _ast.Add, _ast.Sub, _ast.Mult,
               _ast.Div, _ast.Pow, _ast.Mod, _ast.FloorDiv, _ast.USub, _ast.UAdd, _ast.Call, _ast.Name)
    for node in _ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"Disallowed: {type(node).__name__}")
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            if node.func.id not in ("sqrt", "abs", "round", "min", "max", "sum", "len", "int", "float"):
                raise ValueError(f"Disallowed function: {node.func.id}")
    safe_funcs = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max, "sum": sum, "len": len, "int": int, "float": float}
    result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, safe_funcs)
    return {"result": result}


async def _run_python(params: Dict[str, Any]) -> Dict[str, Any]:
    code = params["code"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {"output": stdout.decode(errors="replace"), "error": stderr.decode(errors="replace")}
    except asyncio.TimeoutError:
        return {"output": "", "error": "Timed out (30s limit)"}


async def _run_shell(params: Dict[str, Any]) -> Dict[str, Any]:
    command = params["command"]
    timeout = params.get("timeout", 30)
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"stdout": "", "stderr": "Timed out", "returncode": -1}


async def _read_file(params: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(params["path"])
    encoding = params.get("encoding", "utf-8")
    if not path.exists():
        return {"content": "", "error": f"File not found: {path}"}
    return {"content": path.read_text(encoding=encoding)}


async def _write_file(params: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(params["path"])
    content = params["content"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"bytes_written": len(content.encode("utf-8"))}


async def _list_directory(params: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(params["path"])
    if not path.exists():
        return {"entries": [], "error": f"Directory not found: {path}"}
    entries = []
    for item in sorted(path.iterdir()):
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else 0,
        })
    return {"entries": entries}


async def _json_query(params: Dict[str, Any]) -> Dict[str, Any]:
    data = json.loads(params["json_str"])
    keys = params["key_path"].split(".")
    for k in keys:
        if isinstance(data, list):
            data = data[int(k)]
        else:
            data = data[k]
    return {"result": data}


async def _json_transform(params: Dict[str, Any]) -> Dict[str, Any]:
    data = json.loads(params["json_str"])
    safe_builtins = {"len": len, "int": int, "float": float, "str": str, "bool": bool, "sum": sum,
                     "min": min, "max": max, "sorted": sorted, "reversed": reversed, "list": list, "dict": dict}
    result = eval(params["expression"], {"__builtins__": safe_builtins}, {"d": data})
    return {"result": result}


async def _current_datetime(params: Dict[str, Any]) -> Dict[str, Any]:
    fmt = params.get("format", "%Y-%m-%d %H:%M:%S UTC")
    now = datetime.now(timezone.utc)
    return {"datetime": now.strftime(fmt), "timestamp": now.timestamp()}


async def _diff_text(params: Dict[str, Any]) -> Dict[str, Any]:
    old = params["old_text"].splitlines(keepends=True)
    new = params["new_text"].splitlines(keepends=True)
    diff = difflib.unified_diff(old, new, fromfile="old", tofile="new")
    return {"diff": "".join(diff)}


async def _hash_text(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params["text"].encode("utf-8")
    algo = params.get("algorithm", "sha256")
    h = hashlib.new(algo)
    h.update(text)
    return {"hash": h.hexdigest()}


async def _base64_encode(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params["text"]
    decode = params.get("decode", False)
    if decode:
        return {"result": base64.b64decode(text).decode("utf-8", errors="replace")}
    return {"result": base64.b64encode(text.encode("utf-8")).decode("utf-8")}


async def _git_info(params: Dict[str, Any]) -> Dict[str, Any]:
    repo_path = params["repo_path"]
    result = {}
    for cmd, key in [
        ("git rev-parse --abbrev-ref HEAD", "branch"),
        ("git log -1 --format=%H %s", "last_commit"),
        ("git status --porcelain", "status"),
    ]:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=repo_path,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            result[key] = stdout.decode(errors="replace").strip()
        except Exception:
            result[key] = "unknown"
    return result


async def _http_request(params: Dict[str, Any]) -> Dict[str, Any]:
    url = params["url"]
    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")
    try:
        data = body.encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"status": resp.status, "body": resp.read().decode("utf-8", errors="replace")}
    except Exception as e:
        return {"status": 0, "body": str(e)}


async def _grep(params: Dict[str, Any]) -> Dict[str, Any]:
    pattern = re.compile(params["pattern"])
    search_path = Path(params.get("path", "."))
    include = params.get("include")
    matches = []
    for f in search_path.rglob("*" if not include else include):
        if not f.is_file() or len(matches) >= 50:
            break
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
                if pattern.search(line):
                    matches.append({"file": str(f), "line": i + 1, "text": line.strip()})
        except Exception:
            continue
    return {"matches": matches}


async def _system_info(params: Dict[str, Any]) -> Dict[str, Any]:
    import multiprocessing
    return {"info": {
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpus": multiprocessing.cpu_count(),
        "cwd": os.getcwd(),
    }}


EXTENDED_HANDLERS: Dict[str, Any] = {
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
}
