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


def _cmd_eval(args: argparse.Namespace) -> None:
    from nexus.eval.__main__ import main as eval_main

    eval_args = ["--output", args.output, "--min-pass-rate", str(args.min_pass_rate)]
    if getattr(args, "base_url", None):
        eval_args += ["--base-url", args.base_url]
    if getattr(args, "model", None):
        eval_args += ["--model", args.model]
    if getattr(args, "api_key", None):
        eval_args += ["--api-key", args.api_key]
    raise SystemExit(eval_main(eval_args))


def _cmd_train(args: argparse.Namespace) -> None:
    from nexus.training import cli as training_cli

    rest: List[str] = getattr(args, "command", [])
    if rest:
        training_cli.main(rest)
    else:
        training_cli.main(["--help"])


def _cmd_backup(args: argparse.Namespace) -> None:
    import asyncio

    from nexus.infrastructure.backup import BackupManager, Neo4jBackup, QdrantBackup
    from nexus.infrastructure.di.container import Config

    async def _run() -> dict:
        cfg = Config()
        qdrant = None
        neo4j = None
        if cfg.infra_backend != "memory":
            qdrant = QdrantBackup(host=cfg.qdrant_host, port=cfg.qdrant_port)
            neo4j = Neo4jBackup(uri=cfg.neo4j_uri, user=cfg.neo4j_user, password=cfg.neo4j_password)
        tenants = [t.strip() for t in (args.tenant or "").split(",") if t.strip()] or ["default"]
        mgr = BackupManager(
            qdrant=qdrant,
            neo4j=neo4j,
            retain_snapshots=args.retain,
            dump_dir=args.output_dir,
        )
        combined = {"timestamp": "", "qdrant_snapshots": [], "qdrant_pruned": [], "neo4j": None, "errors": []}
        for tenant in tenants:
            res = await mgr.run(tenant_id=tenant)
            combined["timestamp"] = res.timestamp
            combined["qdrant_snapshots"].extend([s.__dict__ for s in res.qdrant_snapshots])
            combined["qdrant_pruned"].extend(res.qdrant_pruned)
            if res.neo4j is not None:
                combined["neo4j"] = res.neo4j.__dict__
            combined["errors"].extend(res.errors)
        return combined

    result = asyncio.run(_run())
    print(json.dumps(result, indent=2, default=str))
    if result["errors"] and not result["qdrant_snapshots"] and result["neo4j"] is None:
        raise SystemExit(1)


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

    p_eval = sub.add_parser("eval", help="Run the golden-set eval against the live LLM")
    p_eval.add_argument(
        "--base-url", default=None, help="OpenAI-compatible base URL (env NEXUS_EVAL_BASE_URL)"
    )
    p_eval.add_argument("--model", default=None, help="Model id (env NEXUS_EVAL_MODEL)")
    p_eval.add_argument("--api-key", default=None, help="API key (env NEXUS_EVAL_API_KEY)")
    p_eval.add_argument("--output", default=".", help="Directory for eval-report.json/.html")
    p_eval.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.0,
        help="Exit non-zero if pass rate is below this threshold.",
    )
    p_eval.set_defaults(func=_cmd_eval)

    p_train = sub.add_parser("train", help="Coding-training CLI (add/list/search/...)")
    p_train.add_argument(
        "command", nargs=argparse.REMAINDER, help="Sub-command forwarded to nexus.training.cli"
    )
    p_train.set_defaults(func=_cmd_train)

    p_backup = sub.add_parser("backup", help="Snapshot Qdrant + dump Neo4j (DR)")
    p_backup.add_argument("--output-dir", default="backups", help="Directory for Neo4j JSONL dumps")
    p_backup.add_argument("--retain", type=int, default=7, help="Qdrant snapshots to retain (newest N)")
    p_backup.add_argument("--tenant", default="", help="Comma-separated tenants (default: all/default)")
    p_backup.set_defaults(func=_cmd_backup)

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
