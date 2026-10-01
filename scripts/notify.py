"""
NEXUS multi-agent notification webhook.
Posts handoff messages to a shared channel (Slack/Discord/custom).

Usage:
    python scripts/notify.py --agent opencode --task "Fixed SSRF" --status done
    python scripts/notify.py --agent copilot --task "Need review" --status blocked --needs "Antigravity: check domain logic"
"""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent


def main_root() -> Path:
    # Shared rendezvous: every worktree uses the main worktree's state.
    # See scripts/agent_comm.py for the full explanation.
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        gitdir = Path(r.stdout.strip())
        if gitdir.parent.name == "worktrees":
            return gitdir.parent.parent.parent
        return gitdir.parent
    except Exception:
        return REPO_ROOT


load_dotenv(REPO_ROOT / ".env")
STATE_FILE = main_root() / "nexus_state.json"
HANDOFF_FILE = main_root() / "docs" / "HANDOFF.md"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"agents": {}, "tasks": [], "locks": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fire_webhook(url: str, payload: dict) -> None:
    try:
        import httpx

        httpx.post(url, json=payload, timeout=5)
    except Exception:
        pass


def post_to_webhook(agent: str, task: str, status: str, needs: str) -> None:
    # Notifications must never block work: socket timeouts don't cover DNS
    # hangs on all platforms, so the POST runs on a daemon thread with a
    # hard join deadline. Worst case this function costs 10s, never 120s.
    import threading

    webhook_url = os.environ.get("NEXUS_WEBHOOK_URL", "")
    if not webhook_url:
        return
    payload = {
        "agent": agent,
        "task": task,
        "status": status,
        "needs": needs,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    t = threading.Thread(target=_fire_webhook, args=(webhook_url, payload), daemon=True)
    t.start()
    t.join(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS agent notifier")
    parser.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    parser.add_argument("--task", required=True)
    parser.add_argument("--status", default="done", choices=["done", "in-progress", "blocked"])
    parser.add_argument("--needs", default="")
    parser.add_argument("--files", default="")
    args = parser.parse_args()

    state = load_state()
    state["agents"][args.agent] = {
        "status": args.status,
        "current_task": args.task,
        "last_active": datetime.now(UTC).isoformat(),
    }
    save_state(state)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"""
### {timestamp} — {args.agent}
**Task:** {args.task}
**Files:** {args.files or 'none'}
**Status:** {args.status}
**Next:** {'awaiting review' if args.status == 'done' else 'in progress'}
**Needs:** {args.needs or 'none'}
"""
    with open(HANDOFF_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

    post_to_webhook(args.agent, args.task, args.status, args.needs)
    print(f"[{args.agent}] {args.task} -> {args.status}")


if __name__ == "__main__":
    main()
