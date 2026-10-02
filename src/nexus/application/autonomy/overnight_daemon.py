"""Overnight autonomy daemon - one loop with safety gates, not a free-running script.

Ties bridge events + task queue -> heal -> consensus -> apply (CEO-approved
only) -> verify -> commit -> dream. The pieces already exist (`heal_loop`,
`ConsensusProtocol`, the token budget ledger); what was missing is the loop that
composes them with the stop conditions checked in the right order.

Safety properties, in the order they gate each cycle:

1. Kill-switch file stops the daemon BEFORE any work - not after the current
   item, and never mid-apply.
2. Blackout windows (checked against an injected clock) pause it - so a daemon
   left running overnight stays quiet during working hours.
3. Budget exhaustion pauses it - over-budget traffic already degrades to the
   local tier; a dead budget must not also spawn unbounded cycles.
4. And no patch is EVER applied unless the consensus gate says `approved`. The
   apply path in `scripts/consensus.py` refuses non-approved patches too, but
   this loop filters as well: defense in depth, because a refactor that touches
   either guard must leave one intact.

Dependencies are injected callables so the whole loop is testable with fakes;
`scripts/overnight_daemon.py` is the thin wiring that builds the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol


@dataclass
class PendingPatch:
    """A consensus proposal the daemon may or may not be allowed to apply."""

    proposal_id: str
    status: str  # consensus status: approved / rejected / in_review / request_changes
    files: list[str] = field(default_factory=list)
    draft: str = ""


class ConsensusGate(Protocol):
    """The slice of the consensus protocol the daemon needs."""

    def pending_proposals(self) -> list[PendingPatch]: ...

    def mark_applied(self, proposal_id: str) -> None: ...


@dataclass
class DaemonResult:
    cycles_run: int = 0
    heal_iterations: int = 0
    patches_applied: int = 0
    dreams_run: int = 0
    stopped_reason: str = "completed"  # completed | kill_switch | blackout | budget


def parse_blackouts(spec: str) -> list[tuple[int, int]]:
    """Parse `09:00-17:00,22:00-06:00` into `[(9, 17), (22, 6)]`.

    Invalid entries are skipped, not fatal: a typo in an env var must not take
    down the safety rail, it must only narrow it.
    """
    windows: list[tuple[int, int]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk or "-" not in chunk:
            continue
        start_s, end_s = chunk.split("-", 1)
        try:
            start, end = int(start_s.split(":")[0]), int(end_s.split(":")[0])
        except ValueError:
            continue
        if 0 <= start <= 23 and 0 <= end <= 23:
            windows.append((start, end))
    return windows


class OvernightDaemon:
    def __init__(
        self,
        clock: Callable[[], datetime],
        kill_switch: Callable[[], bool],
        budget_available: Callable[[], bool],
        work_items: Callable[[], list[str]],
        heal: Callable[[str], int],
        consensus: ConsensusGate,
        apply_patch: Callable[[PendingPatch], bool],
        verify: Callable[[], bool],
        commit: Callable[[PendingPatch], bool],
        rollback: Callable[[PendingPatch], None],
        dream: Callable[[], None],
        blackout_windows: list[tuple[int, int]] | None = None,
        default_target: str = "tests/unit",
        max_cycles: int = 50,
    ) -> None:
        self._clock = clock
        self._kill_switch = kill_switch
        self._budget_available = budget_available
        self._work_items = work_items
        self._heal = heal
        self._consensus = consensus
        self._apply_patch = apply_patch
        self._verify = verify
        self._commit = commit
        self._rollback = rollback
        self._dream = dream
        self._blackout_windows = blackout_windows or []
        self._default_target = default_target
        self._max_cycles = max_cycles

    def run(self) -> DaemonResult:
        result = DaemonResult()
        for _ in range(self._max_cycles):
            stop = self._stop_reason()
            if stop:
                result.stopped_reason = stop
                return result

            # Task queue + bridge events -> heal targets. The heal step proposes
            # to consensus internally; the daemon never re-proposes.
            for target in self._work_items() or [self._default_target]:
                result.heal_iterations += self._heal(target)
                if self._kill_switch():
                    result.stopped_reason = "kill_switch"
                    return result

            for patch in self._consensus.pending_proposals():
                if patch.status != "approved":
                    continue  # no patch applies without an approved verdict
                if not self._apply_patch(patch):
                    continue
                if not self._verify():
                    self._rollback(patch)  # applied but broken -> undo, never commit
                    continue
                self._commit(patch)
                self._consensus.mark_applied(patch.proposal_id)
                result.patches_applied += 1

            self._dream()
            result.dreams_run += 1
            result.cycles_run += 1
        return result

    def _stop_reason(self) -> str | None:
        if self._kill_switch():
            return "kill_switch"
        if self._in_blackout(self._clock()):
            return "blackout"
        if not self._budget_available():
            return "budget"
        return None

    def _in_blackout(self, now: datetime) -> bool:
        for start, end in self._blackout_windows:
            if start == end:
                continue
            if start < end:
                if start <= now.hour < end:
                    return True
            elif now.hour >= start or now.hour < end:
                return True  # wraps midnight, e.g. 22:00-06:00
        return False
