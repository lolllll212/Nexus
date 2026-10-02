"""Plan-first CLI - make a bounded plan BEFORE implementing.

Cost control: steps are capped, each step names its files, and the gate
refuses edits to files no active plan covers. No more open-ended thinking
and mid-set file edits that error out.

Usage:
    python scripts/plan_comm.py plan --agent astra --title "Fix auth 401s" --max-steps 3 \
        --step "merge NEXUS_API_KEYS in conftest|tests/conftest.py" \
        --step "verify auth tests|tests/unit/test_route_authentication.py"
    python scripts/plan_comm.py begin --id plan-fix-auth-401s
    python scripts/plan_comm.py step --id plan-fix-auth-401s --note "merged, tests pass"
    python scripts/plan_comm.py finish --id plan-fix-auth-401s
    python scripts/plan_comm.py check --file tests/conftest.py        # the gate - run BEFORE editing
    python scripts/plan_comm.py list [--status in_progress] [--agent astra]
    python scripts/plan_comm.py show --id <id>
    python scripts/plan_comm.py abandon --id <id> --reason "scope changed"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def board():
    from nexus.infrastructure.adapters.swarm.planning import PlanningBoard

    return PlanningBoard(main_root() / "planning_state.json")


def _parse_steps(args) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    for raw in args.step or []:
        if "|" in raw:
            desc, files = raw.split("|", 1)
            steps.append((desc.strip(), [f.strip() for f in files.split(",") if f.strip()]))
        else:
            steps.append((raw.strip(), []))
    return steps


def cmd_plan(args) -> None:
    steps = _parse_steps(args)
    p, error = board().create_plan(
        title=args.title,
        agent=args.agent,
        steps=steps,
        max_steps=args.max_steps,
    )
    if error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"planned: {p.id} [{p.status}] {p.progress()}")
    for i, s in enumerate(p.steps, 1):
        print(f"  {i}. {s.description}" + (f"  ({', '.join(s.files)})" if s.files else ""))
    print(f"  next: python scripts/plan_comm.py begin --id {p.id}")


def cmd_begin(args) -> None:
    p, error = board().begin(args.id)
    if error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"started: {p.id} [{p.status}] - plan FROZEN; edit only the planned files")
    print("  gate: python scripts/plan_comm.py check --file <path> before every edit")


def cmd_step(args) -> None:
    p, error = board().complete_step(args.id, note=args.note)
    if error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"stepped: {p.id} [{p.status}] {p.progress()}" + (f" - {args.note}" if args.note else ""))


def cmd_finish(args) -> None:
    p, error = board().finish(args.id)
    if error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"finished: {p.id} [{p.status}] - resolve the task with evidence next")


def cmd_check(args) -> None:
    from nexus.infrastructure.adapters.swarm.planning import check_file

    allowed, reason = check_file(args.file, board())
    print(reason)
    sys.exit(0 if allowed else 1)


def cmd_list(args) -> None:
    plans = board().list_plans(status=args.status, agent=args.agent)
    if not plans:
        print("no plans")
        return
    for p in plans:
        print(f"{p.id}  [{p.status}] {p.agent} {p.progress()} - {p.title[:70]}")


def cmd_show(args) -> None:
    p = board().get(args.id)
    if p is None:
        print(f"error: unknown plan {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"id: {p.id} | status: {p.status} | agent: {p.agent} | cap: {p.max_steps} | {p.progress()}")
    if p.abandon_reason:
        print(f"abandoned: {p.abandon_reason}")
    print("---")
    for i, s in enumerate(p.steps, 1):
        mark = "x" if s.done else " "
        files = f"  ({', '.join(s.files)})" if s.files else ""
        note = f" - {s.note}" if s.note else ""
        print(f"  [{mark}] {i}. {s.description}{files}{note}")


def cmd_abandon(args) -> None:
    p, error = board().abandon(args.id, reason=args.reason)
    if error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"abandoned: {p.id}" + (f" - {args.reason}" if args.reason else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS plan-first gate")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="create a bounded plan (draft)")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom", "heal"])
    p.add_argument("--title", required=True)
    p.add_argument(
        "--step", action="append", default=[], help='"description|file1,file2" - repeatable, one per step'
    )
    p.add_argument("--max-steps", type=int, default=5)

    p = sub.add_parser("begin", help="draft -> in_progress (freezes the plan)")
    p.add_argument("--id", required=True)

    p = sub.add_parser("step", help="mark the first not-done step done")
    p.add_argument("--id", required=True)
    p.add_argument("--note", default="")

    p = sub.add_parser("finish", help="in_progress -> done (requires all steps done)")
    p.add_argument("--id", required=True)

    p = sub.add_parser("check", help="THE GATE: is a file covered by an in_progress plan?")
    p.add_argument("--file", required=True)

    p = sub.add_parser("list", help="list plans")
    p.add_argument("--status", default=None, choices=["draft", "in_progress", "done", "abandoned"])
    p.add_argument("--agent", default=None)

    p = sub.add_parser("show", help="print a full plan")
    p.add_argument("--id", required=True)

    p = sub.add_parser("abandon", help="abandon a plan (in_progress plans are frozen)")
    p.add_argument("--id", required=True)
    p.add_argument("--reason", default="")

    args = parser.parse_args()
    {
        "plan": cmd_plan,
        "begin": cmd_begin,
        "step": cmd_step,
        "finish": cmd_finish,
        "check": cmd_check,
        "list": cmd_list,
        "show": cmd_show,
        "abandon": cmd_abandon,
    }[args.command](args)


if __name__ == "__main__":
    main()
