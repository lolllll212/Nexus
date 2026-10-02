"""Consensus CLI - critique-and-consensus protocol for code changes.

No patch is written to disk without consensus: one agent drafts, the others
review, the CEO casts the deciding vote.

Usage:
    python scripts/consensus.py propose --author xenom --title "Fix SSRF" --file draft.patch --files src/a.py
    python scripts/consensus.py review --id <pid> --agent astra --verdict approve --note "lgtm"
    python scripts/consensus.py vote   --id <pid> --agent ceo --choice yes
    python scripts/consensus.py verdict --id <pid>
    python scripts/consensus.py list [--status in_review]
    python scripts/consensus.py show --id <pid>
    python scripts/consensus.py apply --id <pid>      # ONLY after approved
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
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


def protocol():
    from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

    return ConsensusProtocol(main_root() / "consensus_state.json")


def _load_draft(args) -> str:
    if args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            sys.exit(1)
        return p.read_text(encoding="utf-8", errors="replace")
    if args.draft:
        return args.draft
    print("error: --file or --draft required", file=sys.stderr)
    sys.exit(1)


def cmd_propose(args) -> None:
    draft = _load_draft(args)
    files = [f.strip() for f in (args.files or "").split(",") if f.strip()]
    p = protocol().propose(
        title=args.title,
        author=args.author,
        draft=draft,
        files=files,
        created_at=datetime.now(UTC).isoformat(),
    )
    print(f"proposed: {p.id} [{p.status}]")
    print(f"  next: python scripts/consensus.py review --id {p.id} --agent astra --verdict approve")


def cmd_review(args) -> None:
    p = protocol().review(args.id, args.agent, args.verdict, args.note)
    if p is None:
        print(f"error: unknown proposal {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"reviewed by {args.agent}: {p.status} - {p.verdict_reason or p.status}")


def cmd_vote(args) -> None:
    p = protocol().vote(args.id, args.agent, args.choice)
    if p is None:
        print(f"error: unknown proposal {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"vote {args.agent}={args.choice}: {p.status} - {p.verdict_reason or p.status}")


def cmd_verdict(args) -> None:
    result = protocol().resolve(args.id)
    if result is None:
        print(f"error: unknown proposal {args.id}", file=sys.stderr)
        sys.exit(1)
    status, reason = result
    print(f"{args.id}: {status} - {reason}")


def cmd_list(args) -> None:
    for p in protocol().list_proposals(status=args.status):
        print(f"{p.id}  [{p.status}] {p.author}: {p.title[:70]} (tick {p.tick})")


def cmd_show(args) -> None:
    p = protocol().get(args.id)
    if p is None:
        print(f"error: unknown proposal {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"id: {p.id} | status: {p.status} | author: {p.author} | files: {', '.join(p.files) or '-'}")
    print(f"reviews: {p.reviews or '-'}")
    print(f"votes: {p.votes or '-'}")
    print(f"reason: {p.verdict_reason or '-'}")
    print("---")
    print(p.draft)


def cmd_apply(args) -> None:
    from nexus.infrastructure.adapters.swarm.consensus import CEO

    proto = protocol()
    p = proto.get(args.id)
    if p is None:
        print(f"error: unknown proposal {args.id}", file=sys.stderr)
        sys.exit(1)
    status, reason = proto.resolve(args.id)
    if status != "approved":
        print(
            f"error: not approved ({status} - {reason}); consensus required before writing to disk",
            file=sys.stderr,
        )
        sys.exit(1)
    # The draft is a unified diff; apply it with git apply --check first.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
        f.write(p.draft)
        patch_path = f.name
    check = subprocess.run(
        ["git", "apply", "--check", patch_path], capture_output=True, text=True, cwd=str(main_root())
    )
    if check.returncode != 0:
        print(f"error: patch does not apply cleanly:\n{check.stderr}", file=sys.stderr)
        sys.exit(1)
    apply_r = subprocess.run(
        ["git", "apply", patch_path], capture_output=True, text=True, cwd=str(main_root())
    )
    if apply_r.returncode != 0:
        print(f"error: git apply failed:\n{apply_r.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"applied: {p.id} ({', '.join(p.files) or 'see patch'}) - consensus {status} ({reason})")
    print(f"ceo: {p.votes.get(CEO, 'n/a')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS consensus protocol")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose", help="draft a code-change proposal")
    p.add_argument("--author", required=True, choices=["ceo", "astra", "tron", "xenom", "heal"])
    p.add_argument("--title", required=True)
    p.add_argument("--draft", default="")
    p.add_argument("--file", default="", help="read the draft (unified diff) from a file")
    p.add_argument("--files", default="", help="comma-separated files the patch touches")

    p = sub.add_parser("review", help="review a proposal")
    p.add_argument("--id", required=True)
    p.add_argument("--agent", required=True, choices=["astra", "tron", "xenom"])
    p.add_argument("--verdict", required=True, choices=["approve", "request_changes"])
    p.add_argument("--note", default="")

    p = sub.add_parser("vote", help="cast a vote (CEO decides)")
    p.add_argument("--id", required=True)
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom"])
    p.add_argument("--choice", required=True, choices=["yes", "no", "abstain"])

    p = sub.add_parser("verdict", help="current deterministic outcome")
    p.add_argument("--id", required=True)

    p = sub.add_parser("list", help="list proposals")
    p.add_argument("--status", default=None, choices=["in_review", "approved", "rejected"])

    p = sub.add_parser("show", help="print a full proposal")
    p.add_argument("--id", required=True)

    p = sub.add_parser("apply", help="apply an approved patch to the working tree")
    p.add_argument("--id", required=True)

    args = parser.parse_args()
    {
        "propose": cmd_propose,
        "review": cmd_review,
        "vote": cmd_vote,
        "verdict": cmd_verdict,
        "list": cmd_list,
        "show": cmd_show,
        "apply": cmd_apply,
    }[args.command](args)


if __name__ == "__main__":
    main()
