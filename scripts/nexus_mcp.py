#!/usr/bin/env python3
"""Standard Model Context Protocol (MCP) server for Project Nexus.

Speaks JSON-RPC 2.0 over stdio (protocolVersion 2024-11-05).
Exposes the shared coordination blackboard (tasks, plans, memory, consensus)
as MCP resources and tools without breaking the plan-first gate.

CRITICAL: stdout is the protocol channel. All internal tool calls that print
must be wrapped in contextlib.redirect_stdout.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure src/ and scripts/ are available before importing internal modules
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from agent_comm import (  # noqa: E402
    OWNER_MAP,
    PRIORITY_RANK,
    cmd_ask,
    cmd_claim,
    cmd_heartbeat,
    cmd_inbox,
    cmd_progress,
    cmd_resolve,
    load_state,
    main_root,
)

from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore  # noqa: E402
from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol  # noqa: E402
from nexus.infrastructure.adapters.swarm.planning import PlanningBoard  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "idle"
SERVER_VERSION = "1.0.0"


def _planning_board() -> PlanningBoard:
    return PlanningBoard(main_root() / "planning_state.json")


def _consensus_protocol() -> ConsensusProtocol:
    return ConsensusProtocol(main_root() / "consensus_state.json")


def _agent_memory_store() -> AgentMemoryStore:
    return AgentMemoryStore(main_root() / "agent_memory.json")


# ── MCP Resources ─────────────────────────────────────────────────────────────

RESOURCES_SPEC = [
    {
        "uri": "nexus://tasks/pending",
        "name": "Pending Tasks",
        "description": "Available tasks awaiting claiming in the shared queue",
        "mimeType": "application/json",
    },
    {
        "uri": "nexus://state/current",
        "name": "Current Swarm State",
        "description": "Git branch, status, architecture tree, and agent statuses",
        "mimeType": "application/json",
    },
    {
        "uri": "nexus://board/plans",
        "name": "Active Plans",
        "description": "In-progress plan-first gate state",
        "mimeType": "application/json",
    },
    {
        "uri": "nexus://board/consensus",
        "name": "Consensus Board",
        "description": "Patches and proposals awaiting votes or resolution",
        "mimeType": "application/json",
    },
    {
        "uri": "nexus://memory/recent",
        "name": "Recent Memory Chunks",
        "description": "Recent content-addressable memory store entries",
        "mimeType": "application/json",
    },
]


def handle_resource_read(uri: str) -> dict[str, Any]:
    """Read rendezvous state for a given resource URI."""
    if uri == "nexus://tasks/pending":
        state = load_state()
        pending = [t for t in state.get("task_queue", []) if t.get("status") == "pending"]
        pending.sort(
            key=lambda t: (PRIORITY_RANK.get(t.get("priority", "medium"), 2), t.get("created_at", ""))
        )
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(pending, indent=2)}

    if uri == "nexus://state/current":
        state = load_state()
        git_res = subprocess.run(
            ["git", "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            cwd=str(main_root()),
        )
        payload = {
            "git": git_res.stdout.strip(),
            "agents": state.get("agents", {}),
            "state_hash": state.get("state_hash", ""),
            "locks": state.get("locks", []),
        }
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(payload, indent=2)}

    if uri == "nexus://board/plans":
        board = _planning_board()
        plans = [p.to_dict() for p in board.list_plans()]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(plans, indent=2)}

    if uri == "nexus://board/consensus":
        cp = _consensus_protocol()
        proposals = [p.to_dict() for p in cp.list_proposals()]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(proposals, indent=2)}

    if uri == "nexus://memory/recent":
        store = _agent_memory_store()
        recent = [c.to_dict() for c in store.latest(n=10)]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(recent, indent=2)}

    raise ValueError(f"Unknown resource URI: {uri}")


# ── MCP Tools ─────────────────────────────────────────────────────────────────

TOOLS_SPEC = [
    {
        "name": "next_task",
        "description": "CAPABILITY-BASED auto-pick for next task using OWNER_MAP (astra=application/eval/docs, tron=domain/tests, xenom=infra/web)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "enum": ["ceo", "astra", "tron", "xenom"],
                    "description": "The agent requesting work",
                }
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "claim_task",
        "description": "Claim a pending task in the shared queue",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "task_id": {"type": "string", "description": "ID of task to claim"},
            },
            "required": ["agent_id", "task_id"],
        },
    },
    {
        "name": "resolve_task",
        "description": "Resolve a claimed task with required test evidence",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "task_id": {"type": "string", "description": "ID of task to resolve"},
                "evidence": {"type": "string", "description": "Command and test output proving resolution"},
            },
            "required": ["agent_id", "task_id", "evidence"],
        },
    },
    {
        "name": "heartbeat",
        "description": "Send a liveness heartbeat for the agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "progress",
        "description": "Update what the agent is currently doing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "doing": {"type": "string", "description": "Brief description of current action"},
            },
            "required": ["agent_id", "doing"],
        },
    },
    {
        "name": "ask_ceo",
        "description": "Post a message or blocker request to the CEO inbox",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["astra", "tron", "xenom"]},
                "kind": {"type": "string", "enum": ["question", "blocker", "escalation", "handoff"]},
                "text": {"type": "string", "description": "Details of the question or blocker"},
            },
            "required": ["agent_id", "kind", "text"],
        },
    },
    {
        "name": "check_inbox",
        "description": "Inspect open messages and replies",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "plan_create",
        "description": "Create a bounded plan (draft) before implementation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "title": {"type": "string", "description": "Title of the plan"},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 'description|file1,file2' step specs",
                },
                "max_steps": {"type": "integer", "default": 5},
            },
            "required": ["agent_id", "title", "steps"],
        },
    },
    {
        "name": "plan_begin",
        "description": "Begin and freeze a plan (draft -> in_progress)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "ID of plan to begin"},
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "plan_step",
        "description": "Mark the current in-order step of an in-progress plan as completed",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "ID of plan"},
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "plan_finish",
        "description": "Complete an in-progress plan once all steps are done",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "ID of plan to finish"},
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "plan_check_file",
        "description": "Check if editing a file is permitted by the plan-first gate",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Repo-relative file path"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "memory_put",
        "description": "Append an immutable report, patch, or decision to content-addressable memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "kind": {
                    "type": "string",
                    "enum": ["report", "patch", "decision", "context", "note", "error"],
                },
                "text": {"type": "string", "description": "Content of memory chunk"},
                "tags": {"type": "string", "description": "Comma-separated tags"},
                "refs": {"type": "string", "description": "Comma-separated chunk IDs this extends"},
            },
            "required": ["agent_id", "kind", "text"],
        },
    },
    {
        "name": "memory_query",
        "description": "Search memory chunks using hybrid semantic and TF-IDF relevance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "k": {"type": "integer", "default": 5, "description": "Number of results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "consensus_propose",
        "description": "Propose a patch for swarm review and automated checks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "author": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "title": {"type": "string", "description": "Title of patch proposal"},
                "patch_file": {"type": "string", "description": "Path to diff/patch file"},
                "files": {"type": "string", "description": "Comma-separated list of touched files"},
                "description": {"type": "string", "description": "Description of proposed change"},
            },
            "required": ["author", "title", "files"],
        },
    },
    {
        "name": "consensus_review",
        "description": "Review a proposal with approval or changes requested",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": ["astra", "tron", "xenom"]},
                "proposal_id": {"type": "string", "description": "ID of proposal to review"},
                "verdict": {"type": "string", "enum": ["approve", "request_changes"]},
                "comment": {"type": "string", "description": "Review notes / rationale"},
            },
            "required": ["agent_id", "proposal_id", "verdict"],
        },
    },
    {
        "name": "consensus_vote",
        "description": "Cast decisive vote on a proposal (CEO decides; workers may vote)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ceo_agent": {"type": "string", "enum": ["ceo", "astra", "tron", "xenom"]},
                "proposal_id": {"type": "string", "description": "ID of proposal"},
                "verdict": {"type": "string", "enum": ["yes", "no"]},
            },
            "required": ["ceo_agent", "proposal_id", "verdict"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List all tasks in the swarm queue with their status and assignee",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "claimed", "resolved", "all"]},
            },
        },
    },
    {
        "name": "agent_status",
        "description": "Report agent liveness and current work across the swarm",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_plans",
        "description": "List active plan records and progress for the plan-first gate",
        "inputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["draft", "in_progress", "done", "abandoned", "all"]}},
        },
    },
    {
        "name": "git_status",
        "description": "Check current workspace git status",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


class _Args:
    """Helper to mock argparse Namespace for reusing existing command handlers."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _exec_with_redirect(func: Any, *args: Any, **kwargs: Any) -> str:
    """Execute a function while capturing all stdout/stderr."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            func(*args, **kwargs)
        except SystemExit:
            pass
    return buf.getvalue().strip()


def handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch an MCP tool call to the corresponding Nexus implementation."""
    state = load_state()

    if name == "next_task":
        agent = arguments.get("agent_id", "unassigned")
        mine = [
            t for t in state.get("task_queue", []) if t.get("status") == "pending" and t.get("for") == agent
        ]
        if not mine:
            # Capability fallback based on OWNER_MAP
            prefixes = OWNER_MAP.get(agent, [])
            for t in state.get("task_queue", []):
                if t.get("status") != "pending":
                    continue
                target = t.get("for", "any")
                if target in ("any", "unassigned", None):
                    files = t.get("files", [])
                    desc = (t.get("description") or "").lower()
                    if any(
                        any(f.startswith(p) or f == p.rstrip("/") for p in prefixes) for f in files
                    ) or any(p.strip("/").lower() in desc for p in prefixes):
                        mine.append(t)
        if not mine:
            return f"[{agent}] queue empty - no pending tasks matching capabilities."
        mine.sort(key=lambda t: (PRIORITY_RANK.get(t.get("priority", "medium"), 2), t.get("created_at", "")))
        t = mine[0]
        res = [
            f"[{agent}] next task: {t['id']} (priority={t.get('priority', 'medium')})",
            f"  what: {t.get('description', '')[:300]}",
        ]
        if t.get("files"):
            res.append(f"  files: {', '.join(t['files'][:8])}")
        if t.get("acceptance"):
            res.append(f"  acceptance: {'; '.join(t['acceptance'])}")
        res.append(f"  claim it: claim_task(agent_id='{agent}', task_id='{t['id']}')")
        return "\n".join(res)

    if name == "claim_task":
        args = _Args(agent=arguments.get("agent_id"), task_id=arguments.get("task_id"))
        return _exec_with_redirect(cmd_claim, args, state)

    if name == "resolve_task":
        args = _Args(
            agent=arguments.get("agent_id"),
            task_id=arguments.get("task_id"),
            evidence=arguments.get("evidence"),
        )
        return _exec_with_redirect(cmd_resolve, args, state)

    if name == "heartbeat":
        args = _Args(agent=arguments.get("agent_id"))
        return _exec_with_redirect(cmd_heartbeat, args, state)

    if name == "progress":
        args = _Args(agent=arguments.get("agent_id"), doing=arguments.get("doing"))
        return _exec_with_redirect(cmd_progress, args, state)

    if name == "ask_ceo":
        args = _Args(
            agent=arguments.get("agent_id"),
            kind=arguments.get("kind", "question"),
            text=arguments.get("text", ""),
        )
        return _exec_with_redirect(cmd_ask, args, state)

    if name == "check_inbox":
        args = _Args(agent=arguments.get("agent_id"))
        return _exec_with_redirect(cmd_inbox, args, state)

    if name == "plan_create":
        board = _planning_board()
        parsed: list[tuple[str, list[str]]] = []
        for s in arguments.get("steps", []):
            parts = s.split("|", 1)
            desc = parts[0].strip()
            files = [f.strip() for f in parts[1].split(",") if f.strip()] if len(parts) > 1 else []
            parsed.append((desc, files))
        plan, error = board.create_plan(
            agent=arguments.get("agent_id", "tron"),
            title=arguments.get("title", ""),
            steps=parsed,
            max_steps=arguments.get("max_steps", 5),
        )
        if plan is None or error:
            return f"Plan rejected: {error}"
        return f"Plan created: {plan.id} [draft] with {len(parsed)} steps."

    if name == "plan_begin":
        board = _planning_board()
        plan, error = board.begin(arguments.get("plan_id", ""))
        if plan is None:
            return f"Error: {error}"
        if error:
            return f"Plan not begun: {error}"
        return f"Plan begun: {plan.id} [{plan.status}] - frozen for edits."

    if name == "plan_step":
        board = _planning_board()
        plan, error = board.complete_step(arguments.get("plan_id", ""))
        if plan is None:
            return f"Error: {error}"
        if error:
            return f"Step not completed: {error}"
        idx = plan.next_step()
        done_idx = (idx - 1) if idx is not None else len(plan.steps) - 1
        return f"Plan {plan.id}: step {done_idx + 1} completed ({plan.progress()})"

    if name == "plan_finish":
        board = _planning_board()
        plan, error = board.finish(arguments.get("plan_id", ""))
        if plan is None:
            return f"Error: {error}"
        if error:
            return f"Plan not finished: {error}"
        return f"Plan {plan.id} finished: status={plan.status}"

    if name == "plan_check_file":
        board = _planning_board()
        covered, plan, reason = board.is_covered(arguments.get("file_path", ""))
        if covered:
            return f"ALLOWED: covered by {plan.id if plan else 'plan'} ({reason})"
        return f"DENIED: {reason}"

    if name == "memory_put":
        store = _agent_memory_store()
        tags_raw = arguments.get("tags", "")
        tags = (
            [t.strip() for t in tags_raw.split(",") if t.strip()]
            if isinstance(tags_raw, str)
            else list(tags_raw or [])
        )
        refs_raw = arguments.get("refs", "")
        refs = (
            [r.strip() for r in refs_raw.split(",") if r.strip()]
            if isinstance(refs_raw, str)
            else list(refs_raw or [])
        )
        chunk, created = store.put(
            agent=arguments.get("agent_id", "tron"),
            kind=arguments.get("kind", "report"),
            text=arguments.get("text", ""),
            tags=tags,
            refs=refs,
        )
        verb = "Stored memory chunk" if created else "Duplicate memory chunk"
        return f"{verb}: {chunk.id} (tick {chunk.tick})"

    if name == "memory_query":
        store = _agent_memory_store()
        results = store.query(arguments.get("query", ""), k=int(arguments.get("k", 5)))
        lines = [f"Found {len(results)} chunks:"]
        for chunk, score in results:
            lines.append(f"  [{score:.3f}] {chunk.id} ({chunk.kind} by {chunk.agent}): {chunk.text[:120]}")
        return "\n".join(lines)

    if name == "consensus_propose":
        cp = _consensus_protocol()
        patch_file = arguments.get("patch_file")
        draft_content = ""
        if patch_file and Path(patch_file).exists():
            draft_content = Path(patch_file).read_text(encoding="utf-8")
        else:
            draft_content = arguments.get("description", "Proposal patch")
        files_raw = arguments.get("files", "")
        files = (
            [f.strip() for f in files_raw.split(",") if f.strip()]
            if isinstance(files_raw, str)
            else list(files_raw)
        )
        prop = cp.propose(
            author=arguments.get("author", "xenom"),
            title=arguments.get("title", "Code Proposal"),
            draft=draft_content,
            files=files,
        )
        return f"Proposed {prop.id}: {prop.title} (status={prop.status})"

    if name == "consensus_review":
        cp = _consensus_protocol()
        prop = cp.review(
            proposal_id=arguments.get("proposal_id", ""),
            reviewer=arguments.get("agent_id", "astra"),
            verdict=arguments.get("verdict", "approve"),
            note=arguments.get("comment", ""),
        )
        if prop is None:
            return f"Error: unknown proposal {arguments.get('proposal_id', '')}"
        return f"Reviewed {prop.id}: status={prop.status}, reviews={prop.reviews}"

    if name == "consensus_vote":
        cp = _consensus_protocol()
        prop = cp.vote(
            proposal_id=arguments.get("proposal_id", ""),
            agent=arguments.get("ceo_agent", "ceo"),
            choice=arguments.get("verdict", "yes"),
        )
        if prop is None:
            return f"Error: unknown proposal {arguments.get('proposal_id', '')}"
        return f"Voted on {prop.id}: status={prop.status}, verdict={prop.verdict}"

    if name == "list_tasks":
        tasks = state.get("task_queue", [])
        status_filter = arguments.get("status", "all")
        if status_filter != "all":
            tasks = [t for t in tasks if t.get("status") == status_filter]
        if not tasks:
            return "No tasks match the requested filter."
        lines = [f"Task queue ({len(tasks)}):"]
        for t in tasks:
            assignee = t.get("claimed_by") or t.get("for") or "unassigned"
            lines.append(
                f"  [{t.get('id', 'unknown')}] {t.get('status', 'unknown')} | {t.get('description', '')[:80]} | claimed_by={assignee}"
            )
        return "\n".join(lines)

    if name == "agent_status":
        agents = state.get("agents", {})
        if not agents:
            return "No agents are currently registered."
        lines = ["Agent status:"]
        for agent, info in sorted(agents.items()):
            task = info.get("current_task") or "-"
            lines.append(f"  {agent}: status={info.get('status', 'unknown')} task={task}")
        return "\n".join(lines)

    if name == "list_plans":
        board = _planning_board()
        plans = board.list_plans()
        status_filter = arguments.get("status", "all")
        if status_filter != "all":
            plans = [p for p in plans if p.status == status_filter]
        if not plans:
            return "No plans match the requested filter."
        lines = [f"Plans ({len(plans)}):"]
        for p in plans:
            lines.append(f"  [{p.id}] {p.status} | {p.agent} | {p.progress()} | {p.title[:80]}")
        return "\n".join(lines)

    if name == "git_status":
        r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=str(main_root()))
        return r.stdout.strip() or "working tree clean"

    raise ValueError(f"Unknown tool: {name}")


# ── MCP Server Core Loop (JSON-RPC 2.0 over stdio) ───────────────────────────


def handle_json_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 request or notification."""
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no id)
    if req_id is None:
        if method == "notifications/initialized":
            return None
        if method == "cancelled":
            return None
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": RESOURCES_SPEC}}

    if method == "resources/read":
        uri = params.get("uri", "")
        try:
            content = handle_resource_read(uri)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"contents": [content]}}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(e)},
            }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SPEC}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        try:
            res_text = handle_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": res_text}],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio() -> None:
    """Run the newline-delimited JSON-RPC loop over stdio."""
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError as err:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {err}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        response = handle_json_rpc(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
