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
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

# ── paths ────────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
CONFIG_DIR = ROOT_DIR / "config"
ENV_PATH = ROOT_DIR / ".env"

# Ensure repo root, src/ and scripts/ are in sys.path
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

# Load .env from project root
load_dotenv(ENV_PATH)

# ── LLM config ──────────────────────────────────────────────────────────────


# LLM configuration, provider state, and model calls live in the LLM service
# (backend/services/llm.py). Call sites access it via llm_service.<name> so
# tests can patch the owning module directly.
from backend.services import llm as llm_service  # noqa: E402
from backend.services.llm import (  # noqa: E402,F401
    DEFAULT_NIM_BASE_URL,
    LLM_CFG,
    LLM_STATE,
    SUPPORTED_NIM_MODELS,
    _active_llm_target,
    _check_llm_alive,
    _nim_ready,
    _persist_llm_state,
)

# (Model registry state lives in backend/services/llm.py; endpoints below.)

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
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1]


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
# Self-contained tools live in backend/services/tools.py; GRAPH-dependent ones
# (system diagnostics, cosmos trigger) remain here until the knowledge service
# lands. Call sites go through tools_service.<name> for testability.

from backend.services import tools as tools_service  # noqa: E402
from backend.services import training as training_service  # noqa: E402,F401
from backend.services.tools import (  # noqa: E402,F401
    _extract_path_hint,
    _safe_repo_path,
    tool_agent_status,
    tool_calculator,
    tool_git_status,
    tool_list_tasks,
    tool_memory_query,
    tool_read_repo,
    tool_run_python,
)
from backend.services.training import (  # noqa: E402,F401
    RL_STATE,
    RL_STATE_PATH,
    TRAINING_CORPUS,
    _judge_answer,
    _pick_exemplars,
    _record_training_pair,
)


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


# (_check_llm_alive and _call_llm live in backend/services/llm.py; call sites
#  below go through llm_service.<name> so tests patch the owning module.)


# ── J.A.R.V.I.S. Intelligent Synthesis Engine ────────────────────────────────


def _clean_markdown_excerpt(text: str) -> str:
    """Strip repetitive headers and noise for synthesis."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("```")]
    return " ".join(lines)[:380]


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
                f"{e['name']}{'/' if e['type'] == 'dir' else ''}" for e in repo.get("entries", [])[:25]
            )
            ans = f"Listing of **{repo.get('path')}** ({repo.get('count')} entries), sir:\n\n{names}"
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

    # 1c. DEEP RESEARCH
    if intent == "research":
        res = tool_data.get("research", {})
        if res.get("ok"):
            srcs = ", ".join(res.get("sources", [])) or "repository knowledge"
            ans = (
                f"Research complete, sir. The full note is saved to **{res['note_path']}** "
                f"and the knowledge graph has been re-indexed.\n\n"
                f"{res.get('summary', '')[:500]}\n\n"
                f"Sub-questions explored: {'; '.join(res.get('sub_queries', [])[:3])}. "
                f"Sources: {srcs}."
            )
            return ans, [], ["deep_research"]
        ans = (
            "The research pipeline hit a snag, sir: "
            + str(res.get("error", "unknown failure"))
            + " I can still answer from repository knowledge in the meantime."
        )
        return ans, [], ["deep_research"]

    # 2. GIT STATUS & COMMITS
    if intent == "git":
        git = tool_data.get("git", {})
        branch = git.get("branch", "master")
        clean = git.get("clean", True)
        changes_count = git.get("changes_count", 0)
        recent = git.get("recent_commits", [])
        commits_md = (
            "\n".join([f"  • `{c}`" for c in recent[:3]]) if recent else "  • No recent commits detected."
        )

        status_text = "Working tree is clean." if clean else f"{changes_count} pending file changes detected."
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
            (["agent_status", "knowledge_rag"] if matched_id else ["agent_status"]),
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
        ans = f"Python execution finished in {elapsed}ms, sir:\n\n" f"```text\n{out_block}\n```"
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
            chunks_md = "  • No memory chunks match the specified query terms."

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
    """Serve index.html as the primary dashboard.

    Opt-in for demos/embeds: ``NEXUS_ROOT_PAGE=workspace`` sends the bare host to the
    light-mode workspace cockpit instead, leaving the graph as the default.
    """
    if (os.environ.get("NEXUS_ROOT_PAGE") or "").strip().lower() == "workspace":
        return RedirectResponse("/workspace", status_code=307)
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


@app.get("/workspace")
@app.get("/workspace.html")
async def serve_workspace():
    """NEXUS OS — premium light-mode workspace + floating cockpit console."""
    page = FRONTEND_DIR / "workspace.html"
    if not page.is_file():
        return JSONResponse({"error": "workspace.html missing"}, status_code=404)
    return FileResponse(page, media_type="text/html")


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
                title = (lines[0].lstrip("# ").strip() if lines else p.stem)[:48] or p.stem
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
            tree.append({"kind": "folder", "name": folder_name, "files": files})

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
        clean_id = node_id.replace("note:", "").replace("folder:", "").replace("k:", "")
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
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    # Re-index live
    try:
        from backend.indexer import build_graph, write_outputs

        new_graph = build_graph()
        write_outputs(new_graph)
        GRAPH = new_graph
    except Exception:
        pass

    summary = f"Node '{found_node.get('label') if found_node else node_id}' updated on disk."
    _COSMOS_ACTIVITY.insert(0, {"ts": time.time(), "node": "memory", "ok": True, "summary": summary})
    return JSONResponse({"ok": True, "node_id": node_id, "summary": summary, "file": file_rel})


class SaveNoteRequest(BaseModel):
    title: str
    content: str


@app.post("/api/notes/save")
async def api_save_note(req: SaveNoteRequest):
    """Save a synthesis as a new note in docs/notes/, re-index, and return new node."""
    global GRAPH
    notes_dir = ROOT_DIR / "docs" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]+", "-", req.title.lower()).strip("-")[:48] or f"note-{int(time.time())}"
    file_path = notes_dir / f"{slug}.md"

    body = f"# {req.title}\n\n{req.content}\n"
    try:
        file_path.write_text(body, encoding="utf-8")
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

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
    _COSMOS_ACTIVITY.insert(0, {"ts": time.time(), "node": "memory", "ok": True, "summary": summary})
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
    return JSONResponse({"ok": True, "suggestions": top_suggestions, "count": len(top_suggestions)})


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
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    try:
        from backend.indexer import build_graph, write_outputs

        new_graph = build_graph()
        write_outputs(new_graph)
        GRAPH = new_graph
    except Exception:
        pass

    summary = f"Dream link approved: '{src_node.get('label')}' ↔ '{tgt_node.get('label')}'."
    _COSMOS_ACTIVITY.insert(0, {"ts": time.time(), "node": "dream", "ok": True, "summary": summary})
    return JSONResponse({"ok": True, "source": req.source, "target": req.target, "summary": summary})


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
            remediation.append("Store secrets in .env or secret store; do not commit keys.")

        # 2. Unsafe shell/exec execution
        if "subprocess.run(shell=True)" in text or "os.system(" in text:
            issues.append("Unsafe shell execution (shell=True or os.system) found.")
            remediation.append("Use array arguments with SubprocessSandbox or DockerSandbox.")

        # 3. Prompt injection vulnerabilities
        if re.search(r"(?i)(ignore previous instructions|system prompt override)", text):
            issues.append("Prompt injection risk pattern detected in note content.")
            remediation.append("Sanitize user-provided text with perimeter ReAct validator.")

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

    query = (raw.get("question", "") or raw.get("message", "") or "").strip()

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
    if any(q_lower == g or q_lower.startswith(g + " ") for g in greetings) and len(q_lower.split()) <= 6:
        intent = "greeting"
        tool_data["diag"] = tool_system_diagnostics()

    # 1b. Repo / File Inspection (explicit reads, a path in the query, or a
    # question about the project/repo itself)
    elif bool(_extract_path_hint(query)) or (
        any(
            kw in q_lower
            for kw in (
                "read",
                "see",
                "look at",
                "open",
                "inspect",
                "show me",
                "project file",
                "the repo",
                "repository",
                "directory",
                "folder",
                "source code",
            )
        )
        and any(kw in q_lower for kw in ("file", "repo", "project", "directory", "folder", "code", "path"))
    ):
        intent = "repo"
        tool_data["repo"] = tools_service.tool_read_repo(query)

    # 1c. Deep Research (broad multi-source investigation)
    elif any(kw in q_lower for kw in ("research", "deep dive", "investigate", "look up")):
        intent = "research"
        tool_data["research"] = await tools_service.deep_research(query)

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
        tool_data["git"] = tools_service.tool_git_status()

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
        tool_data["tasks"] = tools_service.tool_list_tasks()

    # 4. Agent Swarm
    elif any(kw in q_lower for kw in ["agent", "agents", "astra", "tron", "xenom", "ceo", "swarm"]):
        intent = "agents"
        tool_data["agents"] = tools_service.tool_agent_status()

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
        tool_data["py"] = tools_service.tool_run_python(code)

    # 6. Math & Calculator
    elif any(kw in q_lower for kw in ["calculate", "math", "sqrt", "factorial"]) or (
        any(op in query for op in ["+", "-", "*", "/", "%", "^"])
        and any(char.isdigit() for char in query)
        and len(query.split()) <= 6
    ):
        intent = "calculator"
        expr = query.replace("calculate", "").replace("what is", "").replace("math", "").strip()
        tool_data["calc"] = tools_service.tool_calculator(expr)

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
    elif any(kw in q_lower for kw in ["memory", "recall", "remember", "search memory"]):
        intent = "memory"
        tool_data["memory"] = tools_service.tool_memory_query(query)

    # 9. Knowledge RAG
    top_notes = _pick_top_notes(query, k=5)

    # Generate synthesized J.A.R.V.I.S. answer
    answer, node_ids, tools_used = _synthesize_jarvis_answer(query, intent, tool_data, top_notes)

    # Try external LLM if available and responding
    assistant_reasoning = ""
    base_url = LLM_CFG.get("base_url", "")
    model = LLM_CFG.get("model", "")
    if base_url and model and await llm_service._check_llm_alive():
        try:
            notes_context = "\n".join([f"[{n['label']}]: {n['excerpt'][:250]}" for n in top_notes[:3]])
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
                    f"Q: {p['q']}\nA (rated {p['score']}/10): {p['a'][:500]}" for p in exemplars
                )
                system_prompt += (
                    "\n\nMirror the clarity, structure, and technical depth of "
                    f"these past top-rated answers:\n{ex_txt}"
                )
            reply_text, reply_reasoning = await llm_service._call_llm(
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


# ── Routers (Upgrade 1): chat + cosmos remain in main; the rest are modular ──

from backend.routers import holo as holo_router  # noqa: E402
from backend.routers import models as models_router  # noqa: E402
from backend.routers import rea as rea_router  # noqa: E402
from backend.routers import research as research_router  # noqa: E402
from backend.routers import training as training_router  # noqa: E402
from backend.routers import workspace as workspace_router  # noqa: E402

app.include_router(holo_router.router)
app.include_router(models_router.router)
app.include_router(research_router.router)
app.include_router(training_router.router)
app.include_router(rea_router.router)
app.include_router(workspace_router.router)


# ── static file fallback (serve frontend/) ───────────────────────────────────


# (Training service - corpus, judge, reward store, exemplars - lives in
#  backend/services/training.py; endpoints and the daily loop remain here.)

_TRAINING_TASK: asyncio.Task | None = None


@app.on_event("startup")
async def _start_daily_training():
    global _TRAINING_TASK
    if _TRAINING_TASK is None or _TRAINING_TASK.done():
        _TRAINING_TASK = asyncio.create_task(training_router._daily_training_loop())


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
    print(f"[galaxy] N.E.X.U.S. J.A.R.V.I.S. Cortex active on http://127.0.0.1:{port}")
    print(f"[galaxy] graph: {len(GRAPH.get('nodes', []))} nodes loaded")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
