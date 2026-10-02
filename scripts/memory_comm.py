"""Agent memory CLI - content-addressable store for multi-agent coordination.

Agents append summaries/diffs once and pull only what they need by relevance,
instead of passing full context between loops (token savings up to ~70%).

Usage:
    python scripts/memory_comm.py put --agent astra --kind report --text "..." --tags ci,ruff
    python scripts/memory_comm.py put --agent xenom --kind patch --file diffs/001.patch --refs <chunk-id>
    python scripts/memory_comm.py query --q "ci red docker" --k 5
    python scripts/memory_comm.py diff --from-id <id> --to-id <id>
    python scripts/memory_comm.py latest --kind report
    python scripts/memory_comm.py show --id <id>
    python scripts/memory_comm.py prune --max 500
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main_root() -> Path:
    # Shared rendezvous: every worktree uses the main worktree's store.
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


def store():
    from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore

    return AgentMemoryStore(main_root() / "agent_memory.json")


def cmd_put(args) -> None:
    text = args.text or ""
    if args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            sys.exit(1)
        text = p.read_text(encoding="utf-8", errors="replace")
    if not text:
        print("error: nothing to store (--text or --file required)", file=sys.stderr)
        sys.exit(1)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    refs = [r.strip() for r in (args.refs or "").split(",") if r.strip()]
    chunk, created = store().put(
        agent=args.agent,
        kind=args.kind,
        text=text,
        tags=tags,
        refs=refs,
        created_at=datetime.now(UTC).isoformat(),
    )
    if created:
        print(f"stored: {chunk.id} (tick {chunk.tick})")
    else:
        print(f"duplicate: {chunk.id} already stored (idempotent)")


def cmd_query(args) -> None:
    results = store().query(args.q, k=args.k, kind=args.kind, agent=args.agent)
    if not results:
        print("no matches")
        return
    for chunk, score in results:
        first = chunk.text.strip().splitlines()[0][:100] if chunk.text.strip() else ""
        print(f"{chunk.id}  {score:.3f}  [{chunk.kind}] {chunk.agent} tick={chunk.tick}")
        print(f"    {first}")


def cmd_show(args) -> None:
    chunk = store().get(args.id)
    if chunk is None:
        print(f"error: unknown id {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"id: {chunk.id} | tick: {chunk.tick} | agent: {chunk.agent} | kind: {chunk.kind}")
    print(f"tags: {', '.join(chunk.tags) or '-'} | refs: {', '.join(chunk.refs) or '-'}")
    print(f"created: {chunk.created_at or '-'}")
    print("---")
    print(chunk.text)


def cmd_diff(args) -> None:
    d = store().diff(args.from_id, args.to_id)
    if d is None:
        print("error: unknown id(s)", file=sys.stderr)
        sys.exit(1)
    print(d if d else "(no textual difference)")


def cmd_latest(args) -> None:
    for chunk in store().latest(kind=args.kind, n=args.n):
        first = chunk.text.strip().splitlines()[0][:100] if chunk.text.strip() else ""
        print(f"{chunk.id}  [{chunk.kind}] {chunk.agent} tick={chunk.tick}  {first}")


def cmd_prune(args) -> None:
    removed = store().prune(args.max)
    print(f"pruned {removed} chunk(s); {args.max} newest kept")


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS agent memory (content-addressable)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("put", help="append a chunk (idempotent by content)")
    p.add_argument("--agent", required=True, choices=["ceo", "astra", "tron", "xenom", "heal", "router"])
    p.add_argument(
        "--kind", required=True, choices=["report", "patch", "decision", "context", "note", "error"]
    )
    p.add_argument("--text", default="")
    p.add_argument("--file", default="", help="store a file's content instead of --text")
    p.add_argument("--tags", default="")
    p.add_argument("--refs", default="", help="comma-separated chunk ids this corrects/extends")

    p = sub.add_parser("query", help="top-k relevant chunks (TF-IDF)")
    p.add_argument("--q", required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--kind", default=None)
    p.add_argument("--agent", default=None)

    p = sub.add_parser("show", help="print a full chunk")
    p.add_argument("--id", required=True)

    p = sub.add_parser("diff", help="unified diff between two chunks")
    p.add_argument("--from-id", required=True)
    p.add_argument("--to-id", required=True)

    p = sub.add_parser("latest", help="most recent chunks")
    p.add_argument("--kind", default=None)
    p.add_argument("--n", type=int, default=10)

    p = sub.add_parser("prune", help="keep the newest --max chunks")
    p.add_argument("--max", type=int, default=500)

    args = parser.parse_args()
    {
        "put": cmd_put,
        "query": cmd_query,
        "show": cmd_show,
        "diff": cmd_diff,
        "latest": cmd_latest,
        "prune": cmd_prune,
    }[args.command](args)


if __name__ == "__main__":
    main()
