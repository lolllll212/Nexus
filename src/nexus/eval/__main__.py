"""`python -m nexus.eval` - run the golden set against a real brain.

Connects a real Container in memory mode (no Redis/Qdrant/Neo4j) with a real
LLM and the real extended tool handlers, so the nightly eval measures the
actual ReAct loop + tool execution, not fakes.

Usage:
    python -m nexus.eval [--base-url URL] [--model MODEL] [--api-key KEY]
                         [--output PATH] [--min-pass-rate 0.8]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from nexus.eval.harness import EvalRunner, GOLDEN_SET, write_report_html


def _build_live_runner() -> "object":
    """Container in memory mode + real LLM + real extended tools."""
    from nexus.infrastructure.di.container import Config, Container

    base_url = os.getenv("NEXUS_EVAL_BASE_URL") or os.getenv("NEXUS_LLM_BASE_URL")
    model = os.getenv("NEXUS_EVAL_MODEL") or "qwen2.5-coder-7b-instruct"
    api_key = os.getenv("NEXUS_EVAL_API_KEY") or "local-no-key"

    config = Config(
        infra_backend="memory",
        llm_base_url=base_url,
        llm_model=model,
        openai_api_key=api_key,
        sandbox_backend="subprocess",
    )
    container = Container(config)

    # The eval runner only needs use-case + llm; keep container references
    # alive on the runner object so the event loop etc. stay wired.
    runner = EvalRunner(container_factory=lambda: _EvalHarnessShim(container))
    return runner


class _EvalHarnessShim:
    """Adapts the live Container to the (minimal) EvalRunner interface."""

    def __init__(self, container) -> None:
        self.container = container
        self.llm = container.llm
        self.process_message = container.process_message


async def _run(root: Path) -> tuple[EvalRunner, Path]:
    runner = _build_live_runner()
    for case in GOLDEN_SET:
        runner.results.append(await runner.run_case(case))

    root.mkdir(parents=True, exist_ok=True)
    (root / "eval-report.json").write_text(json.dumps(runner.to_json(), indent=2))
    write_report_html(runner.results, root / "eval-report.html")
    return runner, root / "eval-report.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nexus.eval", description="Run the NEXUS golden-set eval against a live LLM."
    )
    parser.add_argument("--base-url", default=os.getenv("NEXUS_EVAL_BASE_URL"))
    parser.add_argument("--model", default=os.getenv("NEXUS_EVAL_MODEL"))
    parser.add_argument("--api-key", default=os.getenv("NEXUS_EVAL_API_KEY"))
    parser.add_argument("--output", default=".", help="Directory for eval-report.json/.html")
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=float(os.getenv("NEXUS_EVAL_MIN_PASS_RATE", "0.0")),
        help="Exit non-zero if pass rate is below this (0.0 = never fail on rate).",
    )
    args = parser.parse_args(argv)

    if args.base_url:
        os.environ["NEXUS_EVAL_BASE_URL"] = args.base_url
    if args.model:
        os.environ["NEXUS_EVAL_MODEL"] = args.model
    if args.api_key:
        os.environ["NEXUS_EVAL_API_KEY"] = args.api_key

    runner, html_path = asyncio.run(_run(Path(args.output)))
    print(runner.report())
    print(f"HTML report: {html_path}")

    if runner.pass_rate < args.min_pass_rate:
        print(
            f"Pass rate {runner.pass_rate:.1%} below threshold {args.min_pass_rate:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())