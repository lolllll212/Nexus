"""Headless IDE bridge - WebSocket event bus between the orchestrator and VS Code.

Replaces the manual prompt-copying bridge: agents and VS Code connect to one
bus, receive push events (new tasks, CI results, consensus verdicts), and can
issue workspace commands headlessly via the `code` CLI.

Usage:
    python scripts/ide_bridge.py                    # serve on 127.0.0.1:8765
    python scripts/ide_bridge.py --port 9000 --poll 5

Client protocol (JSON messages):
    {"type": "ping"}                                    -> {"type": "pong", "clients": N}
    {"type": "event", "topic": "...", "payload": {...}} -> published on the bus + fanned out
    {"type": "cmd", "op": "open|edit|run", "params": {...}} -> headless workspace op

Workspace ops (executed via the VS Code CLI or subprocess, never blocking):
    open:  {"op": "open", "params": {"path": "src/..."}}
    run:   {"op": "run", "params": {"args": ["git", "status"]}}
    edit:  {"op": "edit", "params": {"path": "...", "content": "..."}}   # guarded, see below

The bridge also polls the shared task queue and pushes `nexus.task_created`
events, so connected clients learn about new work with zero polling latency.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from agent_comm import main_root  # noqa: E402

from nexus.domain.ports.event_bus import Event, EventTopic  # noqa: E402
from nexus.infrastructure.adapters.eventbus.websocket_event_bus import WebSocketEventBus  # noqa: E402

EDITABLE_ROOTS = ("src", "tests", "scripts", "docs", "plugins", "config")
_COMMAND_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _bridge_security_state() -> tuple[set[str], int, int]:
    raw_allowlist = os.getenv("NEXUS_BRIDGE_ALLOWLIST", "ping,open").strip()
    allowlist = {op.strip().lower() for op in (raw_allowlist or "ping,open").split(",") if op.strip()}
    if not allowlist:
        allowlist = {"ping", "open"}
    rate_limit = max(1, int(os.getenv("NEXUS_BRIDGE_RATE_LIMIT", "10")))
    rate_window = max(1, int(os.getenv("NEXUS_BRIDGE_RATE_WINDOW_SECONDS", "60")))
    return allowlist, rate_limit, rate_window


def _bridge_rate_limit_check(op: str, limit: int, window_seconds: int) -> bool:
    now = datetime.now(UTC).timestamp()
    bucket = _COMMAND_RATE_BUCKETS[op]
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _run_cmd(args: list[str], timeout: float = 30.0) -> dict:
    """Run a subprocess with a hard deadline. Never hangs the bridge."""
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(main_root()),
            shell=False,
        )
        return {
            "ok": r.returncode == 0,
            "code": r.returncode,
            "stdout": r.stdout[-4000:],
            "stderr": r.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except FileNotFoundError as e:
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(e)}


def handle_cmd(op: str, params: dict) -> dict:
    """Headless workspace ops. Edits are guarded to project subdirectories."""
    allowlist, rate_limit, rate_window = _bridge_security_state()
    op_name = str(op).lower()
    if op_name not in allowlist:
        return {"ok": False, "error": f"op {op_name} not allowed"}
    if not _bridge_rate_limit_check(op_name, rate_limit, rate_window):
        return {"ok": False, "error": f"rate limit exceeded for {op_name}"}

    if op_name == "open":
        path = params.get("path", "")
        if not path:
            return {"ok": False, "error": "path required"}
        r = _run_cmd(["code", "-r", str(main_root() / path)])
        if not r["ok"] and "cannot find" in r["stderr"].lower():
            r = _run_cmd(["cmd", "/c", "start", "", str(main_root() / path)])
        return r
    if op_name == "run":
        args = params.get("args", [])
        if not args or not isinstance(args, list):
            return {"ok": False, "error": "args list required"}
        return _run_cmd([str(a) for a in args], timeout=float(params.get("timeout", 30)))
    if op_name == "edit":
        path = params.get("path", "")
        content = params.get("content")
        if not path or content is None:
            return {"ok": False, "error": "path and content required"}
        target = (main_root() / path).resolve()
        try:
            target.relative_to(main_root().resolve())
        except ValueError:
            return {"ok": False, "error": "path escapes repository"}
        root = target.relative_to(main_root().resolve()).parts[0] if target != main_root().resolve() else ""
        if root and root not in EDITABLE_ROOTS:
            return {"ok": False, "error": f"root {root} not editable"}
        # Plan-first gate: no headless edit to a file no in_progress plan covers.
        from nexus.infrastructure.adapters.swarm.planning import PlanningBoard

        covered, plan, gate_reason = PlanningBoard(main_root() / "planning_state.json").is_covered(path)
        if not covered:
            return {"ok": False, "error": f"plan gate: {gate_reason}", "gate": "plan-first"}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(target), "bytes": len(str(content)), "plan": plan.id}
    return {"ok": False, "error": f"unknown op {op_name!r}"}


def get_swarm_snapshot() -> dict[str, Any]:
    """Capture a coherent real-time snapshot of the multi-agent swarm state."""
    state_file = main_root() / "nexus_state.json"
    consensus_file = main_root() / "consensus_state.json"
    memory_file = main_root() / "agent_memory.json"
    activity_file = main_root() / "agent_activity.jsonl"

    agents: dict[str, Any] = {}
    task_queue: list[dict[str, Any]] = []
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            agents = data.get("agents", {})
            task_queue = data.get("task_queue", [])
        except Exception:
            pass

    for a in ("ceo", "astra", "tron", "xenom"):
        if a not in agents:
            agents[a] = {"status": "idle", "current_task": None, "last_heartbeat": None}

    proposals: list[dict[str, Any]] = []
    if consensus_file.exists():
        try:
            cdata = json.loads(consensus_file.read_text(encoding="utf-8"))
            proposals = cdata.get("proposals", [])
        except Exception:
            pass

    budget_cap = int(os.getenv("NEXUS_DAILY_TOKEN_BUDGET", "500000"))
    budgets = {
        a: {
            "limit": budget_cap,
            "used": 0,
            "pct": 0.0,
            "tier": "primary" if os.getenv("NEXUS_MODEL_ROUTING") == "1" else "local",
        }
        for a in ("ceo", "astra", "tron", "xenom")
    }

    heals: list[dict[str, Any]] = []
    if memory_file.exists():
        try:
            mdata = json.loads(memory_file.read_text(encoding="utf-8"))
            chunks = mdata.get("chunks", {})
            for cid, chunk in chunks.items():
                agent = chunk.get("agent")
                if agent in budgets:
                    text_len = len(chunk.get("text", ""))
                    budgets[agent]["used"] += max(25, text_len // 4)
                tags = chunk.get("tags", [])
                kind = chunk.get("kind", "")
                if "heal" in tags or "ci" in tags or kind == "patch":
                    heals.append(
                        {
                            "id": cid,
                            "agent": chunk.get("agent", "heal"),
                            "kind": kind,
                            "text": chunk.get("text", "")[:300],
                            "tags": tags,
                            "created_at": chunk.get("created_at"),
                        }
                    )
        except Exception:
            pass

    for b in budgets.values():
        b["pct"] = round(min(100.0, (b["used"] / b["limit"]) * 100), 1)

    if not heals and activity_file.exists():
        try:
            lines = activity_file.read_text(encoding="utf-8").strip().splitlines()[-10:]
            for line in lines:
                try:
                    rec = json.loads(line)
                    if "heal" in rec.get("action", "") or "verify" in rec.get("action", ""):
                        heals.append(
                            {
                                "id": rec.get("ts", ""),
                                "agent": rec.get("agent", "ceo"),
                                "kind": rec.get("action"),
                                "text": rec.get("detail", ""),
                                "tags": [rec.get("action")],
                                "created_at": rec.get("ts"),
                            }
                        )
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "agents": agents,
        "task_queue": task_queue,
        "consensus": proposals,
        "budgets": budgets,
        "heals": heals[-10:],
        "timestamp": datetime.now(UTC).isoformat(),
    }


class TaskQueueWatcher:
    """Polls shared swarm state and pushes real-time updates over the bridge."""

    def __init__(self, bus: WebSocketEventBus, poll_seconds: float) -> None:
        self.bus = bus
        self.poll_seconds = poll_seconds
        self._seen: set[str] = set()
        self._last_snapshot_hash: str = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _scan(self) -> None:
        snapshot = get_swarm_snapshot()

        # Emit task_created for newly pending tasks
        for t in snapshot.get("task_queue", []):
            if t.get("status") != "pending":
                continue
            tid = t.get("id", "")
            if not tid or tid in self._seen:
                continue
            self._seen.add(tid)
            _try_publish(
                self.bus,
                EventTopic.CONTEXT_INJECTION,
                {
                    "nexus_event": "task_created",
                    "task_id": tid,
                    "for": t.get("for", ""),
                    "priority": t.get("priority", "medium"),
                    "description": (t.get("description") or "")[:300],
                    "at": datetime.now(UTC).isoformat(),
                },
            )

        snap_str = json.dumps(snapshot, sort_keys=True)
        snap_hash = hashlib.sha256(snap_str.encode("utf-8")).hexdigest()
        if snap_hash != self._last_snapshot_hash:
            self._last_snapshot_hash = snap_hash
            _try_publish(
                self.bus,
                EventTopic.SYSTEM_HEALTH,
                {
                    "nexus_event": "swarm_sync",
                    "snapshot": snapshot,
                },
            )

    def _loop(self) -> None:
        state_file = main_root() / "nexus_state.json"
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            self._seen = {t.get("id", "") for t in data.get("task_queue", [])}
        except (OSError, json.JSONDecodeError):
            self._seen = set()
        while not self._stop.is_set():
            self._scan()
            self._stop.wait(self.poll_seconds)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def _try_publish(bus: WebSocketEventBus, topic: EventTopic, payload: dict) -> None:
    """Publish from a foreign thread; never raises."""
    try:
        loop = bus.loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(bus.publish(Event(topic=topic, payload=payload)), loop)
    except Exception:
        pass


async def _serve(host: str, port: int, poll: float) -> None:
    bus = WebSocketEventBus()
    bus.set_state_provider(get_swarm_snapshot)
    await bus.serve(host, port)
    watcher = TaskQueueWatcher(bus, poll)
    watcher.start()
    print(f"[ide-bridge] ws://{host}:{port} serving; task watcher poll={poll}s")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        watcher.stop()
        await bus.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS headless IDE bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--poll", type=float, default=5.0, help="task queue poll seconds")
    args = parser.parse_args()
    try:
        asyncio.run(_serve(args.host, args.port, args.poll))
    except KeyboardInterrupt:
        print("[ide-bridge] stopped")


if __name__ == "__main__":
    main()
