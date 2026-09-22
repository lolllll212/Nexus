"""NEXUS command-line interface.

Entry points:
    nexus serve                     Run the FastAPI server
    nexus dream                     Run a dreaming cycle (one-shot)
    nexus train <subcommand> ...    Coding-training CLI (add/list/search/...)

Installed as the `nexus` console script (see pyproject.toml [project.scripts])
and importable via `python -m nexus`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import List, Optional


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "nexus.infrastructure.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


async def _run_dream(local: bool = False) -> dict:
    from nexus.infrastructure.di.container import Config, Container

    config = Config()
    if local:
        config.infra_backend = "memory"

    container = Container(config)
    await container.start()
    try:
        from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase

        result = await container.dream_session.run(tenant_id="default")
        report = {
            "session_id": result.session_id,
            "compression": bool(result.compression and result.compression.semantic_fragments_created),
            "pruning": bool(result.pruning and result.pruning.pruned),
            "simulation": bool(result.simulation and result.simulation.solutions_verified),
            "consolidation": bool(result.consolidation and result.consolidation.consolidated),
            "recall_probes": result.recall_probes,
            "recall_hit_rate_before": result.recall_hit_rate_before,
            "recall_hit_rate_after": result.recall_hit_rate_after,
            "recall_delta": result.recall_delta,
            "duration_seconds": result.duration_seconds,
            "next_dream_at": DreamSessionUseCase.next_dream_time().isoformat(),
        }
        return report
    finally:
        await container.shutdown()


def _cmd_dream(args: argparse.Namespace) -> None:
    local = bool(getattr(args, "local", False))
    try:
        report = asyncio.run(_run_dream(local=local))
    except Exception as e:
        if not local:
            print(
                f"dream failed against external infra ({e}); retrying with in-memory backend...",
                file=sys.stderr,
            )
            try:
                report = asyncio.run(_run_dream(local=True))
            except Exception as e2:
                print(f"dream failed: {e2}", file=sys.stderr)
                raise SystemExit(1)
        else:
            print(f"dream failed: {e}", file=sys.stderr)
            raise SystemExit(1)
    print(json.dumps(report, indent=2, default=str))


def _cmd_train(args: argparse.Namespace) -> None:
    from nexus.training import cli as training_cli

    rest: List[str] = getattr(args, "command", [])
    if rest:
        training_cli.main(rest)
    else:
        training_cli.main(["--help"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description="NEXUS - a new kind of brain.")
    sub = parser.add_subparsers(dest="verb")

    p_serve = sub.add_parser("serve", help="Run the FastAPI server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    p_dream = sub.add_parser("dream", help="Run a single dreaming cycle")
    p_dream.add_argument(
        "--local",
        action="store_true",
        help="Use the in-memory backend (no Redis/Qdrant/Neo4j needed). "
        "Default: external infra, with automatic fallback if it is unreachable.",
    )
    p_dream.set_defaults(func=_cmd_dream)

    p_train = sub.add_parser("train", help="Coding-training CLI (add/list/search/...)")
    p_train.add_argument(
        "command", nargs=argparse.REMAINDER, help="Sub-command forwarded to nexus.training.cli"
    )
    p_train.set_defaults(func=_cmd_train)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(0)
    args.func(args)


if __name__ == "__main__":
    main()
