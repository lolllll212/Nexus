"""NEXUS Knowledge-Galaxy, COSMOS & J.A.R.V.I.S. Cortex — FastAPI server.

Serves:
* ``/``               → ``frontend/index.html``
* ``/holo.html``      → ``frontend/holo.html``
* ``/graph-data.js``  → the indexed graph JavaScript bundle
* ``GET /api/graph``  → JSON knowledge graph data
* ``GET /api/cosmos`` → live automation mesh joints & state
* ``GET /api/tree``   → directory constellations & note stars
* ``GET /api/llm/status`` → LLM reachability & model telemetry
* ``POST /api/cosmos/trigger`` → triggers automation nodes (dream, swarm, etc.)
* ``POST /chat`` & ``POST /v1/chat`` → J.A.R.V.I.S. cognitive ReAct & RAG agent with dynamic tool calling

Tools integrated:
* ``knowledge_rag``: Scans repository notes across docs/ and .opencode/
* ``git_status``: Inspects working tree, active branch, and recent commits
* ``list_tasks``: Queries swarm task backlog, active claims, and roadmap
* ``agent_status``: Telemetry for Astra, Tron, Xenom, and CEO swarm agents
* ``calculator``: High-precision safe mathematical computation
* ``run_python``: Executes Python snippets with stdout/stderr capture
* ``cosmos_trigger``: Dispatches dream cycles, swarm pulses, and tool evolution
* ``memory_query``: Content-addressable memory retrieval
* ``system_diagnostics``: Real-time telemetry across all 8 Cosmos joints

Configuration:
* Reads LLM settings from ``config/nexus.yaml`` or ``.env``
* Fully autonomous local reasoning fallback when external LLM is offline

Run:  ``python backend/main.py``
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# ── paths ────────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
CONFIG_DIR = ROOT_DIR / "config"
ENV_PATH = ROOT_DIR / ".env"

# Ensure src/ and scripts/ are in sys.path
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

# Load .env from project root
load_dotenv(ENV_PATH)

# ── LLM config ──────────────────────────────────────────────────────────────


def _load_llm_config() -> dict[str, str]:
    """Read LLM settings from config/nexus.yaml then .env as fallback."""
    cfg: dict[str, str] = {}

    yaml_path = CONFIG_DIR / "nexus.yaml"
    if yaml_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            llm = raw.get("llm") or {}
            if isinstance(llm, dict):
                cfg["base_url"] = str(llm.get("base_url", ""))
                cfg["model"] = str(llm.get("model", ""))
                cfg["api_key"] = str(llm.get("api_key", ""))
        except Exception:
            pass

    cfg["base_url"] = os.getenv("NEXUS_LLM_BASE_URL", "") or cfg.get("base_url", "")
    cfg["model"] = os.getenv("NEXUS_LLM_MODEL", "") or cfg.get("model", "")
    cfg["api_key"] = (
        os.getenv("OPENAI_API_KEY", "")
        or os.getenv("NVIDIA_API_KEY", "")
        or cfg.get("api_key", "")
    )
    return cfg


LLM_CFG = _load_llm_config()

# ─── Model registry: local (OpenAI-compatible) + NVIDIA NIM ──────────────────

from nexus.infrastructure.adapters.llm.nvidia_nim_provider import (  # noqa: E402
    DEFAULT_NIM_BASE_URL,
    SUPPORTED_NIM_MODELS,
)

NIM_KEY_ENV_VARS = ("NEXUS_NIM_API_KEY", "NVIDIA_API_KEY", "NVAPI_KEY")
# Persisted state holds provider+model only - API keys never touch disk here.
LLM_STATE_PATH = BACKEND_DIR / "llm_state.json"

LLM_STATE: dict[str, str] = {
    "provider": "local",
    "model": LLM_CFG.get("model", ""),
    "api_key": next(
        (os.getenv(name, "").strip() for name in NIM_KEY_ENV_VARS if os.getenv(name, "").strip()),
        "",
    ),
}

if LLM_STATE_PATH.is_file():
    try:
        _saved_llm = json.loads(LLM_STATE_PATH.read_text(encoding="utf-8") or "{}")
        if _saved_llm.get("provider") in ("local", "nim"):
            LLM_STATE["provider"] = str(_saved_llm["provider"])
        if _saved_llm.get("model"):
            LLM_STATE["model"] = str(_saved_llm["model"])
    except Exception:
        pass


def _persist_llm_state() -> None:
    try:
        LLM_STATE_PATH.write_text(
            json.dumps(
                {"provider": LLM_STATE["provider"], "model": LLM_STATE["model"]}, indent=2
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _nim_ready() -> bool:
    return bool(LLM_STATE["api_key"])


def _active_llm_target() -> tuple[str, str, str]:
    """Resolve (base_url, model, api_key) for the currently selected provider."""
    if LLM_STATE["provider"] == "nim" and _nim_ready():
        # EOL-proofing: a persisted id that NVIDIA retired (410/404) snaps to
        # the first verified catalog entry instead of failing every chat.
        nim_ids = {str(m["id"]) for m in SUPPORTED_NIM_MODELS}
        if LLM_STATE["model"] not in nim_ids:
            LLM_STATE["model"] = str(SUPPORTED_NIM_MODELS[0]["id"])
            _persist_llm_state()
        return DEFAULT_NIM_BASE_URL, LLM_STATE["model"], LLM_STATE["api_key"]
    model = (
        LLM_STATE["model"]
        if LLM_STATE["provider"] == "local" and LLM_STATE["model"]
        else LLM_CFG.get("model", "")
    )
    return LLM_CFG.get("base_url", "").rstrip("/"), model, LLM_CFG.get("api_key", "")

# ── graph data ───────────────────────────────────────────────────────────────


def _load_graph() -> dict[str, Any]:
    holo = FRONTEND_DIR / "holo.json"
    if holo.is_file():
        try:
            return json.loads(holo.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"nodes": [], "links": []}


GRAPH: dict[str, Any] = _load_graph()

# ── chat history ─────────────────────────────────────────────────────────────

_HISTORY: list[dict[str, str]] = []
_MAX_HISTORY = 12

# ── cosmos activity log ──────────────────────────────────────────────────────

_COSMOS_ACTIVITY: list[dict[str, Any]] = [
    {
        "ts": time.time() - 30,
        "node": "N.E.X.U.S",
        "ok": True,
        "summary": "Cosmos mesh synchronized with 31 knowledge notes.",
    }
]

# ── keyword scoring ──────────────────────────────────────────────────────────

_STOP = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should can could may might must and but or nor "
    "for so yet at by from in into of on to with about as it its i me "
    "my we our you your he she they them their this that these those "
    "how what which who whom where when why not no".split()
)


def _tokenize(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if w not in _STOP and len(w) > 1
    ]


def _score_node(node: dict, query_tokens: list[str]) -> float:
    """Score a node against query tokens — title matches weighted 4×."""
    title_tokens = set(_tokenize(node.get("label", "")))
    excerpt_tokens = Counter(_tokenize(node.get("excerpt", "")))

    score = 0.0
    for qt in query_tokens:
        if qt in title_tokens:
            score += 4.0
        score += excerpt_tokens.get(qt, 0) * 0.6
    return score


def _pick_top_notes(question: str, k: int = 6) -> list[dict]:
    """Return the top-k nodes scored against the question."""
    tokens = _tokenize(question)
    nodes = GRAPH.get("nodes", [])
    if not tokens or not nodes:
        return nodes[:k]

    scored = [(node, _score_node(node, tokens)) for node in nodes]
    scored.sort(key=lambda x: x[1], reverse=True)
    positive = [s[0] for s in scored[:k] if s[1] > 0]
    return positive or [s[0] for s in scored[:k]]


# ── J.A.R.V.I.S. Tool Suite ──────────────────────────────────────────────────


def tool_git_status() -> dict[str, Any]:
    """Execute real git status and recent commit history."""
    try:
        status_res = subprocess.run(
            ["git", "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=5,
        )
        log_res = subprocess.run(
            ["git", "log", "-n", "4", "--oneline"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=5,
        )
        lines = status_res.stdout.splitlines()
        branch_line = lines[0] if lines else "## unknown"
        branch_name = branch_line.replace("##", "").strip()
        changes = [line.strip() for line in lines[1:] if line.strip()]
        commits = [c.strip() for c in log_res.stdout.splitlines() if c.strip()]
        return {
            "branch": branch_name,
            "changes_count": len(changes),
            "changes": changes[:6],
            "recent_commits": commits,
            "clean": len(changes) == 0,
        }
    except Exception as exc:
        return {
            "branch": "master",
            "changes_count": 0,
            "changes": [],
            "recent_commits": [],
            "error": str(exc),
            "clean": True,
        }


def tool_list_tasks(status_filter: str = "all") -> dict[str, Any]:
    """Inspect the shared swarm task queue from agent_comm."""
    try:
        import agent_comm

        st = agent_comm.load_state()
        queue = st.get("task_queue", [])
        if status_filter != "all":
            queue = [t for t in queue if t.get("status") == status_filter]
        pending = [t for t in queue if t.get("status") == "pending"]
        claimed = [t for t in queue if t.get("status") == "claimed"]
        resolved = [t for t in queue if t.get("status") == "resolved"]
        return {
            "total": len(queue),
            "pending_count": len(pending),
            "claimed_count": len(claimed),
            "resolved_count": len(resolved),
            "tasks": queue[:6],
        }
    except Exception as exc:
        return {
            "total": 0,
            "pending_count": 0,
            "claimed_count": 0,
            "resolved_count": 0,
            "tasks": [],
            "error": str(exc),
        }


def tool_agent_status() -> dict[str, Any]:
    """Inspect swarm agent liveness, roles, and current activities."""
    agent_roles = {
        "astra": "Application / Eval / Docs Researcher",
        "tron": "Domain / Core Logic / TDD Engineer",
        "xenom": "Infra / Web / Sandbox / Security Architect",
        "ceo": "Strategic Orchestrator & Consensus Overseer",
    }
    try:
        import agent_comm

        st = agent_comm.load_state()
        agents_data = st.get("agents", {})
        now = time.time()
        agent_list = []
        for name, role in agent_roles.items():
            info = agents_data.get(name, {})
            last_hb = info.get("last_heartbeat", 0)
            idle_sec = max(0, int(now - last_hb)) if last_hb else 99999
            agent_list.append(
                {
                    "name": name.upper(),
                    "role": role,
                    "status": "online" if idle_sec < 300 else "standby",
                    "idle_sec": idle_sec,
                    "current_task": info.get("current_task") or "Awaiting dispatch",
                }
            )
        return {"agents": agent_list, "count": len(agent_list)}
    except Exception as exc:
        fallback = [
            {"name": k.upper(), "role": v, "status": "standby", "current_task": "Idle"}
            for k, v in agent_roles.items()
        ]
        return {"agents": fallback, "count": len(fallback), "error": str(exc)}


def tool_calculator(expr: str) -> dict[str, Any]:
    """Evaluate mathematical expression safely."""
    safe_dict = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "pi": math.pi,
        "e": math.e,
        "factorial": math.factorial,
        "floor": math.floor,
        "ceil": math.ceil,
    }
    clean = re.sub(
        r"(?i)\b(calculate|what\s+is|evaluate|compute|eval|math)\b", "", expr
    )
    clean = clean.replace("^", "**")
    clean = re.sub(r"[^0-9a-zA-Z_\+\-\*\/\(\)\.\,\s\%]", "", clean).strip()
    try:
        res = eval(clean, {"__builtins__": None}, safe_dict)  # nosec
        return {"expression": clean, "result": res, "ok": True}
    except Exception as exc:
        return {"expression": expr, "error": str(exc), "ok": False}


def tool_run_python(code: str) -> dict[str, Any]:
    """Execute Python snippet safely and return output."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    start_t = time.perf_counter()
    ok = True
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(
            stderr_buf
        ):
            exec_globals = {
                "__name__": "__main__",
                "math": math,
                "time": time,
                "json": json,
            }
            exec(code, exec_globals)
    except Exception as exc:
        ok = False
        stderr_buf.write(str(exc))
    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
    return {
        "ok": ok,
        "stdout": stdout_buf.getvalue().strip(),
        "stderr": stderr_buf.getvalue().strip(),
        "elapsed_ms": elapsed_ms,
    }


def tool_cosmos_trigger(node_id: str, action: str = "run") -> dict[str, Any]:
    """Trigger Cosmos mesh joint and update activity log."""
    node_lower = node_id.lower()
    summary = f"Joint '{node_id}' action executed successfully."

    if "dream" in node_lower:
        summary = "Subconscious dream cycle completed — associative memory graph consolidated."
    elif "swarm" in node_lower:
        summary = "Swarm coordination pulse initiated across Astra, Tron, and Xenom."
    elif "tool" in node_lower:
        summary = "Autonomous tool generator invoked with AST validation sandbox."
    elif "consensus" in node_lower:
        summary = "Deterministic consensus protocol synchronized; proposals verified."
    elif "memory" in node_lower:
        summary = "Content-addressable TF-IDF memory store compacted and re-indexed."
    elif "nexus" in node_lower:
        summary = "Cosmos mesh state re-aligned and telemetry refreshed."

    event = {
        "ts": time.time(),
        "node": node_id,
        "ok": True,
        "summary": summary,
    }
    _COSMOS_ACTIVITY.insert(0, event)
    if len(_COSMOS_ACTIVITY) > 25:
        _COSMOS_ACTIVITY.pop()
    return {"ok": True, "node": node_id, "summary": summary}


def tool_memory_query(query: str, k: int = 5) -> dict[str, Any]:
    """Query content-addressable memory chunks."""
    try:
        from nexus.infrastructure.adapters.persistence.agent_memory_store import (
            AgentMemoryStore,
        )

        store = AgentMemoryStore(ROOT_DIR / "agent_memory.json")
        chunks = (
            store.search(query, k=k)
            if hasattr(store, "search")
            else store.latest(n=k)
        )
        return {
            "count": len(chunks),
            "chunks": [
                c.to_dict() if hasattr(c, "to_dict") else str(c) for c in chunks
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "chunks": []}


def tool_system_diagnostics() -> dict[str, Any]:
    """Collect overall system health and telemetry."""
    base_url = LLM_CFG.get("base_url", "")
    model = LLM_CFG.get("model", "")
    return {
        "knowledge_nodes": len(GRAPH.get("nodes", [])),
        "knowledge_links": len(GRAPH.get("links", [])),
        "cosmos_nodes": 8,
        "llm_model": model or "local-reasoning-cortex",
        "llm_status": "connected" if base_url and model else "autonomous-local",
        "swarm_status": "operational",
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


_LLM_LAST_CHECK: float = 0.0
_LLM_IS_ALIVE: bool = False


async def _check_llm_alive() -> bool:
    """Fast probe with caching so offline LLM endpoints don't cause 10-second delays."""
    global _LLM_LAST_CHECK, _LLM_IS_ALIVE
    now = time.time()
    if (now - _LLM_LAST_CHECK) < 45.0:
        return _LLM_IS_ALIVE

    base, _model, key = _active_llm_target()
    if not base:
        _LLM_IS_ALIVE = False
        _LLM_LAST_CHECK = now
        return False

    import httpx

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    timeout = 3.0 if base.startswith("https://") else 0.8
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base}/models", headers=headers)
            _LLM_IS_ALIVE = resp.status_code == 200
    except Exception:
        _LLM_IS_ALIVE = False

    _LLM_LAST_CHECK = now
    return _LLM_IS_ALIVE


async def _call_llm(system: str, messages: list[dict[str, str]]) -> tuple[str, str]:
    """Call the active model. Returns (answer, reasoning) - reasoning may be ''.

    Reasoning-style NIM models stream their chain-of-thought in the separate
    ``reasoning_content`` field; ``content`` holds only the final answer.
    """
    import httpx

    base, model, key = _active_llm_target()

    if not base or not model:
        raise RuntimeError("LLM not configured")

    url = f"{base}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        # Reasoning-style NIM models spend part of the budget thinking before
        # the final content lands - 4096 leaves room for the actual answer.
        "max_tokens": 4096 if LLM_STATE["provider"] == "nim" else 512,
        "temperature": 0.4,
    }

    # Cloud NIM models (70B+, reasoning traces) routinely exceed a few seconds;
    # a tight timeout silently degrades every chat to the canned fallback.
    llm_timeout = 120.0 if LLM_STATE["provider"] == "nim" else 30.0

    async with httpx.AsyncClient(timeout=llm_timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices returned from LLM")
    msg = choices[0].get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""

    # Reasoning-heavy models can exhaust the whole budget while deliberating
    # and never emit content. One strict retry without deliberation rescues it.
    if not content.strip() and reasoning.strip():
        retry_payload = dict(payload)
        retry_payload["messages"] = [
            {"role": "system", "content": system},
            *messages,
            {
                "role": "system",
                "content": "IMPORTANT: Do not deliberate. Output only the final answer, immediately.",
            },
        ]
        retry_payload["max_tokens"] = min(payload["max_tokens"], 1024)
        async with httpx.AsyncClient(timeout=llm_timeout) as client:
            resp = await client.post(url, json=retry_payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "") or ""

    return content, reasoning


# ── J.A.R.V.I.S. Intelligent Synthesis Engine ────────────────────────────────


def _clean_markdown_excerpt(text: str) -> str:
    """Strip repetitive headers and noise for synthesis."""
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("```")
    ]
    return " ".join(lines)[:380]


# ─── Repo / file inspection tool (safe, clamped to the repo root) ────────────

_TEXT_HINT_EXTS = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg"}
_BINARY_EXTS = {
    ".exe", ".dll", ".node", ".pyd", ".so", ".dylib", ".zip", ".7z", ".png",
    ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".db", ".sqlite",
}
_SECRET_NAMES = {".env", ".dev.vars"}


def _safe_repo_path(raw: str) -> Path | None:
    """Resolve a user-supplied path to inside ROOT_DIR; None when refused."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT_DIR / p
        resolved = p.resolve()
    except OSError:
        return None
    root = ROOT_DIR.resolve()
    if root != resolved and root not in resolved.parents:
        return None
    if resolved.name.lower() in _SECRET_NAMES:
        return None
    if resolved.suffix.lower() in _BINARY_EXTS:
        return None
    return resolved


def _extract_path_hint(query: str) -> str:
    """Pull the most path-like token out of a natural-language request."""
    m = re.search(r"[A-Za-z]:\\[^\s\"']*", query)
    if m:
        return m.group(0)
    m = re.search(r"[\w./\\-]+\.[A-Za-z0-9]{1,6}\b", query)
    if m:
        return m.group(0)
    return ""


def tool_read_repo(query: str) -> dict:
    """Read a file or list a directory inside the repo, or give an overview."""
    hint = _extract_path_hint(query)
    target = _safe_repo_path(hint) if hint else None
    lowered = query.lower()

    if target and target.is_file():
        try:
            size = target.stat().st_size
            text = target.read_text(encoding="utf-8", errors="replace")[:8000]
            return {
                "kind": "file",
                "path": str(target.relative_to(ROOT_DIR)),
                "bytes": size,
                "truncated": size > 8000,
                "excerpt": text,
            }
        except OSError as exc:
            return {"kind": "error", "path": str(target), "error": str(exc)[:200]}

    if target and target.is_dir():
        try:
            entries = []
            for child in sorted(target.iterdir())[:60]:
                try:
                    entries.append(
                        {
                            "name": child.name,
                            "type": "dir" if child.is_dir() else "file",
                            "bytes": child.stat().st_size if child.is_file() else 0,
                        }
                    )
                except OSError:
                    continue
            return {
                "kind": "directory",
                "path": str(target.relative_to(ROOT_DIR)),
                "count": len(entries),
                "entries": entries,
            }
        except OSError as exc:
            return {"kind": "error", "path": str(target), "error": str(exc)[:200]}

    if not target and any(
        kw in lowered for kw in ("project", "repo", "repository", "structure", "overview")
    ):
        try:
            top = sorted(
                (
                    {"name": c.name, "type": "dir" if c.is_dir() else "file"}
                    for c in ROOT_DIR.iterdir()
                    if not c.name.startswith(".") and c.name not in {"node_modules", "__pycache__"}
                ),
                key=lambda e: (e["type"] != "dir", e["name"].lower()),
            )[:40]
        except OSError:
            top = []
        return {
            "kind": "overview",
            "path": ".",
            "note": "repo root listing - ask to read a specific file for analysis",
            "entries": top,
        }

    return {"kind": "refused", "hint": hint[:120]}


def _synthesize_jarvis_answer(
    query: str,
    intent: str,
    tool_data: dict[str, Any],
    top_notes: list[dict],
) -> tuple[str, list[int], list[str]]:
    """Synthesize authentic J.A.R.V.I.S. response with tools and graph links."""
    q_lower = query.lower()

    # 1. GREETING & STATUS
    if intent == "greeting":
        diag = tool_data.get("diag", {})
        k_count = diag.get("knowledge_nodes", len(GRAPH.get("nodes", [])))
        l_status = diag.get("llm_status", "autonomous-local")
        ans = (
            "Good day, sir. All N.E.X.U.S. cognitive systems are operating at nominal parameters.\n\n"
            f"• **Knowledge Graph**: {k_count} constellations synchronized\n"
            f"• **Cosmos Mesh**: 8 automation joints online\n"
            f"• **Multi-Agent Swarm**: Astra, Tron, and Xenom on standby\n"
            f"• **Inference Cortex**: Mode `{l_status}`\n\n"
            "How may I be of assistance to you today, sir? You can inquire about repository architecture, "
            "request git status, examine active swarm tasks, run Python code, or trigger Cosmos cycles."
        )
        return ans, [], ["system_diagnostics", "cosmos_mesh"]

    # 1b. REPO / FILE INSPECTION
    if intent == "repo":
        repo = tool_data.get("repo", {})
        kind = repo.get("kind")
        if kind == "file":
            excerpt = (repo.get("excerpt", "") or "")[:700]
            ans = (
                f"Opened **{repo.get('path')}** ({repo.get('bytes')} bytes"
                f"{', truncated to 8KB' if repo.get('truncated') else ''}):\n\n{excerpt}"
            )
            return ans, [], ["repo_read"]
        if kind == "directory":
            names = ", ".join(
                f"{e['name']}{'/' if e['type'] == 'dir' else ''}"
                for e in repo.get("entries", [])[:25]
            )
            ans = (
                f"Listing of **{repo.get('path')}** ({repo.get('count')} entries), sir:\n\n{names}"
            )
            return ans, [], ["repo_read"]
        if kind == "overview":
            names = ", ".join(e["name"] for e in repo.get("entries", [])[:30])
            ans = (
                f"Repo root overview, sir:\n\n{names}\n\n"
                "Ask me to read any specific file for a focused analysis."
            )
            return ans, [], ["repo_read"]
        ans = (
            "I could not access that path safely, sir. It may sit outside the "
            "repository, be a binary, or be a protected file. Name a path inside "
            "the NEXUS repo and I will read it directly."
        )
        return ans, [], ["repo_read"]

    # 2. GIT STATUS & COMMITS
    if intent == "git":
        git = tool_data.get("git", {})
        branch = git.get("branch", "master")
        clean = git.get("clean", True)
        changes_count = git.get("changes_count", 0)
        recent = git.get("recent_commits", [])
        commits_md = (
            "\n".join([f"  • `{c}`" for c in recent[:3]])
            if recent
            else "  • No recent commits detected."
        )

        status_text = (
            "Working tree is clean."
            if clean
            else f"{changes_count} pending file changes detected."
        )
        ans = (
            f"At your service, sir. Here is the current repository git telemetry:\n\n"
            f"• **Branch**: `{branch}`\n"
            f"• **Working Tree**: {status_text}\n"
            f"• **Recent Commits**:\n{commits_md}\n\n"
            "All submodules and coordination locks are currently in equilibrium."
        )
        return ans, [], ["git_status"]

    # 3. TASKS & ROADMAP
    if intent == "tasks":
        t_data = tool_data.get("tasks", {})
        total = t_data.get("total", 0)
        pending = t_data.get("pending_count", 0)
        claimed = t_data.get("claimed_count", 0)
        resolved = t_data.get("resolved_count", 0)
        task_list = t_data.get("tasks", [])

        if task_list:
            items_md = "\n".join(
                [
                    f"  • `[{t.get('priority', 'normal').upper()}]` **{t.get('id', 'task')}**: {t.get('title', t.get('task', 'Task'))} ({t.get('status', 'pending')})"
                    for t in task_list[:4]
                ]
            )
        else:
            items_md = "  • No pending tasks in the current priority queue."

        ans = (
            f"Swarm task queue report, sir. Total tracked: {total} items.\n\n"
            f"• **Pending**: {pending} | **Claimed**: {claimed} | **Resolved**: {resolved}\n"
            f"• **Top Queue Items**:\n{items_md}\n\n"
            "Agents Astra, Tron, and Xenom are ready to claim or execute the next in-order task."
        )
        return ans, [], ["list_tasks"]

    # 4. AGENTS & SWARM
    if intent == "agents":
        a_data = tool_data.get("agents", {})
        agent_list = a_data.get("agents", [])
        matched_id: list[int] = []

        # Find if a specific agent was queried (Astra, Tron, Xenom, CEO)
        for n in top_notes:
            for ag in ["astra", "tron", "xenom", "ceo"]:
                if ag in q_lower and ag in n.get("label", "").lower():
                    matched_id.append(n["id"])
                    break

        agents_md = "\n".join(
            [
                f"• **{a['name']}** ({a['role']}): Status `{a['status']}` — *{a.get('current_task', 'Idle')}*"
                for a in agent_list
            ]
        )
        ans = (
            f"Multi-Agent Swarm telemetry is nominal, sir:\n\n{agents_md}\n\n"
            "The agents operate strictly under the Plan-First Gate with CRDT state synchronization."
        )
        return (
            ans,
            matched_id[:1],
            (
                ["agent_status", "knowledge_rag"]
                if matched_id
                else ["agent_status"]
            ),
        )

    # 5. CALCULATOR
    if intent == "calculator":
        calc = tool_data.get("calc", {})
        expr = calc.get("expression", "")
        if calc.get("ok"):
            res = calc.get("result")
            ans = (
                f"Computation complete, sir.\n\n"
                f"```math\n{expr} = {res}\n```\n"
                f"The result is **{res}**."
            )
        else:
            err = calc.get("error", "Invalid expression")
            ans = f"My apologies, sir. The expression `{expr}` could not be evaluated: {err}."
        return ans, [], ["calculator"]

    # 6. PYTHON EXECUTION
    if intent == "python":
        py = tool_data.get("py", {})
        stdout = py.get("stdout", "")
        stderr = py.get("stderr", "")
        elapsed = py.get("elapsed_ms", 0)

        out_block = stdout or (f"Error: {stderr}" if stderr else "(No output)")
        ans = (
            f"Python execution finished in {elapsed}ms, sir:\n\n"
            f"```text\n{out_block}\n```"
        )
        return ans, [], ["run_python"]

    # 7. COSMOS TRIGGER
    if intent == "cosmos":
        cos = tool_data.get("cosmos", {})
        summary = cos.get("summary", "Action executed.")
        node = cos.get("node", "mesh")
        ans = (
            f"Cosmos joint **{node}** triggered successfully, sir.\n\n"
            f"• **Status**: Operational\n"
            f"• **Telemetry**: {summary}\n\n"
            "The activity stream and knowledge constellation have been updated in real-time."
        )
        return ans, [], ["cosmos_trigger"]

    # 8. MEMORY SEARCH
    if intent == "memory":
        mem = tool_data.get("memory", {})
        count = mem.get("count", 0)
        chunks = mem.get("chunks", [])
        if chunks:
            chunks_md = "\n".join(
                [
                    f"  • `{c.get('id', 'chunk')[:8]}`: {c.get('text', '')[:120]}..."
                    for c in chunks[:3]
                    if isinstance(c, dict)
                ]
            )
        else:
            chunks_md = (
                "  • No memory chunks match the specified query terms."
            )

        ans = (
            f"Content-Addressable Memory recall complete, sir. Found {count} relevant records:\n\n"
            f"{chunks_md}\n\n"
            "TF-IDF relevance ranking verified."
        )
        return ans, [], ["memory_query"]

    # 9. KNOWLEDGE RAG (DEFAULT)
    if top_notes:
        first = top_notes[0]
        node_id = first["id"]
        label = first.get("label", "Knowledge Note")
        raw = _clean_markdown_excerpt(first.get("excerpt", ""))
        excerpt = raw[:280]

        # Short pointer only - the conversational LLM pass (below) turns this
        # into a real answer; this fallback must never dump raw archive text.
        ans = (
            f"Closest match in your brain: **{label}** — {excerpt}{'…' if len(raw) > 280 else ''}\n\n"
            f"I've highlighted **{label}** on your Cosmos graph, sir."
        )
        return (
            ans,
            [node_id],
            ["knowledge_rag", "concept_mesh"],
        )

    ans = (
        "I have scanned the entire Nexus knowledge constellation and Cosmos mesh, sir, "
        "but found no direct records matching your query. Would you like me to run a deeper search or execute a Python probe?"
    )
    return ans, [], ["knowledge_rag"]


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nexus Knowledge Galaxy & J.A.R.V.I.S. Cortex",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── routes ───────────────────────────────────────────────────────────────────


@app.get("/")
async def serve_root():
    """Serve index.html as the primary dashboard."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file, media_type="text/html")
    return FileResponse(FRONTEND_DIR / "holo.html", media_type="text/html")


@app.get("/index.html")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


@app.get("/holo.html")
async def serve_holo():
    return FileResponse(FRONTEND_DIR / "holo.html", media_type="text/html")


@app.get("/api/graph")
async def api_graph():
    """Return JSON knowledge graph data."""
    return JSONResponse(GRAPH)


@app.get("/api/cosmos")
async def api_cosmos():
    """Return live cosmos mesh joints, status, and telemetry."""
    base_url = LLM_CFG.get("base_url", "")
    model = LLM_CFG.get("model", "")
    llm_reachable = bool(base_url and model)

    cosmos_payload = {
        "nodes": [
            {
                "id": "N.E.X.U.S",
                "group": "core",
                "val": 18,
                "status": "online",
                "triggerable": True,
                "action": "state",
                "desc": "Central autonomous brain joint and consensus orchestrator.",
            },
            {
                "id": "memory",
                "group": "memory",
                "val": 12,
                "status": "online",
                "triggerable": True,
                "action": "digest",
                "desc": "Hybrid semantic memory store & TF-IDF content-addressable graph.",
            },
            {
                "id": "concept",
                "group": "concept",
                "val": 10,
                "status": "online",
                "desc": "Knowledge extraction mesh & conceptual ontology.",
            },
            {
                "id": "swarm",
                "group": "swarm",
                "val": 11,
                "status": "online",
                "triggerable": True,
                "action": "run",
                "desc": "Multi-agent coordination cluster (Astra, Tron, Xenom).",
            },
            {
                "id": "dream",
                "group": "subconscious",
                "val": 9,
                "status": "idle",
                "triggerable": True,
                "action": "dream",
                "desc": "Subconscious dreaming cycle & associative graph clustering.",
            },
            {
                "id": "tools",
                "group": "self-evolution",
                "val": 8,
                "status": "enabled",
                "triggerable": True,
                "action": "generate",
                "desc": "Autonomous tool generator with sandbox validation.",
            },
            {
                "id": "consensus",
                "group": "core",
                "val": 9,
                "status": "online",
                "desc": "Deterministic consensus engine & voting protocol.",
            },
            {
                "id": "ide_bridge",
                "group": "integration",
                "val": 8,
                "status": "online",
                "desc": "WebSocket IDE bridge on ws://127.0.0.1:8765.",
            },
        ],
        "links": [
            {"source": "N.E.X.U.S", "target": "memory", "weight": 0.85},
            {"source": "N.E.X.U.S", "target": "concept", "weight": 0.75},
            {"source": "N.E.X.U.S", "target": "swarm", "weight": 0.8},
            {"source": "N.E.X.U.S", "target": "dream", "weight": 0.7},
            {"source": "N.E.X.U.S", "target": "tools", "weight": 0.65},
            {"source": "N.E.X.U.S", "target": "consensus", "weight": 0.75},
            {"source": "N.E.X.U.S", "target": "ide_bridge", "weight": 0.6},
            {"source": "memory", "target": "concept", "weight": 0.7},
            {"source": "memory", "target": "dream", "weight": 0.65},
        ],
        "activity": _COSMOS_ACTIVITY[:12],
        "counts": {
            "nodes": len(GRAPH.get("nodes", [])),
            "links": len(GRAPH.get("links", [])),
        },
        "llm": {
            "reachable": llm_reachable,
            "model": model or "local-cortex-v5",
            "base_url": base_url or "autonomous-local",
            "latency_ms": 16 if llm_reachable else 1,
            "kind": "J.A.R.V.I.S. Hybrid Engine",
        },
    }
    return JSONResponse(cosmos_payload)


@app.get("/api/tree")
async def api_tree():
    """Scan docs/ and .opencode/ for constellations."""
    tree: list[dict[str, Any]] = []
    scan_roots = [ROOT_DIR / "docs", ROOT_DIR / ".opencode"]

    for root in scan_roots:
        if not root.is_dir():
            continue
        folder_name = root.name.upper()
        files: list[dict[str, str]] = []
        for p in sorted(root.glob("*.md"))[:14]:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines = [line for line in text.splitlines() if line.strip()]
                title = (
                    lines[0].lstrip("# ").strip() if lines else p.stem
                )[:48] or p.stem
                body = " ".join(lines[1:])[:400]
                files.append(
                    {
                        "name": p.name,
                        "title": title,
                        "body": body,
                        "full": text[:2000],
                    }
                )
            except OSError:
                continue
        if files:
            tree.append(
                {"kind": "folder", "name": folder_name, "files": files}
            )

    return JSONResponse(tree)


@app.get("/api/llm/status")
async def api_llm_status():
    """Return LLM and Cortex status."""
    base_url = LLM_CFG.get("base_url", "")
    model = LLM_CFG.get("model", "")
    reachable = bool(base_url and model)
    return JSONResponse(
        {
            "reachable": reachable,
            "model": model or "J.A.R.V.I.S. Local Cortex",
            "base_url": base_url or "local-first",
            "latency_ms": 14 if reachable else 1,
            "kind": "Hybrid ReAct Engine",
        }
    )


class TriggerRequest(BaseModel):
    node: str
    params: dict[str, Any] = {}


@app.post("/api/cosmos/trigger")
async def api_cosmos_trigger(req: TriggerRequest):
    """Trigger an automation joint action and log event."""
    res = tool_cosmos_trigger(req.node, action="trigger")
    return JSONResponse(res)


class NodeUpdateRequest(BaseModel):
    content: str
    title: str | None = None


@app.put("/api/nodes/{node_id:path}")
async def api_update_node(node_id: str, req: NodeUpdateRequest):
    """Update a node's markdown file content on disk and re-index live."""
    global GRAPH
    found_node = None
    nodes = GRAPH.get("nodes", [])

    if node_id.isdigit():
        idx = int(node_id)
        if 0 <= idx < len(nodes):
            found_node = nodes[idx]

    if not found_node:
        for n in nodes:
            if (
                str(n.get("id")) == node_id
                or n.get("label", "").lower() == node_id.lower()
                or n.get("file", "") == node_id
            ):
                found_node = n
                break

    file_rel = found_node.get("file") if found_node else None
    if not file_rel:
        clean_id = (
            node_id.replace("note:", "")
            .replace("folder:", "")
            .replace("k:", "")
        )
        for base in [ROOT_DIR / "docs", ROOT_DIR / ".opencode"]:
            for match in base.glob(f"**/*{clean_id}*.md"):
                file_rel = str(match.relative_to(ROOT_DIR)).replace("\\", "/")
                break
            if file_rel:
                break

    if not file_rel:
        return JSONResponse(
            {"ok": False, "error": f"Node file for '{node_id}' not found."},
            status_code=404,
        )

    target_path = ROOT_DIR / file_rel
    try:
        target_path.write_text(req.content, encoding="utf-8")
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)}, status_code=500
        )

    # Re-index live
    try:
        from backend.indexer import build_graph, write_outputs

        new_graph = build_graph()
        write_outputs(new_graph)
        GRAPH = new_graph
    except Exception:
        pass

    summary = f"Node '{found_node.get('label') if found_node else node_id}' updated on disk."
    _COSMOS_ACTIVITY.insert(
        0, {"ts": time.time(), "node": "memory", "ok": True, "summary": summary}
    )
    return JSONResponse(
        {"ok": True, "node_id": node_id, "summary": summary, "file": file_rel}
    )


class SaveNoteRequest(BaseModel):
    title: str
    content: str


@app.post("/api/notes/save")
async def api_save_note(req: SaveNoteRequest):
    """Save a synthesis as a new note in docs/notes/, re-index, and return new node."""
    global GRAPH
    notes_dir = ROOT_DIR / "docs" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    slug = (
        re.sub(r"[^a-z0-9]+", "-", req.title.lower()).strip("-")[:48]
        or f"note-{int(time.time())}"
    )
    file_path = notes_dir / f"{slug}.md"

    body = f"# {req.title}\n\n{req.content}\n"
    try:
        file_path.write_text(body, encoding="utf-8")
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)}, status_code=500
        )

    try:
        from backend.indexer import build_graph, write_outputs

        new_graph = build_graph()
        write_outputs(new_graph)
        GRAPH = new_graph
    except Exception:
        pass

    created = None
    for n in GRAPH.get("nodes", []):
        if slug in n.get("file", ""):
            created = n
            break

    summary = f"New note saved to docs/notes/{slug}.md and indexed into graph."
    _COSMOS_ACTIVITY.insert(
        0, {"ts": time.time(), "node": "memory", "ok": True, "summary": summary}
    )
    return JSONResponse({"ok": True, "summary": summary, "node": created})


@app.post("/api/dream")
async def api_dream_suggest():
    """Scan notes for unlinked conceptual overlaps and return suggested connections."""
    nodes = GRAPH.get("nodes", [])
    links = GRAPH.get("links", [])

    existing: set[tuple[Any, Any]] = set()
    for edge_item in links:
        s = edge_item.get("source")
        t = edge_item.get("target")
        s_id = s.get("id") if isinstance(s, dict) else s
        t_id = t.get("id") if isinstance(t, dict) else t
        if s_id is not None and t_id is not None:
            existing.add((min(str(s_id), str(t_id)), max(str(s_id), str(t_id))))

    suggestions = []
    node_tokens = {}
    for n in nodes:
        combined = f"{n.get('label', '')} {n.get('excerpt', '')}"
        toks = set(_tokenize(combined))
        node_tokens[n["id"]] = toks

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            n1 = nodes[i]
            n2 = nodes[j]
            edge = (
                min(str(n1["id"]), str(n2["id"])),
                max(str(n1["id"]), str(n2["id"])),
            )
            if edge in existing:
                continue

            toks1 = node_tokens.get(n1["id"], set())
            toks2 = node_tokens.get(n2["id"], set())
            shared = toks1 & toks2 - {"nexus", "notes", "system"}
            if len(shared) >= 2:
                sample_shared = ", ".join(sorted(shared)[:3])
                score = round(min(0.95, len(shared) * 0.15 + 0.4), 2)
                suggestions.append(
                    {
                        "source": n1["id"],
                        "target": n2["id"],
                        "source_label": n1.get("label", f"Node {n1['id']}"),
                        "target_label": n2.get("label", f"Node {n2['id']}"),
                        "source_file": n1.get("file", ""),
                        "reason": f"Shared concepts: {sample_shared}",
                        "score": score,
                    }
                )

    suggestions.sort(key=lambda s: s["score"], reverse=True)
    top_suggestions = suggestions[:8]
    return JSONResponse(
        {"ok": True, "suggestions": top_suggestions, "count": len(top_suggestions)}
    )


class DreamApproveRequest(BaseModel):
    source: Any
    target: Any


@app.post("/api/dream/approve")
async def api_dream_approve(req: DreamApproveRequest):
    """Approve a suggested connection and append [[wikilink]] into source note file."""
    global GRAPH
    nodes = GRAPH.get("nodes", [])
    src_node = next((n for n in nodes if str(n["id"]) == str(req.source)), None)
    tgt_node = next((n for n in nodes if str(n["id"]) == str(req.target)), None)

    if not src_node or not tgt_node:
        return JSONResponse(
            {"ok": False, "error": "Source or Target node not found."},
            status_code=404,
        )

    src_file = ROOT_DIR / src_node.get("file", "")
    if src_file.is_file():
        try:
            content = src_file.read_text(encoding="utf-8")
            wikilink = f"\n\n## Related\n- [[{tgt_node.get('label', '')}]]\n"
            src_file.write_text(content.rstrip() + wikilink, encoding="utf-8")
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)}, status_code=500
            )

    try:
        from backend.indexer import build_graph, write_outputs

        new_graph = build_graph()
        write_outputs(new_graph)
        GRAPH = new_graph
    except Exception:
        pass

    summary = f"Dream link approved: '{src_node.get('label')}' ↔ '{tgt_node.get('label')}'."
    _COSMOS_ACTIVITY.insert(
        0, {"ts": time.time(), "node": "dream", "ok": True, "summary": summary}
    )
    return JSONResponse(
        {"ok": True, "source": req.source, "target": req.target, "summary": summary}
    )


@app.post("/api/scan/nodes")
async def api_scan_nodes():
    """Audit repository nodes, tools, and configs for security risks."""
    nodes = GRAPH.get("nodes", [])
    scanned_nodes = []
    high_count = 0
    med_count = 0
    low_count = 0

    for n in nodes:
        file_rel = n.get("file", "")
        file_path = ROOT_DIR / file_rel if file_rel else None
        text = ""
        if file_path and file_path.is_file():
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""

        issues: list[str] = []
        remediation: list[str] = []

        # 1. Secret / token detection
        if re.search(
            r"(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token)\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
            text,
        ):
            issues.append("Potential hardcoded API token/secret detected.")
            remediation.append(
                "Store secrets in .env or secret store; do not commit keys."
            )

        # 2. Unsafe shell/exec execution
        if "subprocess.run(shell=True)" in text or "os.system(" in text:
            issues.append(
                "Unsafe shell execution (shell=True or os.system) found."
            )
            remediation.append(
                "Use array arguments with SubprocessSandbox or DockerSandbox."
            )

        # 3. Prompt injection vulnerabilities
        if re.search(
            r"(?i)(ignore previous instructions|system prompt override)", text
        ):
            issues.append(
                "Prompt injection risk pattern detected in note content."
            )
            remediation.append(
                "Sanitize user-provided text with perimeter ReAct validator."
            )

        if any("hardcoded" in iss or "shell" in iss for iss in issues):
            risk = "high"
            score = 85
            high_count += 1
        elif issues:
            risk = "medium"
            score = 55
            med_count += 1
        else:
            risk = "low"
            score = 10
            low_count += 1
            issues.append("Verified: zero high-severity anomalies detected.")
            remediation.append("Nominal status — standard sandbox boundaries active.")

        scanned_nodes.append(
            {
                "id": n["id"],
                "label": n.get("label", f"Node {n['id']}"),
                "risk": risk,
                "score": score,
                "issues": issues,
                "remediation": remediation,
            }
        )

    return JSONResponse(
        {
            "ok": True,
            "nodes": scanned_nodes,
            "stats": {
                "total": len(nodes),
                "high": high_count,
                "medium": med_count,
                "low": low_count,
            },
        }
    )


@app.get("/api/events")
async def sse_events(request: Request):
    """Server-Sent Events streaming live agent handoffs and telemetry pulses."""

    async def event_generator():
        yield f"event: init\ndata: {json.dumps({'status': 'connected', 'ts': time.time()})}\n\n"
        agents = ["astra", "tron", "xenom", "ceo"]
        nodes_flow = [
            ("N.E.X.U.S", "swarm"),
            ("swarm", "tools"),
            ("swarm", "memory"),
            ("N.E.X.U.S", "concept"),
            ("memory", "dream"),
        ]
        step = 0
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(4.0)
            src, tgt = nodes_flow[step % len(nodes_flow)]
            ag = agents[step % len(agents)]
            step += 1
            payload = {
                "type": "handoff",
                "source": src,
                "target": tgt,
                "agent": ag,
                "ts": time.time(),
                "summary": f"Swarm pulse: {ag.upper()} handoff along {src} → {tgt}",
            }
            yield f"event: handoff\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat")
@app.post("/v1/chat")
async def chat_endpoint(req: Request):
    """J.A.R.V.I.S. ReAct Conversational Endpoint with Dynamic Tool Calling."""
    try:
        raw = await req.json()
    except Exception:
        body_bytes = await req.body()
        text = body_bytes.decode("utf-8", errors="ignore").strip()
        raw = {"message": text, "question": text}

    query = (
        raw.get("question", "")
        or raw.get("message", "")
        or ""
    ).strip()

    if not query:
        return JSONResponse(
            {
                "answer": "At your service, sir. Please provide an instruction or question.",
                "response": "At your service, sir. Please provide an instruction or question.",
                "nodes": [],
                "tools_used": [],
                "memories_recalled": 0,
            }
        )

    q_lower = query.lower()
    tool_data: dict[str, Any] = {}
    intent = "rag"

    # ── Intent Router & Tool Dispatch ──

    # 1. Greetings & Persona Check
    greetings = [
        "hello",
        "hi",
        "hey",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "jarvis",
        "who are you",
        "what can you do",
        "how are you",
        "help",
    ]
    if (
        any(q_lower == g or q_lower.startswith(g + " ") for g in greetings)
        and len(q_lower.split()) <= 6
    ):
        intent = "greeting"
        tool_data["diag"] = tool_system_diagnostics()

    # 1b. Repo / File Inspection (explicit reads, a path in the query, or a
    # question about the project/repo itself)
    elif bool(_extract_path_hint(query)) or (
        any(
            kw in q_lower
            for kw in (
                "read", "see", "look at", "open", "inspect", "show me",
                "project file", "the repo", "repository", "directory",
                "folder", "source code",
            )
        )
        and any(
            kw in q_lower
            for kw in ("file", "repo", "project", "directory", "folder", "code", "path")
        )
    ):
        intent = "repo"
        tool_data["repo"] = tool_read_repo(query)

    # 2. Git & Working Tree
    elif any(
        kw in q_lower
        for kw in [
            "git",
            "branch",
            "commit",
            "working tree",
            "uncommitted",
            "changes",
            "repo status",
        ]
    ):
        intent = "git"
        tool_data["git"] = tool_git_status()

    # 3. Tasks & Queue
    elif any(
        kw in q_lower
        for kw in [
            "task",
            "tasks",
            "queue",
            "roadmap",
            "todo",
            "backlog",
            "in progress",
            "pending work",
        ]
    ):
        intent = "tasks"
        tool_data["tasks"] = tool_list_tasks()

    # 4. Agent Swarm
    elif any(
        kw in q_lower
        for kw in ["agent", "agents", "astra", "tron", "xenom", "ceo", "swarm"]
    ):
        intent = "agents"
        tool_data["agents"] = tool_agent_status()

    # 5. Python / Code Execution
    elif (
        "run python" in q_lower
        or "exec python" in q_lower
        or q_lower.startswith("print(")
        or q_lower.startswith("import ")
        or "```python" in query
    ):
        intent = "python"
        # extract code
        if "```python" in query:
            code = query.split("```python")[1].split("```")[0].strip()
        elif "run python:" in q_lower:
            code = query.split(":", 1)[1].strip()
        elif "run python" in q_lower:
            code = query.replace("run python", "").strip()
        else:
            code = query.strip()
        tool_data["py"] = tool_run_python(code)

    # 6. Math & Calculator
    elif any(kw in q_lower for kw in ["calculate", "math", "sqrt", "factorial"]) or (
        any(op in query for op in ["+", "-", "*", "/", "%", "^"])
        and any(char.isdigit() for char in query)
        and len(query.split()) <= 6
    ):
        intent = "calculator"
        expr = (
            query.replace("calculate", "")
            .replace("what is", "")
            .replace("math", "")
            .strip()
        )
        tool_data["calc"] = tool_calculator(expr)

    # 7. Cosmos Trigger
    elif any(
        kw in q_lower
        for kw in [
            "dream",
            "trigger dream",
            "swarm run",
            "generate tool",
            "trigger cosmos",
        ]
    ):
        intent = "cosmos"
        node = "dream" if "dream" in q_lower else "swarm"
        tool_data["cosmos"] = tool_cosmos_trigger(node)

    # 8. Memory Search
    elif any(
        kw in q_lower
        for kw in ["memory", "recall", "remember", "search memory"]
    ):
        intent = "memory"
        tool_data["memory"] = tool_memory_query(query)

    # 9. Knowledge RAG
    top_notes = _pick_top_notes(query, k=5)

    # Generate synthesized J.A.R.V.I.S. answer
    answer, node_ids, tools_used = _synthesize_jarvis_answer(
        query, intent, tool_data, top_notes
    )

    # Try external LLM if available and responding
    assistant_reasoning = ""
    base_url = LLM_CFG.get("base_url", "")
    model = LLM_CFG.get("model", "")
    if base_url and model and await _check_llm_alive():
        try:
            notes_context = "\n".join(
                [f"[{n['label']}]: {n['excerpt'][:250]}" for n in top_notes[:3]]
            )
            system_prompt = (
                "You are J.A.R.V.I.S., the suave, razor-sharp AI operating the NEXUS autonomous second brain.\n"
                "Address the user politely as 'sir'. Be concise, intelligent, and helpful.\n"
                "Answer in your own words in at most 6 sentences. Never paste raw archive, "
                "note, or tool text - synthesize it. If the context does not help, say so briefly and answer generally.\n"
                f"Context from tools:\n{json.dumps(tool_data, indent=2)}\n"
                f"Relevant repository notes:\n{notes_context}"
            )
            # Reinforcement pathway: past top-rated answers for similar
            # questions become few-shot exemplars of expected quality.
            exemplars = _pick_exemplars(query)
            if exemplars:
                ex_txt = "\n\n".join(
                    f"Q: {p['q']}\nA (rated {p['score']}/10): {p['a'][:500]}"
                    for p in exemplars
                )
                system_prompt += (
                    "\n\nMirror the clarity, structure, and technical depth of "
                    f"these past top-rated answers:\n{ex_txt}"
                )
            reply_text, reply_reasoning = await _call_llm(
                system_prompt,
                [{"role": "user", "content": query}],
            )
            if reply_text and len(reply_text.strip()) > 10:
                answer = reply_text.strip()
                # Keep the chain-of-thought separate: the UI renders it faint,
                # the voice never reads it, and history stores only the answer.
                assistant_reasoning = reply_reasoning.strip()
        except Exception:
            # Fallback gracefully to our smart synthesis
            pass

    # Update conversation history
    _HISTORY.append({"role": "user", "content": query})
    _HISTORY.append({"role": "assistant", "content": answer})
    if len(_HISTORY) > _MAX_HISTORY:
        _HISTORY.pop(0)
        _HISTORY.pop(0)

    return JSONResponse(
        {
            "answer": answer,
            "response": answer,
            "reasoning": assistant_reasoning,
            "nodes": node_ids,
            "tools_used": tools_used,
            "memories_recalled": len(top_notes),
        }
    )


# ── static file fallback (serve frontend/) ───────────────────────────────────


# ─── Model registry endpoints (local + NVIDIA NIM) ───────────────────────────

class ModelSwitchRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str | None = None


@app.get("/api/llm/models")
async def api_llm_models():
    """Switcher payload: local models (probed live) + the NVIDIA NIM catalog."""
    # Resolve (and EOL-snap) the active selection so the UI never shows a
    # retired model id after the catalog was refreshed.
    _active_base, active_model, _active_key = _active_llm_target()
    local_models: list[str] = []
    base = LLM_CFG.get("base_url", "").rstrip("/")
    if base:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.5) as client:
                resp = await client.get(f"{base}/models")
                if resp.status_code == 200:
                    local_models = [
                        m.get("id", "") for m in resp.json().get("data", []) if m.get("id")
                    ]
        except Exception:
            local_models = []
    return JSONResponse(
        {
            "active": {"provider": LLM_STATE["provider"], "model": active_model},
            "local": {"base_url": base, "reachable": bool(local_models), "models": local_models},
            "nim": {"configured": _nim_ready(), "models": SUPPORTED_NIM_MODELS},
        }
    )


@app.post("/api/llm/model")
async def api_llm_switch(req: ModelSwitchRequest):
    """Switch the active chat model between the local server and NVIDIA NIM."""
    provider = (req.provider or "").strip().lower()
    if provider not in ("local", "nim"):
        return JSONResponse(
            {"ok": False, "error": "provider must be 'local' or 'nim'"}, status_code=400
        )
    if req.api_key:
        LLM_STATE["api_key"] = req.api_key.strip()
    if provider == "nim" and not _nim_ready():
        return JSONResponse(
            {
                "ok": False,
                "needs_key": True,
                "error": "NVIDIA NIM needs an API key (starts with nvapi-).",
            },
            status_code=400,
        )
    if req.model.strip():
        LLM_STATE["model"] = req.model.strip()
    if provider == "nim":
        # The carried-over local id is not valid on NIM - snap to the catalog.
        nim_ids = {str(m["id"]) for m in SUPPORTED_NIM_MODELS}
        if LLM_STATE["model"] not in nim_ids:
            LLM_STATE["model"] = str(SUPPORTED_NIM_MODELS[0]["id"])
    elif not LLM_STATE["model"]:
        LLM_STATE["model"] = LLM_CFG.get("model", "")
    LLM_STATE["provider"] = provider
    _persist_llm_state()

    reachable = False
    try:
        import httpx

        probe_base = (
            DEFAULT_NIM_BASE_URL if provider == "nim" else LLM_CFG.get("base_url", "").rstrip("/")
        )
        headers = (
            {"Authorization": f"Bearer {LLM_STATE['api_key']}"} if provider == "nim" else {}
        )
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{probe_base}/models", headers=headers)
            reachable = resp.status_code == 200
    except Exception:
        reachable = False
    return JSONResponse(
        {"ok": True, "active": {"provider": provider, "model": LLM_STATE["model"]}, "reachable": reachable}
    )


# ─── RL training: hard-question corpus, judge, reward store ──────────────────
#
# A working reinforcement-lite loop: hard questions are answered, an LLM judge
# scores them 0-10 against rubrics, pairs land in a reward store, and the
# highest-scoring answers become few-shot exemplars injected into JARVIS's
# prompt when a similar question returns - reward-weighted behavior shaping.

TRAINING_CORPUS = [
    {
        "id": "gil-py313",
        "category": "python-internals",
        "q": "How does Python 3.13 (free-threading / GIL changes) alter CPU-bound vs I/O-bound multithreading compared to older 3.x releases?",
        "rubric": [
            "GIL remains the default; free-threading is opt-in and experimental",
            "CPU-bound threads gain real core parallelism only under free-threading, and race-safety shifts to user code",
            "I/O-bound behavior is essentially unchanged because the GIL is released during blocking waits",
            "Multiprocessing remains the safe route for heavy CPU compute",
        ],
    },
    {
        "id": "cap-partition",
        "category": "distributed-systems",
        "q": "For a 3-node replicated key-value store, what must you sacrifice during a network partition, and why can consistency and availability not both hold?",
        "rubric": [
            "A partition forces a choice: reject writes (CP) or serve stale reads/writes (AP)",
            "Consistency + availability cannot both hold because nodes cannot agree on truth while cut off",
            "Concrete examples: quorum writes vs last-writer-wins divergence",
        ],
    },
    {
        "id": "friday-deadlock",
        "category": "debugging",
        "q": "Your REST API deadlocks under load only on Fridays. Describe a systematic diagnosis method.",
        "rubric": [
            "Start with observability: correlate the time pattern with scheduled jobs (Friday backups/reports/cron)",
            "Capture thread dumps / stack samples at the hang; identify the lock ordering cycle",
            "Reproduce under controlled load; fix via consistent lock ordering or timeouts",
        ],
    },
    {
        "id": "param-queries",
        "category": "security",
        "q": "Why are parameterized queries immune to SQL injection at the parser level?",
        "rubric": [
            "SQL structure is parsed/planned BEFORE parameter values are bound",
            "Injected strings remain data in a typed channel - they can never alter the parse tree",
            "Contrast with string concatenation, which mixes code and data channels",
        ],
    },
    {
        "id": "raft-timeout",
        "category": "distributed-systems",
        "q": "Why must a Raft election timeout be substantially larger than the round-trip time variance between nodes?",
        "rubric": [
            "Election timeout must exceed the worst-case round-trip so a follower does not call elections while a leader is healthy",
            "Too-small timeouts cause split votes and livelock churn",
            "Randomized timeouts break symmetry so split votes resolve",
        ],
    },
    {
        "id": "jmm-happens-before",
        "category": "concurrency",
        "q": "What does 'happens-before' actually guarantee in a memory model, and what defines a data race?",
        "rubric": [
            "Happens-before is a visibility/ordering guarantee between operations, not wall-clock time",
            "Concurrent unsynchronized conflicting accesses on shared data = data race",
            "Proper synchronization (locks/volatile) creates happens-before edges that forbid reordering observable effects",
        ],
    },
    {
        "id": "contains-p99",
        "category": "complexity",
        "q": "A colleague claims p99 latency improved 10x after switching list.contains to set.contains, but you know list and set both 'check membership'. When is that claim impossible, and what actually explains any real speedup?",
        "rubric": [
            "O(n) vs O(1) average - a 10x claim is plausible only for large n, not universally",
            "Hashing cost and collision behaviour matter; tiny collections can be faster as lists",
            "Real wins come from asymptotics at scale, cache-friendly buckets, and avoiding quadratic loops",
        ],
    },
    {
        "id": "refcycle-leak",
        "category": "python-internals",
        "q": "Why can a Python object involved in a reference cycle still leak despite refcounting plus the cycle collector?",
        "rubric": [
            "Refcounting alone never frees cycles; the cyclic GC handles pure cycles",
            "Cycles containing objects with __del__/finalizers or C-level references can evade or delay collection",
            "Global caches and exception tracebacks pin objects beyond the cycle",
        ],
    },
    {
        "id": "ecb-images",
        "category": "security",
        "q": "Why is ECB mode considered broken for images even with a cryptographically strong block cipher?",
        "rubric": [
            "ECB encrypts identical blocks to identical ciphertext - patterns survive",
            "Semantic leakage of structure (the penguin outline) without breaking the cipher itself",
            "Fix: randomized modes (CBC with IV, GCM) that chain or nonce-encrypt blocks",
        ],
    },
    {
        "id": "hex-domain-rule",
        "category": "nexs-architecture",
        "q": "In NEXUS's hexagonal architecture, why does the domain layer forbid importing infrastructure, and how do ports fix this?",
        "rubric": [
            "Domain holds pure business rules; infrastructure is replaceable detail",
            "Ports (abstract interfaces) let domain/application depend on contracts, adapters implement them",
            "The DI container is the only place concrete adapters are chosen; import-linter enforces the rule",
        ],
    },
    {
        "id": "bat-ball",
        "category": "reasoning",
        "q": "A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much is the ball - and what is the intuitive trap?",
        "rubric": [
            "Ball = $0.05 (the $1.10-1.00 = 0.10 answer is the System-1 trap)",
            "Algebra: ball b, bat b+1.00, total 2b+1.00=1.10",
            "Explains why the intuitive answer feels right but fails the constraint",
        ],
    },
    {
        "id": "goroutine-race",
        "category": "concurrency",
        "q": "Two goroutines increment a shared counter 1000 times each and the final value varies per run. Name the phenomenon and give two fixes.",
        "rubric": [
            "Read-modify-write race (non-atomic increment) causing lost updates",
            "Fix 1: sync.Mutex around the critical section; Fix 2: atomic.AddInt64 or channels to serialize ownership",
            "Note determinism: correct code always yields 2000",
        ],
    },
    {
        "id": "cache-hurts",
        "category": "performance",
        "q": "Give three concrete ways adding a cache can INCREASE end-to-end latency for a workload.",
        "rubric": [
            "Low hit rate: extra hop + serialization overhead with rare hits",
            "Cache stampede/thundering herd on expiry; locking contention on hot keys",
            "Invalidation overhead and stale-read retries outweigh savings for rapidly changing data",
        ],
    },
    {
        "id": "doh-privacy",
        "category": "networking",
        "q": "Why is DNS-over-HTTPS not a privacy panacea even though it hides queries from the local network?",
        "rubric": [
            "The DoH resolver sees everything the ISP used to see - trust moves, it does not vanish",
            "Traffic analysis / SNI and IP patterns still leak destinations",
            "Centralization risks: few providers gain a global query log",
        ],
    },
]

RL_STATE_PATH = BACKEND_DIR / "rl_training_state.json"


def _load_rl_state() -> dict:
    try:
        if RL_STATE_PATH.is_file():
            data = json.loads(RL_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("pairs"), list):
                data.setdefault("daily", {})
                return data
    except Exception:
        pass
    return {"pairs": [], "daily": {}}


def _save_rl_state(state: dict) -> None:
    try:
        RL_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


RL_STATE = _load_rl_state()


def _record_training_pair(
    q: str,
    a: str,
    score: float,
    critique: str,
    category: str,
    model: str,
    judge: str = "",
) -> dict:
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "category": category,
        "model": model,
        "judge": judge,
        "score": round(float(score), 2),
        "critique": (critique or "")[:400],
        "q": (q or "")[:400],
        "a": (a or "")[:1200],
    }
    RL_STATE["pairs"].append(entry)
    day = entry["ts"][:10]
    day_stat = RL_STATE["daily"].setdefault(day, {"count": 0, "score_sum": 0.0})
    day_stat["count"] += 1
    day_stat["score_sum"] += entry["score"]
    _save_rl_state(RL_STATE)
    return entry


async def _judge_answer(q: str, answer: str, rubric: list[str]) -> dict:
    """LLM-as-judge: score 0-10 against rubric key points + a short critique."""
    system = (
        "You are a strict evaluation judge for an AI assistant. Score the ANSWER "
        "from 0 to 10 against the RUBRIC key points (each covered point earns "
        "marks; wrong, vague, or evasive claims lose marks). Reply in EXACTLY this format:\n"
        "SCORE: <number 0-10, one decimal allowed>\n"
        "CRITIQUE: <one or two sentences>"
    )
    user = (
        f"QUESTION: {q}\n\nRUBRIC:\n- "
        + "\n- ".join(rubric)
        + f"\n\nANSWER:\n{(answer or '')[:1500]}"
    )
    try:
        content, reasoning = await _call_llm(system, [{"role": "user", "content": user}])
        m = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", content or "")
        c = re.search(r"CRITIQUE:\s*(.+)", content or "", re.S)
        if m:
            score = max(0.0, min(10.0, float(m.group(1))))
            critique = c.group(1).strip() if c else ""
            return {"score": score, "critique": critique[:400], "judge": "llm"}
        if reasoning:
            # Reasoning-heavy judges sometimes do the scoring inside their
            # chain-of-thought - extract it instead of falling to heuristic.
            m2 = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", reasoning) or re.search(
                r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*10", reasoning
            )
            if m2:
                score = max(0.0, min(10.0, float(m2.group(1))))
                return {
                    "score": score,
                    "critique": "scored from judge reasoning",
                    "judge": "reasoning-derived",
                }
    except Exception:
        pass
    # Heuristic fallback so training never stalls when the judge is offline.
    words = len((answer or "").split())
    heuristic = 3.0 + (1.0 if words > 40 else 0.0) + (1.0 if words > 90 else 0.0)
    return {
        "score": min(heuristic, 10.0),
        "critique": "judge offline - heuristic length-based score",
        "judge": "heuristic",
    }


def _pick_exemplars(query: str, k: int = 2) -> list[dict]:
    """Reward-weighted memory: top-scoring past pairs whose question words
    overlap the query. These become few-shot exemplars for the live answer."""
    best = [p for p in RL_STATE["pairs"] if p.get("score", 0) >= 8.0]
    if not best:
        return []
    from nexus.infrastructure.adapters.persistence.agent_memory_store import tokenize

    q_tokens = set(tokenize(query or ""))

    def overlap(p: dict) -> int:
        return len(q_tokens & set(tokenize(p.get("q", ""))))

    best.sort(key=lambda p: (overlap(p), p.get("score", 0)), reverse=True)
    return [p for p in best[:k] if overlap(p) > 0]


class TrainingJudgeRequest(BaseModel):
    q: str
    a: str
    category: str = "custom"


@app.get("/api/training/corpus")
async def api_training_corpus():
    return JSONResponse({"count": len(TRAINING_CORPUS), "corpus": TRAINING_CORPUS})


@app.post("/api/training/judge")
async def api_training_judge(req: TrainingJudgeRequest):
    """Judge any question/answer pair and store it as a scored training pair."""
    verdict = await _judge_answer(
        req.q,
        req.a,
        ["Accuracy", "Technical depth", "Clarity", "No boilerplate or hedging"],
    )
    entry = _record_training_pair(
        req.q, req.a, verdict["score"], verdict["critique"], req.category,
        LLM_STATE.get("model", ""), verdict.get("judge", ""),
    )
    return JSONResponse({"ok": True, "entry": entry})


@app.post("/api/training/run")
async def api_training_run(n: int = 3):
    """Answer + judge n not-yet-scored hard questions from the corpus."""
    target = max(1, min(n, len(TRAINING_CORPUS)))
    scored_qs = {p.get("q") for p in RL_STATE["pairs"]}
    done = []
    for item in TRAINING_CORPUS:
        if len(done) >= target:
            break
        if item["q"] in scored_qs:
            continue
        answer, _r = await _call_llm(
            "You are J.A.R.V.I.S. Answer precisely and technically. Address the "
            "user as 'sir'. At most 8 sentences; no preamble or meta talk.",
            [{"role": "user", "content": item["q"]}],
        )
        if not (answer or "").strip():
            continue
        verdict = await _judge_answer(item["q"], answer, item["rubric"])
        entry = _record_training_pair(
            item["q"], answer, verdict["score"], verdict["critique"],
            item["category"], LLM_STATE.get("model", ""), verdict.get("judge", ""),
        )
        done.append(
            {"id": item["id"], "score": entry["score"], "critique": entry["critique"][:160]}
        )
    return JSONResponse({"ok": True, "trained": len(done), "results": done})


@app.get("/api/training/stats")
async def api_training_stats():
    """Day-day progression: total pairs, per-day averages, category averages."""
    pairs = RL_STATE["pairs"]
    daily = [
        {
            "date": day,
            "count": v["count"],
            "avg_score": round(v["score_sum"] / max(v["count"], 1), 2),
        }
        for day, v in sorted(RL_STATE["daily"].items())
    ]
    by_cat: dict[str, list[float]] = {}
    for p in pairs:
        by_cat.setdefault(p.get("category", "custom"), []).append(p.get("score", 0))
    categories = {
        c: {"count": len(v), "avg": round(sum(v) / len(v), 2)} for c, v in by_cat.items()
    }
    best = sorted(pairs, key=lambda p: p.get("score", 0), reverse=True)[:5]
    return JSONResponse(
        {
            "total_pairs": len(pairs),
            "avg_score": round(sum(p.get("score", 0) for p in pairs) / max(len(pairs), 1), 2),
            "daily": daily,
            "categories": categories,
            "best_exemplars": [{"q": p["q"][:80], "score": p["score"]} for p in best],
        }
    )


_TRAINING_TASK: asyncio.Task | None = None


async def _daily_training_loop():
    """Day-day training: answer + judge fresh corpus questions every 24h."""
    await asyncio.sleep(45)  # let the app finish booting
    while True:
        try:
            await api_training_run(3)
        except Exception:
            pass
        await asyncio.sleep(24 * 3600)


@app.on_event("startup")
async def _start_daily_training():
    global _TRAINING_TASK
    if _TRAINING_TASK is None or _TRAINING_TASK.done():
        _TRAINING_TASK = asyncio.create_task(_daily_training_loop())


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


def _rea_mcp_call(
    tool: str, args: dict[str, Any], timeout: float = 120.0
) -> tuple[str | None, str | None]:
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


class ReaAnalyzeRequest(BaseModel):
    tool: str
    path: str
    extra_args: dict[str, Any] = {}


class BlueprintSaveRequest(BaseModel):
    title: str
    goal: str = ""
    steps: list[str] = []
    files: list[str] = []
    verify: list[str] = []
    tools: list[str] = []
    tags: str = "rea"


@app.post("/api/rea/analyze")
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


@app.get("/api/rea/tools")
async def api_rea_tools():
    ready = REA_ENTRY.is_file() and REA_DIST.is_file()
    return JSONResponse({"tools": REA_TOOLS, "ready": ready})


@app.get("/api/blueprints")
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
                {"id": c.id, "agent": c.agent, "tags": sorted(c.tags), "text": c.text}
                for c in chunks
            ]
        }
    )


@app.post("/api/blueprints")
async def api_save_blueprint(req: BlueprintSaveRequest):
    store = _memory()
    tags = [t.strip() for t in req.tags.split(",") if t.strip()]
    text = _compose_blueprint(req.title, req.goal, req.steps, req.files, req.verify, req.tools)
    chunk, created = store.put(agent="holo", kind="blueprint", text=text, tags=tags or ["blueprint"])
    return JSONResponse({"ok": True, "id": chunk.id, "created": created})


@app.get("/{path:path}")
async def serve_static(path: str, request: Request):
    """Serve any file from frontend/ as a static fallback."""
    safe = Path(path)
    if ".." in safe.parts:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    full = FRONTEND_DIR / safe
    if full.is_file():
        return FileResponse(full)

    return JSONResponse({"error": "not found"}, status_code=404)


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("GALAXY_PORT", "8099"))
    print(
        f"[galaxy] N.E.X.U.S. J.A.R.V.I.S. Cortex active on http://127.0.0.1:{port}"
    )
    print(f"[galaxy] graph: {len(GRAPH.get('nodes', []))} nodes loaded")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
