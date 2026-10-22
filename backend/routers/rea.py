"""REA workbench + blueprint memory endpoints."""

import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.schemas import BlueprintSaveRequest, ReaAnalyzeRequest

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

router = APIRouter()

# ─── REA workbench + blueprint memory ─────────────────────────────────────────

from nexus.infrastructure.adapters.persistence.agent_memory_store import (  # noqa: E402
    AgentMemoryStore,
)

REA_ROOT = ROOT_DIR / "vendor" / "rea"
REA_ENTRY = REA_ROOT / "scripts" / "rea.mjs"
REA_DIST = REA_ROOT / "dist" / "mcp" / "main.js"

# Curated, read-only analysis tools exposed to the REA workbench UI.
REA_TOOLS: dict[str, str] = {
    "inspect_pe_resources": "Static PE32/PE32+ resource inventory (fast)",
    "inspect_electron_fuses": "Electron fuse wire bytes + derived implications (fast)",
    "inspect_sqlite_database": "Offline SQLite schema + sampled rows (fast)",
    "analyze_javascript_application": "Execution-free JavaScript app graph (slow)",
}


def _memory() -> AgentMemoryStore:
    return AgentMemoryStore(ROOT_DIR / "agent_memory.json")


def _compose_blueprint(
    title: str, goal: str, steps: list[str], files: list[str], verify: list[str], tools: list[str]
) -> str:
    lines = [f"BLUEPRINT: {title}", f"GOAL: {goal}"]
    if steps:
        lines.append("STEPS:")
        lines.extend(f"{i}. {s}" for i, s in enumerate(steps, 1))
    if files:
        lines.append(f"FILES: {', '.join(files)}")
    if verify:
        lines.append("VERIFY: " + " ; ".join(verify))
    if tools:
        lines.append(f"TOOLS: {', '.join(tools)}")
    return "\n".join(lines)


def _rea_mcp_call(tool: str, args: dict[str, Any], timeout: float = 120.0) -> tuple[str | None, str | None]:
    """Drive the vendored REA MCP server over stdio for one tool call."""
    if not (REA_ENTRY.is_file() and REA_DIST.is_file()):
        return None, "REA is not built. Run: python scripts/setup_rea.py"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT_DIR / "scripts" / "rea_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(ROOT_DIR),
    )
    try:

        def send(obj: dict[str, Any]) -> None:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()

        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "nexus-cosmos", "version": "1.0.0"},
                },
            }
        )
        proc.stdout.readline()  # initialize response
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                return None, "REA server closed unexpectedly"
            with contextlib.suppress(json.JSONDecodeError):
                obj = json.loads(line)
                if obj.get("id") == 2:
                    if "error" in obj:
                        return None, str(obj["error"].get("message", "REA error"))
                    content = obj.get("result", {}).get("content", [])
                    text = content[0].get("text", "") if content else ""
                    return text, None
        return None, f"REA call timed out after {timeout:.0f}s"
    finally:
        proc.kill()


@router.post("/api/rea/analyze")
async def api_rea_analyze(req: ReaAnalyzeRequest):
    """Run one whitelisted REA analysis tool and return its evidence text."""
    if req.tool not in REA_TOOLS:
        return JSONResponse(
            {"ok": False, "error": f"Tool '{req.tool}' is not in the workbench whitelist"},
            status_code=400,
        )
    args = dict(req.extra_args or {})
    if "path" not in args:
        target = Path(req.path)
        if not target.is_absolute():
            target = (ROOT_DIR / target).resolve()
        args["path"] = str(target)
    text, err = _rea_mcp_call(req.tool, args)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=502)
    return JSONResponse({"ok": True, "tool": req.tool, "path": req.path, "result": text[:20000]})


@router.get("/api/rea/tools")
async def api_rea_tools():
    ready = REA_ENTRY.is_file() and REA_DIST.is_file()
    return JSONResponse({"tools": REA_TOOLS, "ready": ready})


@router.get("/api/blueprints")
async def api_blueprints(q: str = "", k: int = 8):
    """Query (or list) saved blueprints from the shared memory store."""
    store = _memory()
    if q.strip():
        hits = store.query(q, k=max(k * 3, 12))
        chunks = [c for c, _score in hits if c.kind == "blueprint"][:k]
    else:
        chunks = store.latest(kind="blueprint", n=k)
    return JSONResponse(
        {
            "blueprints": [
                {"id": c.id, "agent": c.agent, "tags": sorted(c.tags), "text": c.text} for c in chunks
            ]
        }
    )


@router.post("/api/blueprints")
async def api_save_blueprint(req: BlueprintSaveRequest):
    store = _memory()
    tags = [t.strip() for t in req.tags.split(",") if t.strip()]
    text = _compose_blueprint(req.title, req.goal, req.steps, req.files, req.verify, req.tools)
    chunk, created = store.put(agent="holo", kind="blueprint", text=text, tags=tags or ["blueprint"])
    return JSONResponse({"ok": True, "id": chunk.id, "created": created})
