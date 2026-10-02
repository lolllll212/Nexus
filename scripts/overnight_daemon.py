"""Overnight autonomy daemon - the thin wiring that builds the real loop.

Composes what already exists into the daemon core
(`nexus.application.autonomy.overnight_daemon.OvernightDaemon`):

- heal: `scripts/heal_loop.py`'s `heal_once` - runs pytest, builds targeted
  patch instructions, proposes to consensus. The daemon never re-proposes.
- consensus: `ConsensusProtocol` over the rendezvous state file, filtered to
  non-terminal proposals. Only `approved` ones reach the apply path.
- apply: `scripts/consensus.py apply --id` - it refuses non-approved patches
  itself (defense in depth with the daemon's own status filter).
- verify: full pytest run. A patch that breaks the gates is reverse-applied and
  NEVER committed.
- commit: one commit per applied patch, attributed to the daemon.
- dream: one dreaming cycle per loop iteration, via `nexus.cli`.

Stop conditions: kill-switch file, blackout windows (NEXUS_DAEMON_BLACKOUTS),
token budget (NEXUS_DAILY_TOKEN_BUDGET over the spend ledger).

Usage:
    python scripts/overnight_daemon.py                       # run the loop
    python scripts/overnight_daemon.py --max-cycles 3        # bounded run
    python scripts/overnight_daemon.py --target tests/unit   # override heal target

The kill switch is a file: create it to stop the daemon between items.
    touch .nexus_overnight_stop
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from agent_comm import main_root  # noqa: E402
from heal_loop import heal_once  # noqa: E402

from nexus.application.autonomy.overnight_daemon import (  # noqa: E402
    OvernightDaemon,
    PendingPatch,
    parse_blackouts,
)

KILL_SWITCH_FILE = ".nexus_overnight_stop"


def _kill_switched(root: Path) -> bool:
    """Kill switch: the marker file, or NEXUS_DAEMON_KILL_SWITCH=1. `=0` disarms."""
    env = os.environ.get("NEXUS_DAEMON_KILL_SWITCH")
    if env == "0":
        return False
    if env == "1":
        return True
    return (root / KILL_SWITCH_FILE).exists()


def _budget_available(root: Path, agent: str) -> bool:
    """True while the agent is under its daily token budget. No ledger = no cap."""
    ledger_path = root / "token_budget_ledger.json"
    if not ledger_path.exists():
        return True
    daily = int(os.environ.get("NEXUS_DAILY_TOKEN_BUDGET", "500000"))
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    spent = int(ledger.get(today, {}).get(agent, 0))
    return spent < daily


def _consensus_gate(root: Path):
    """ConsensusGate over the real protocol: non-terminal proposals only."""
    from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

    proto = ConsensusProtocol(root / "consensus_state.json")

    class _Gate:
        def pending_proposals(self) -> list[PendingPatch]:
            return [
                PendingPatch(p.id, p.status, list(p.files), p.draft)
                for p in proto.list_proposals()
                if p.status not in ("applied",)
            ]

        def mark_applied(self, proposal_id: str) -> None:
            # The protocol has no applied marker; `git apply --check` fails on an
            # already-applied patch, so a re-run skips it naturally.
            print(f"[daemon] applied {proposal_id}")

    return _Gate()


def _run(cmd: list[str], root: Path) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or ""))[-800:]
        print(f"[daemon] command failed ({' '.join(cmd[:3])}):\n{tail}")
    return r.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS overnight autonomy daemon")
    parser.add_argument("--target", default="tests/unit", help="default heal target when the queue is empty")
    parser.add_argument("--max-cycles", type=int, default=50)
    parser.add_argument("--agent", default="daemon", help="agent name for the token budget ledger")
    parser.add_argument(
        "--dry-run", action="store_true", help="heal in dry-run mode; no LLM calls, no applies"
    )
    args = parser.parse_args()

    root = main_root()
    dry = args.dry_run

    def verify() -> bool:
        if dry:
            return True  # dry-run never applies, so never verifies
        return _run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"], root)

    def apply_patch(patch: PendingPatch) -> bool:
        if dry:
            print(f"[daemon] (dry-run) would apply {patch.proposal_id} [{patch.status}]")
            return False  # dry-run never applies
        return _run([sys.executable, "scripts/consensus.py", "apply", "--id", patch.proposal_id], root)

    def dream() -> bool:
        if dry:
            return True  # dry-run never applies, so never verifies
        # PYTHONPATH so the dream runs THIS tree's src, not the editable install,
        # which points at the main checkout and may hold a different branch.
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        r = subprocess.run(
            [sys.executable, "-m", "nexus", "dream", "--local"],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=env,
        )
        if r.returncode != 0:
            print(f"[daemon] dream failed:\n{((r.stdout or '') + (r.stderr or ''))[-800:]}")
        return r.returncode == 0

    def rollback(patch: PendingPatch) -> None:
        if dry or not patch.draft:
            return
        print(f"[daemon] verify failed - reverse-applying {patch.proposal_id}")
        subprocess.run(
            ["git", "apply", "-R", "--unsafe-paths=no", "-"],
            input=patch.draft,
            text=True,
            cwd=str(root),
            capture_output=True,
        )

    def commit(patch: PendingPatch) -> bool:
        if dry:
            return False
        _run(["git", "add", "-A"], root)
        ok = _run(
            ["git", "commit", "-m", f"daemon: apply consensus patch {patch.proposal_id}\n\nAgent: daemon"],
            root,
        )
        return ok

    daemon = OvernightDaemon(
        clock=datetime.now,
        kill_switch=lambda: _kill_switched(root),
        budget_available=lambda: _budget_available(root, args.agent),
        work_items=lambda: [args.target],
        heal=lambda target: heal_once(dry, target, author="heal"),
        consensus=_consensus_gate(root),
        apply_patch=apply_patch,
        verify=verify,
        commit=commit,
        rollback=rollback,
        dream=dream,
        blackout_windows=parse_blackouts(os.environ.get("NEXUS_DAEMON_BLACKOUTS", "")),
        default_target=args.target,
        max_cycles=args.max_cycles,
    )

    print(f"[daemon] starting: kill-switch={KILL_SWITCH_FILE}, max-cycles={args.max_cycles}, dry-run={dry}")
    result = daemon.run()
    print(
        f"[daemon] stopped ({result.stopped_reason}): {result.cycles_run} cycle(s), "
        f"{result.heal_iterations} heal iteration(s), {result.patches_applied} patch(es) applied, "
        f"{result.dreams_run} dream(s)"
    )


if __name__ == "__main__":
    main()
