"""
NEXUS multi-agent communication toolkit.

Usage:
    python scripts/agent_comm.py heartbeat --agent opencode
    python scripts/agent_comm.py claim --agent opencode --task-id <id>
    python scripts/agent_comm.py request --agent opencode --task "Need X" --for antigravity
    python scripts/agent_comm.py resolve --agent antigravity --task-id <id>
    python scripts/agent_comm.py status
    python scripts/agent_comm.py board
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "src"))
from nexus.domain.crdt import SwarmState  # noqa: E402


def main_root() -> Path:
    # Every worktree shares ONE coordination state, kept in the main
    # worktree. nexus_state.json is gitignored, so without this each
    # worktree reads/writes its own phantom copy and agents can't see
    # each other. --absolute-git-dir is <main>/.git in the main worktree
    # and <main>/.git/worktrees/<name> in a linked one.
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


STATE_FILE = main_root() / "nexus_state.json"
CRDT_FILE = main_root() / "nexus_crdt.json"
HANDOFF_FILE = main_root() / "docs" / "HANDOFF.md"
ACTIVITY_LOG = main_root() / "agent_activity.jsonl"


def load_crdt() -> SwarmState:
    """Load and synchronize CRDT state via merge-on-read."""
    raw: dict = {}
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    base_state = SwarmState.from_nexus_state(raw, tick=time.time())
    if CRDT_FILE.exists():
        try:
            crdt_data = json.loads(CRDT_FILE.read_text(encoding="utf-8"))
            saved_crdt = SwarmState.from_dict(crdt_data)
            return saved_crdt.merge(base_state)
        except Exception:
            pass
    return base_state


def load_state() -> dict:
    state = {"agents": {}, "task_queue": [], "locks": [], "messages": []}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    crdt = load_crdt()
    state["state_hash"] = crdt.state_hash()
    return state


def save_state(state: dict) -> None:
    crdt = SwarmState.from_nexus_state(state, tick=time.time())
    if CRDT_FILE.exists():
        try:
            old_crdt = SwarmState.from_dict(json.loads(CRDT_FILE.read_text(encoding="utf-8")))
            crdt = old_crdt.merge(crdt)
        except Exception:
            pass
    state["state_hash"] = crdt.state_hash()
    try:
        CRDT_FILE.write_text(json.dumps(crdt.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def now() -> str:
    return datetime.now(UTC).isoformat()


def log_activity(agent: str, action: str, detail: str = "") -> None:
    entry = {"ts": now(), "agent": agent, "action": action, "detail": detail}
    with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_activity(n: int = 15) -> list:
    if not ACTIVITY_LOG.exists():
        return []
    lines = ACTIVITY_LOG.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def cmd_heartbeat(args, state):
    agent = args.agent
    if agent not in state["agents"]:
        print(f"Unknown agent: {agent}")
        sys.exit(1)
    state["agents"][agent]["last_heartbeat"] = now()
    if state["agents"][agent].get("status") == "idle":
        state["agents"][agent]["status"] = "active"
    crdt = load_crdt()
    crdt.record_heartbeat(agent, tick=time.time(), timestamp=now())
    try:
        CRDT_FILE.write_text(json.dumps(crdt.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass
    state["state_hash"] = crdt.state_hash()
    save_state(state)
    log_activity(agent, "heartbeat")
    print(f"[{agent}] heartbeat OK")


def cmd_claim(args, state):
    agent = args.agent
    task_id = args.task_id
    for task in state["task_queue"]:
        if task["id"] == task_id and task["status"] == "pending":
            task["status"] = "claimed"
            task["claimed_by"] = agent
            task["claimed_at"] = now()
            state["agents"][agent]["status"] = "working"
            state["agents"][agent]["current_task"] = task_id
            save_state(state)
            log_activity(agent, "claim", f"{task_id}: {task['description'][:100]}")
            print(f"[{agent}] claimed task {task_id}: {task['description']}")
            return
    print(f"Task {task_id} not found or already claimed")


def cmd_request(args, state):
    agent = args.agent
    target = args.for_agent or "any"
    acceptance = [a.strip() for a in (args.acceptance or "").split(";") if a.strip()]
    task = {
        "id": f"task-{len(state['task_queue']) + 1:03d}",
        "description": args.task,
        "requested_by": agent,
        "for": target,
        "status": "pending",
        "priority": args.priority,
        "files": [f.strip() for f in (args.files or "").split(",") if f.strip()],
        "acceptance": acceptance,
        "evidence": None,
        "verified": False,
        "created_at": now(),
        "claimed_by": None,
        "claimed_at": None,
        "resolved_at": None,
    }
    state["task_queue"].append(task)
    save_state(state)
    log_activity(agent, "request", f"{task['id']} for {target}: {args.task[:100]}")
    print(f"[{agent}] requested: {args.task} (id={task['id']}, for={target}, priority={args.priority})")
    if acceptance:
        print(f"  acceptance: {'; '.join(acceptance)}")


def cmd_resolve(args, state):
    agent = args.agent
    task_id = args.task_id
    for task in state["task_queue"]:
        if task["id"] == task_id:
            if not args.evidence:
                print("Resolve refused: --evidence is required (test output proving the fix).")
                print('Example: --evidence "pytest tests/eval/test_x.py -q: 12 passed"')
                sys.exit(1)
            task["status"] = "resolved"
            task["resolved_at"] = now()
            task["evidence"] = args.evidence
            task["verified"] = False
            state["agents"][agent]["status"] = "idle"
            state["agents"][agent]["current_task"] = None
            save_state(state)
            log_activity(agent, "resolve", f"{task_id}: {args.evidence[:100]}")
            print(f"[{agent}] resolved task {task_id} (pending CEO verification)")
            print(f"  evidence: {args.evidence}")
            return
    print(f"Task {task_id} not found")


def heartbeat_age(hb: str | None) -> str:
    if not hb:
        return "never"
    try:
        delta = (datetime.now(UTC) - datetime.fromisoformat(hb)).total_seconds()
        if delta < 60:
            return f"{int(delta)}s ago"
        if delta < 3600:
            return f"{int(delta // 60)}m ago"
        return f"{int(delta // 3600)}h ago STALE"
    except ValueError:
        return hb


def cmd_status(args, state):
    state_hash = state.get("state_hash") or load_crdt().state_hash()
    print(f"=== Swarm Status (CRDT state_hash: {state_hash}) ===")
    print("=== Agent Status ===")
    for name, info in state["agents"].items():
        hb = heartbeat_age(info.get("last_heartbeat"))
        print(f"  {name:12s} | {info['status']:10s} | {info.get('current_task') or '-':30s} | hb: {hb}")
    print()
    print("=== Task Queue ===")
    for task in state["task_queue"]:
        flag = " [UNVERIFIED]" if task["status"] == "resolved" and not task.get("verified") else ""
        print(
            f"  [{task['id']}] {task['status']:8s} | {task['requested_by']:12s} -> {task['for']:12s} | {task['description'][:60]}{flag}"
        )
    print()
    print("=== Scoreboard ===")
    for name in state["agents"]:
        claimed = sum(1 for t in state["task_queue"] if t.get("claimed_by") == name)
        resolved = sum(
            1 for t in state["task_queue"] if t.get("claimed_by") == name and t["status"] == "resolved"
        )
        verified = sum(1 for t in state["task_queue"] if t.get("claimed_by") == name and t.get("verified"))
        print(f"  {name:12s} | claimed: {claimed} | resolved: {resolved} | verified: {verified}")
    print()
    print("=== Active Locks ===")
    for lock in state["locks"]:
        print(f"  {lock['file']} -> {lock['agent']} (since {lock['since']})")


def cmd_crdt(args, state):
    crdt = load_crdt()
    if getattr(args, "merge_file", None):
        path = Path(args.merge_file)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))
        if "heartbeats" in data:
            other = SwarmState.from_dict(data)
        else:
            other = SwarmState.from_nexus_state(data, tick=time.time())
        crdt = crdt.merge(other)
        merged_state = crdt.to_nexus_state()
        merged_state["messages"] = state.get("messages", [])
        save_state(merged_state)
        print(f"Merged successfully. New state_hash: {crdt.state_hash()}")
        return

    print(f"=== Swarm CRDT State (state_hash: {crdt.state_hash()}) ===")
    print("Heartbeats (G-Counter):")
    for ag, count in sorted(crdt.heartbeats.counts.items()):
        print(f"  {ag:12s}: {count}")
    print()
    print("Active Tasks (OR-Set):")
    for tid in sorted(crdt.task_membership.read()):
        t = crdt.tasks.get(tid)
        st = t.status.value if t else "unknown"
        print(f"  [{tid}] status={st}")
    print()
    print("Active Locks (OR-Set):")
    for lk in sorted(crdt.active_locks.read()):
        print(f"  {lk}")


def cmd_verify(args, state):
    agent = args.agent
    task_id = args.task_id
    for task in state["task_queue"]:
        if task["id"] == task_id:
            if task["status"] != "resolved":
                print(f"Cannot verify: task is {task['status']}, not resolved.")
                sys.exit(1)
            if args.passed:
                task["verified"] = True
                save_state(state)
                log_activity(agent, "verify", f"{task_id}: PASS")
                print(f"[{agent}] verified task {task_id} — closed.")
            else:
                task["status"] = "pending"
                task["claimed_by"] = None
                task["evidence"] = None
                save_state(state)
                log_activity(agent, "verify", f"{task_id}: FAIL — {args.note}")
                print(f"[{agent}] verification FAILED for {task_id} — reopened.")
                print(f"  note: {args.note}")
            return
    print(f"Task {task_id} not found")


def cmd_board(args, state):
    if HANDOFF_FILE.exists():
        print(HANDOFF_FILE.read_text(encoding="utf-8"))
    else:
        print("No handoff board found.")


PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def cmd_ask(args, state):
    agent = args.agent
    msg = {
        "id": f"msg-{int(time.time())}-{uuid.uuid4().hex[:4]}",
        "from": agent,
        "to": "ceo",
        "kind": args.kind,
        "text": args.text,
        "status": "open",
        "created_at": now(),
        "reply": None,
    }
    state.setdefault("messages", []).append(msg)
    save_state(state)
    log_activity(agent, "ask", f"{msg['id']} [{args.kind}]: {args.text[:80]}")
    print(f"[{agent}] sent to CEO: {msg['id']} [{args.kind}]")
    print(f"  {args.text[:200]}")


def cmd_inbox(args, state):
    open_msgs = [m for m in state.get("messages", []) if m["status"] == "open"]
    if not open_msgs:
        print("Inbox empty.")
        return
    for m in open_msgs:
        print(f"[{m['id']}] {m['from']} -> {m['to']} [{m['kind']}] {m['created_at'][:19]}")
        print(f"  {m['text'][:250]}")


def cmd_reply(args, state):
    for m in state.get("messages", []):
        if m["id"] == args.msg_id:
            if m["status"] != "open":
                print(f"{args.msg_id} already answered.")
                return
            m["status"] = "answered"
            m["reply"] = args.text
            m["answered_at"] = now()
            save_state(state)
            log_activity(args.agent, "reply", f"{args.msg_id}: {args.text[:80]}")
            print(f"[{args.agent}] replied to {args.msg_id}")
            return
    print(f"Message {args.msg_id} not found.")


def cmd_next(args, state):
    agent = args.agent
    mine = [t for t in state["task_queue"] if t["status"] == "pending" and t.get("for") == agent]
    if not mine:
        print(f"[{agent}] queue empty — nothing to do.")
        return
    mine.sort(key=lambda t: (PRIORITY_RANK.get(t.get("priority", "medium"), 2), t.get("created_at", "")))
    t = mine[0]
    print(f"[{agent}] next task: {t['id']} (priority={t.get('priority', 'medium')})")
    print(f"  what: {t['description'][:300]}")
    if t.get("files"):
        print(f"  files: {', '.join(t['files'][:8])}")
    if t.get("acceptance"):
        print(f"  acceptance: {'; '.join(t['acceptance'])}")
    print(f"  claim it: python scripts/agent_comm.py claim --agent {agent} --task-id {t['id']}")


OWNER_MAP = {
    "astra": ["src/nexus/application/", "tests/eval/", "docs/"],
    "tron": ["src/nexus/domain/", "plugins/", "tests/unit/"],
    "xenom": ["src/nexus/infrastructure/", "web/", "config/", "tests/integration/"],
}


def owner_of(path: str) -> str | None:
    p = path.replace("\\", "/")
    for owner, prefixes in OWNER_MAP.items():
        if any(p.startswith(pref) or p == pref.rstrip("/") for pref in prefixes):
            return owner
    return None


def cmd_plan(args, state):
    try:
        plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Cannot read plan file: {e}")
        sys.exit(1)

    goal = plan.get("goal", "")
    items = plan.get("tasks", [])
    if not goal or not items:
        print("Plan needs 'goal' and non-empty 'tasks'.")
        sys.exit(1)

    errors, warnings = [], []
    seen_files: dict[str, str] = {}
    for i, item in enumerate(items):
        who = item.get("for", "")
        files = item.get("files", [])
        if who not in OWNER_MAP:
            errors.append(f"task {i}: unknown agent '{who}'")
            continue
        for f in files:
            if f in seen_files:
                errors.append(
                    f"task {i}: file '{f}' also claimed by task for {seen_files[f]} — scopes must not overlap"
                )
            else:
                seen_files[f] = who
            if owner_of(f) not in (who, None):
                warnings.append(f"task {i}: file '{f}' is {owner_of(f)}'s area, not {who}'s")

    if errors:
        print("PLAN REJECTED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    for w in warnings:
        print(f"WARNING: {w}")

    if args.check_only:
        print(f"PLAN OK: '{goal}' — {len(items)} tasks, no overlap.")
        return

    plan_id = f"plan-{len(state.get('plans', [])) + 1:03d}"
    task_ids = []
    for item in items:
        task = {
            "id": f"task-{len(state['task_queue']) + 1:03d}-{plan_id}",
            "description": item.get("task", ""),
            "requested_by": args.agent,
            "for": item.get("for"),
            "status": "pending",
            "priority": item.get("priority", "medium"),
            "files": item.get("files", []),
            "acceptance": item.get("acceptance", []),
            "evidence": None,
            "verified": False,
            "plan_id": plan_id,
            "created_at": now(),
            "claimed_by": None,
            "claimed_at": None,
            "resolved_at": None,
        }
        state["task_queue"].append(task)
        task_ids.append(task["id"])
        log_activity(args.agent, "request", f"{task['id']} for {task['for']}: {task['description'][:80]}")

    state.setdefault("plans", []).append(
        {
            "id": plan_id,
            "goal": goal,
            "tasks": task_ids,
            "status": "active",
            "created_by": args.agent,
            "created_at": now(),
        }
    )
    save_state(state)
    print(f"PLAN {plan_id} DISPATCHED: '{goal}'")
    for tid in task_ids:
        print(f"  - {tid}")


def cmd_plan_status(args, state):
    plan = next((p for p in state.get("plans", []) if p["id"] == args.plan_id), None)
    if not plan:
        print(f"Plan {args.plan_id} not found.")
        sys.exit(1)
    print(f"PLAN {plan['id']}: {plan['goal']} [{plan['status']}]")
    by_id = {t["id"]: t for t in state["task_queue"]}
    done = 0
    for tid in plan["tasks"]:
        t = by_id.get(tid)
        if not t:
            print(f"  [{tid}] missing")
            continue
        who = t.get("claimed_by") or t["for"]
        mark = "OK" if t.get("verified") or t["status"] == "resolved" else ".."
        if mark == "OK":
            done += 1
        print(f"  [{mark}] {tid} {t['status']:8s} | {who:8s} | {t['description'][:55]}")
    print(f"{done}/{len(plan['tasks'])} subtasks done")


def cmd_progress(args, state):
    agent = args.agent
    if agent not in state["agents"]:
        print(f"Unknown agent: {agent}")
        sys.exit(1)
    state["agents"][agent]["status"] = "working"
    state["agents"][agent]["current_task"] = args.doing
    state["agents"][agent]["last_heartbeat"] = now()
    save_state(state)
    log_activity(agent, "progress", args.doing)
    print(f"[{agent}] now doing: {args.doing}")


def render_dashboard(state) -> str:
    lines = []
    ts = datetime.now(UTC).strftime("%H:%M:%S UTC")
    lines.append(f"NEXUS LIVE DASHBOARD — {ts}")
    lines.append("=" * 60)
    lines.append("AGENTS:")
    for name, info in state["agents"].items():
        task = info.get("current_task") or "-"
        hb = heartbeat_age(info.get("last_heartbeat"))
        lines.append(f"  {name:8s} | {info.get('status','?'):8s} | {task[:35]:35s} | {hb}")
    lines.append("")
    lines.append("TASK QUEUE:")
    for task in state["task_queue"]:
        if task["status"] == "resolved" and task.get("verified"):
            continue
        who = task.get("claimed_by") or task["for"]
        flag = " [NEEDS VERIFY]" if task["status"] == "resolved" else ""
        lines.append(f"  [{task['id']}] {task['status']:8s} | {who:8s} | {task['description'][:50]}{flag}")
    lines.append("")
    open_msgs = [m for m in state.get("messages", []) if m["status"] == "open"]
    if open_msgs:
        lines.append(f"INBOX ({len(open_msgs)} open):")
        for m in open_msgs[-5:]:
            lines.append(f"  [{m['id']}] {m['from']} [{m['kind']}] {m['text'][:55]}")
        lines.append("")
    lines.append("RECENT ACTIVITY:")
    for entry in read_activity(10):
        lines.append(
            f"  {entry['ts'][11:19]} {entry['agent']:8s} {entry['action']:9s} {entry.get('detail','')[:60]}"
        )
    return "\n".join(lines)


def cmd_watch(args, state):
    interval = args.interval
    try:
        while True:
            state = load_state()
            print("\033[2J\033[H", end="")
            print(render_dashboard(state))
            print(f"\nRefreshing every {interval}s — Ctrl+C to stop")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="NEXUS agent communication")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("heartbeat")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])

    p = sub.add_parser("claim")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--task-id", required=True)

    p = sub.add_parser("request")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--task", required=True)
    p.add_argument("--for-agent", dest="for_agent", choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--priority", default="medium", choices=["critical", "high", "medium", "low"])
    p.add_argument("--files", default="", help="Comma-separated files in scope")
    p.add_argument("--acceptance", default="", help="Semicolon-separated acceptance criteria")

    p = sub.add_parser("resolve")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--task-id", required=True)
    p.add_argument("--evidence", default="", help="REQUIRED: test output proving the fix")

    p = sub.add_parser("verify")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--task-id", required=True)
    p.add_argument("--passed", action="store_true", help="Verification passed")
    p.add_argument("--note", default="", help="Required if not passed: why it failed")

    p = sub.add_parser("progress")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--doing", required=True, help="What the agent is currently working on")

    p = sub.add_parser("watch")
    p.add_argument("--interval", type=int, default=5, help="Refresh seconds")

    p = sub.add_parser("plan")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--plan-file", required=True, help="JSON plan file to validate + dispatch")
    p.add_argument("--check-only", action="store_true", help="Validate without dispatching")

    p = sub.add_parser("plan-status")
    p.add_argument("--plan-id", required=True)

    p = sub.add_parser("next")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])

    p = sub.add_parser("ask")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--kind", required=True, choices=["question", "blocker", "escalation", "handoff"])
    p.add_argument("--text", required=True, help="The message to the CEO")

    sub.add_parser("inbox")

    p = sub.add_parser("reply")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--msg-id", required=True)
    p.add_argument("--text", required=True, help="The reply")

    sub.add_parser("status")
    sub.add_parser("board")

    p = sub.add_parser("crdt")
    p.add_argument("--merge-file", help="Path to state file to merge into local state")

    args = parser.parse_args()
    state = load_state()

    cmds = {
        "heartbeat": cmd_heartbeat,
        "claim": cmd_claim,
        "request": cmd_request,
        "resolve": cmd_resolve,
        "verify": cmd_verify,
        "progress": cmd_progress,
        "watch": cmd_watch,
        "plan": cmd_plan,
        "plan-status": cmd_plan_status,
        "next": cmd_next,
        "ask": cmd_ask,
        "inbox": cmd_inbox,
        "reply": cmd_reply,
        "status": cmd_status,
        "board": cmd_board,
        "crdt": cmd_crdt,
    }
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    cmds[args.command](args, state)


if __name__ == "__main__":
    main()
