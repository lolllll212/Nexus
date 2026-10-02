"""Self-healing test loop - targeted patch instructions, not history dumps.

Runs pytest, parses failures, and for each failing test pipes ONLY the
traceback plus the failing test's source and the touched module's relevant
chunk to the router (low-complexity -> local Ollama models on the RTX 3050)
as a targeted patch instruction. The resulting patch enters the consensus
queue as a draft - never written to disk without review (Zenom drafts, Astra
reviews, CEO votes). Approved patches apply via `scripts/consensus.py apply`.

Usage:
    python scripts/heal_loop.py                       # one heal iteration
    python scripts/heal_loop.py --max-iterations 3 --target tests/unit
    python scripts/heal_loop.py --dry-run             # parse failures, no LLM calls

Design:
- Bounded: max iterations, max patches per iteration, cooldown between.
- Token-lean: only traceback + relevant source slices enter the prompt.
- Safe: patches are proposals; application requires consensus approval.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from agent_comm import main_root  # noqa: E402

PYTEST_TIMEOUT = int(os.environ.get("NEXUS_HEAL_PYTEST_TIMEOUT", "900"))
MAX_PATCHES_PER_ITERATION = 3

_FAILURE_RE = re.compile(r"^FAILED (tests/[^\s]+)::([^\s]+)", re.MULTILINE)
_NODE_RE = re.compile(r"^(?P<mods>[\w./\\-]+?)::(?P<cls>[\w]+::)?(?P<func>[\w]+)")

_HEAL_PROMPT = """You are a targeted patch writer. Produce ONE unified diff (git apply format) \
that fixes the failing test with the minimal correct change. Output ONLY the diff, no prose.

Failing test: {node}
{traceback}

--- failing test source ({test_file}) ---
{test_source}

--- implementation under test ({sut_file}) ---
{sut_source}
"""


def run_pytest(target: str) -> tuple[int, list[tuple[str, str]], str]:
    """Returns (returncode, [(test_file, node)], raw_output_tail)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--tb=short", "-rf"],
        capture_output=True,
        text=True,
        timeout=PYTEST_TIMEOUT,
        cwd=str(main_root()),
    )
    out = (r.stdout or "")[-12000:]
    failures = []
    for m in _FAILURE_RE.finditer(out):
        failures.append((m.group(1), f"{m.group(1)}::{m.group(2)}"))
    seen = set()
    unique = []
    for tf, node in failures:
        if node not in seen:
            seen.add(node)
            unique.append((tf, node))
    return r.returncode, unique, out


def _file_slice(path: Path, max_lines: int = 120) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(unreadable)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return (
        "\n".join(lines[: max_lines // 2])
        + f"\n... ({len(lines) - max_lines} lines omitted) ...\n"
        + "\n".join(lines[-max_lines // 2 :])
    )


def _node_to_paths(node: str) -> tuple[Path | None, Path | None]:
    """Map 'tests/unit/test_x.py::test_y' to (test_file, guessed SUT file)."""
    m = _NODE_RE.match(node)
    if m is None:
        return None, None
    mods = m.group("mods").replace("\\", "/")
    test_path = main_root() / mods
    if not test_path.exists():
        return None, None
    stem = test_path.stem
    prefixes = ("test_",)
    base = stem
    for pre in prefixes:
        if stem.startswith(pre):
            base = stem[len(pre) :]
            break
    sut_candidates = [
        main_root() / "src" / "nexus" / f"{base}.py",
        main_root() / "src" / "nexus" / base / "__init__.py",
    ]
    for c in sut_candidates:
        if c.exists():
            return test_path, c
    return test_path, None


def build_patch_instruction(node: str) -> str | None:
    """Build the targeted prompt: traceback + failing test + SUT slices only."""
    test_path, sut_path = _node_to_paths(node)
    if test_path is None:
        return None
    run = subprocess.run(
        [sys.executable, "-m", "pytest", node, "--tb=long", "-q", "--no-header"],
        capture_output=True,
        text=True,
        timeout=max(PYTEST_TIMEOUT // 4, 120),
        cwd=str(main_root()),
    )
    traceback = ((run.stdout or "") + (run.stderr or ""))[-4000:]
    test_source = _file_slice(test_path)
    sut_source = _file_slice(sut_path) if sut_path is not None else "(not located - infer from the test)"
    sut_file = str(sut_path.relative_to(main_root())) if sut_path is not None else "unknown"
    return _HEAL_PROMPT.format(
        node=node,
        traceback=traceback,
        test_file=str(test_path.relative_to(main_root())),
        test_source=test_source,
        sut_file=sut_file,
        sut_source=sut_source,
    )


def _get_router(agent: str):
    """Build RoutingProvider + budget middleware from env. None components degrade."""
    from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider
    from nexus.infrastructure.adapters.llm.routing_provider import (
        RoutingProvider,
        TokenBudgetMiddleware,
        build_local_tier,
    )

    api_key = os.environ.get("NEXUS_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base_url = os.environ.get("NEXUS_LLM_BASE_URL", "https://api.openai.com/v1")
    primary = OpenAIProvider(api_key=api_key, base_url=base_url) if api_key else None
    local_high, local_low = build_local_tier()
    if primary is None:
        return local_low or local_high, None
    budget = TokenBudgetMiddleware(
        inner=RoutingProvider(primary=primary, local_high=local_high, local_low=local_low),
        fallback=local_low,
        ledger_path=main_root() / "token_budget_ledger.json",
        daily_budget=int(os.environ.get("NEXUS_DAILY_TOKEN_BUDGET", "500000")),
        agent=agent,
    )
    return budget, budget


def heal_once(dry_run: bool, target: str, author: str) -> int:
    """One heal iteration. Returns the number of patch proposals created."""
    code, failures, out = run_pytest(target)
    if code == 0:
        print("[heal] all green - nothing to heal")
        return 0
    if not failures:
        print("[heal] failures present but unparseable; storing tail in agent memory")
        if not dry_run:
            from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore

            AgentMemoryStore(main_root() / "agent_memory.json").put(
                agent="heal",
                kind="error",
                text=f"unparseable pytest failure tail ({target}):\n{out}",
                tags=["pytest", "unparseable"],
                created_at=datetime.now(UTC).isoformat(),
            )
        return 0
    print(f"[heal] {len(failures)} failing test(s)")
    router = None
    if not dry_run:
        router, _ = _get_router(author)
        if router is None:
            print("[heal] no provider available (no key, no Ollama) - aborting iteration")
            return 0
    created = 0
    from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

    proto = ConsensusProtocol(main_root() / "consensus_state.json")
    for test_file, node in failures[:MAX_PATCHES_PER_ITERATION]:
        print(f"[heal] targeting {node}")
        instruction = build_patch_instruction(node)
        if instruction is None:
            print("[heal]  could not map to source files - skipped")
            continue
        if dry_run:
            print(f"[heal]  (dry-run) would send {len(instruction)} chars of targeted context")
            continue
        from nexus.infrastructure.adapters.llm.routing_provider import estimate_tokens

        print(f"[heal]  targeted context: {estimate_tokens(instruction)} tokens (not full history)")
        draft = router.complete([{"role": "user", "content": instruction}], temperature=0.0)
        if not draft or "diff" not in draft.lower():
            print("[heal]  router returned no usable diff - skipped")
            continue
        p = proto.propose(
            title=f"heal: {node.split('::')[-1]}",
            author=author,
            draft=draft,
            files=[str(test_file)],
            created_at=datetime.now(UTC).isoformat(),
        )
        print(f"[heal]  proposal {p.id} [{p.status}] - awaiting review, then CEO vote")
        created += 1
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS self-healing test loop")
    parser.add_argument("--target", default="tests/unit")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--author", default="heal")
    parser.add_argument("--cooldown", type=float, default=30.0, help="seconds between iterations")
    args = parser.parse_args()
    for i in range(1, args.max_iterations + 1):
        print(f"[heal] === iteration {i}/{args.max_iterations} ===")
        created = heal_once(args.dry_run, args.target, args.author)
        if created == 0:
            break
        if i < args.max_iterations:
            print(f"[heal] cooling down {args.cooldown}s (proposals need review before next loop)")
            time.sleep(args.cooldown)
    print("[heal] done - check python scripts/consensus.py list --status in_review")


if __name__ == "__main__":
    main()
