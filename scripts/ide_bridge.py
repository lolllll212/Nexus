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
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from agent_comm import main_root  # noqa: E402

from nexus.domain.ports.event_bus import Event, EventTopic  # noqa: E402
from nexus.infrastructure.adapters.eventbus.websocket_event_bus import WebSocketEventBus  # noqa: E402

EDITABLE_ROOTS = ("src", "tests", "scripts", "docs", "plugins", "config")


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
    if op == "open":
        path = params.get("path", "")
        if not path:
            return {"ok": False, "error": "path required"}
        r = _run_cmd(["code", "-r", str(main_root() / path)])
        if not r["ok"] and "cannot find" in r["stderr"].lower():
            r = _run_cmd(["cmd", "/c", "start", "", str(main_root() / path)])
        return r
    if op == "run":
        args = params.get("args", [])
        if not args or not isinstance(args, list):
            return {"ok": False, "error": "args list required"}
        return _run_cmd([str(a) for a in args], timeout=float(params.get("timeout", 30)))
    if op == "edit":
        path = params.get("path", "")
        content = params.get("content")
        if not path or content is None:
            return {"ok": False, "error": "path and content required"}
        target = (main_root() / path).resolve()
        try:
            target.relative_to(main_root().resolve())
        except ValueError:
            return {"ok": False, "error": "path escapes repository"}
        if target.parts[0] != str(main_root().resolve()):
            rel = target.relative_to(main_root().resolve())
            if rel.parts and rel.parts[0] not in EDITABLE_ROOTS:
                return {"ok": False, "error": f"root {rel.parts[0]} not editable"}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(target), "bytes": len(str(content))}
    return {"ok": False, "error": f"unknown op {op!r}"}


class TaskQueueWatcher:
    """Polls the shared task queue and pushes task_created events."""

    def __init__(self, bus: WebSocketEventBus, poll_seconds: float) -> None:
        self.bus = bus
        self.poll_seconds = poll_seconds
        self._seen: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _scan(self) -> None:
        state_file = main_root() / "nexus_state.json"
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for t in data.get("task_queue", []):
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

    def _loop(self) -> None:
        # Seed _seen without emitting on startup.
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
