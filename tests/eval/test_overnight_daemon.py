"""Tests for the overnight autonomy daemon (`application/autonomy/overnight_daemon.py`).

The three acceptance criteria from plan-001 / Upgrade Space 2, plus the safety
properties they imply:

* The full cycle runs in order: heal -> apply -> verify -> commit -> dream.
* The daemon stops on the kill-switch file and respects blackout windows.
* No patch applies without an approved consensus verdict - the core filters
  statuses itself, so the guard is testable and survives a refactor of either
  half (`scripts/consensus.py apply` refuses non-approved patches as well).

Dependencies are injected callables; the fakes below record calls so the tests
can assert on the order things happened, not just that they happened.
"""

from __future__ import annotations

from datetime import datetime

from nexus.application.autonomy.overnight_daemon import (
    OvernightDaemon,
    PendingPatch,
    parse_blackouts,
)

WORK_TARGET = "tests/unit"


class _Gate:
    """Consensus fake with scripted proposals and an applied log."""

    def __init__(self, proposals: list[PendingPatch]) -> None:
        self._proposals = list(proposals)
        self.applied: list[str] = []

    def pending_proposals(self) -> list[PendingPatch]:
        return list(self._proposals)

    def mark_applied(self, proposal_id: str) -> None:
        self.applied.append(proposal_id)


class _Daemon:
    """Builds the daemon with recording deps sharing one ordered trace."""

    def __init__(self, **overrides) -> None:
        self.trace: list[str] = []
        deps: dict = {
            "clock": lambda: datetime(2026, 10, 3, 2, 0),  # 02:00 - outside blackout
            "kill_switch": lambda: False,
            "budget_available": lambda: True,
            "work_items": lambda: [WORK_TARGET],
            "heal": self._step("heal", returns=1),  # one proposal created per heal call
            "consensus": _Gate([PendingPatch("p1", "approved", ["a.py"])]),
            "apply_patch": self._step("apply", returns=True),
            "verify": self._step("verify", returns=True),
            "commit": self._step("commit", returns=True),
            "rollback": self._step("rollback", returns=None),
            "dream": self._step("dream", returns=None),
            "blackout_windows": [],
            "default_target": WORK_TARGET,
            "max_cycles": 1,
        }
        deps.update(overrides)
        self.daemon = OvernightDaemon(**deps)
        self.deps = deps

    def _step(self, name: str, returns):
        def call(*args):
            arg = args[0] if args else None
            if isinstance(arg, PendingPatch):
                arg = arg.proposal_id
            self.trace.append(name if arg is None else f"{name}:{arg}")
            return returns

        return call


APPROVED = PendingPatch("p-approved", "approved", ["fix.py"])
IN_REVIEW = PendingPatch("p-review", "in_review", ["wip.py"])
REJECTED = PendingPatch("p-reject", "rejected", ["bad.py"])


# --------------------------------------------------------------------------
# AC: the full cycle
# --------------------------------------------------------------------------


def test_happy_path_runs_the_full_cycle_in_order():
    d = _Daemon(consensus=_Gate([APPROVED]))
    result = d.daemon.run()

    assert d.trace == [
        f"heal:{WORK_TARGET}",
        "apply:p-approved",
        "verify",
        "commit:p-approved",
        "dream",
    ]
    assert (result.cycles_run, result.heal_iterations, result.patches_applied, result.dreams_run) == (
        1,
        1,
        1,
        1,
    )
    assert result.stopped_reason == "completed"


def test_no_patch_applies_without_an_approved_verdict():
    """THE safety property: only `approved` reaches the apply path, whatever the
    other statuses say - in_review, rejected, and request_changes never apply."""
    gate = _Gate([APPROVED, IN_REVIEW, REJECTED, PendingPatch("p-rc", "request_changes", ["x.py"])])
    d = _Daemon(consensus=gate)

    result = d.daemon.run()

    assert d.trace == [f"heal:{WORK_TARGET}", "apply:p-approved", "verify", "commit:p-approved", "dream"]
    assert gate.applied == ["p-approved"]
    assert result.patches_applied == 1


def test_apply_failure_is_skipped_without_verify_or_commit():
    d = _Daemon(consensus=_Gate([PendingPatch("p-broken", "approved")]), apply_patch=lambda p: False)

    result = d.daemon.run()

    assert "verify" not in d.trace and "commit" not in d.trace
    assert "rollback" not in d.trace  # nothing was applied, so nothing to undo
    assert result.patches_applied == 0


# --------------------------------------------------------------------------
# AC: kill-switch + blackout windows
# --------------------------------------------------------------------------


def test_kill_switch_stops_the_daemon_before_any_work():
    d = _Daemon(kill_switch=lambda: True)

    result = d.daemon.run()

    assert d.trace == []
    assert result.stopped_reason == "kill_switch"
    assert (result.cycles_run, result.heal_iterations, result.dreams_run) == (0, 0, 0)


def test_kill_switch_flipping_mid_run_stops_before_the_next_cycle():
    """The switch is checked after each item too - a stop mid-cycle must not
    leave a half-healed queue running into the dream phase."""
    calls = {"n": 0}

    def flip_after_first_heal(target: str) -> int:
        calls["n"] += 1
        return 1  # one proposal created

    def kill_after_first_heal() -> bool:
        return calls["n"] >= 1

    d = _Daemon(heal=flip_after_first_heal, kill_switch=kill_after_first_heal)

    result = d.daemon.run()

    assert calls["n"] == 1  # heal ran exactly once, then the switch stopped the loop
    assert result.stopped_reason == "kill_switch"
    assert result.heal_iterations == 1


def test_blackout_window_blocks_the_cycle():
    d = _Daemon(blackout_windows=[(9, 17)], clock=lambda: datetime(2026, 10, 3, 10, 0))

    result = d.daemon.run()

    assert d.trace == []
    assert result.stopped_reason == "blackout"


def test_blackout_window_wrapping_midnight():
    night = _Daemon(blackout_windows=[(22, 6)], clock=lambda: datetime(2026, 10, 3, 3, 0)).daemon.run()
    assert night.stopped_reason == "blackout"

    day = _Daemon(blackout_windows=[(22, 6)], clock=lambda: datetime(2026, 10, 3, 12, 0)).daemon.run()
    assert day.stopped_reason == "completed"


def test_blackout_edges_are_start_inclusive_end_exclusive():
    at_start = _Daemon(blackout_windows=[(9, 17)], clock=lambda: datetime(2026, 10, 3, 9, 0)).daemon.run()
    assert at_start.stopped_reason == "blackout"

    at_end = _Daemon(blackout_windows=[(9, 17)], clock=lambda: datetime(2026, 10, 3, 17, 0)).daemon.run()
    assert at_end.stopped_reason == "completed"


def test_budget_exhaustion_pauses_the_daemon():
    d = _Daemon(budget_available=lambda: False)

    result = d.daemon.run()

    assert d.trace == []
    assert result.stopped_reason == "budget"


# --------------------------------------------------------------------------
# Verify failure -> rollback, never commit
# --------------------------------------------------------------------------


def test_verify_failure_after_apply_rolls_back_and_does_not_commit():
    verify_calls: list[str] = []

    def failing_verify() -> bool:
        verify_calls.append("verify")
        return False

    d = _Daemon(consensus=_Gate([APPROVED]), verify=failing_verify)

    result = d.daemon.run()

    assert verify_calls == ["verify"]  # verify ran, returned False
    assert d.trace == [f"heal:{WORK_TARGET}", "apply:p-approved", "rollback:p-approved", "dream"]
    assert "commit" not in d.trace
    assert result.patches_applied == 0


# --------------------------------------------------------------------------
# Work items + bounds
# --------------------------------------------------------------------------


def test_no_work_items_falls_back_to_the_default_target():
    d = _Daemon(work_items=lambda: [])

    result = d.daemon.run()

    assert d.trace[0] == f"heal:{WORK_TARGET}"
    assert result.heal_iterations == 1


def test_each_work_item_is_healed_and_the_kill_switch_is_checked_between_them():
    d = _Daemon(work_items=lambda: ["tests/unit", "tests/eval"])

    d.daemon.run()

    assert d.trace[0] == "heal:tests/unit"
    assert d.trace[1] == "heal:tests/eval"


def test_max_cycles_bounds_the_loop():
    d = _Daemon(max_cycles=3, consensus=_Gate([APPROVED]))

    result = d.daemon.run()

    assert result.cycles_run == 3
    assert d.trace.count("dream") == 3
    assert d.trace.count("apply:p-approved") == 3


def test_empty_cycle_still_dreams():
    """Idle is not an error: the daemon's overnight job includes dreaming even
    when there is nothing to heal and nothing to apply."""
    d = _Daemon(consensus=_Gate([]))

    result = d.daemon.run()

    assert d.trace == [f"heal:{WORK_TARGET}", "dream"]
    assert result.patches_applied == 0
    assert result.dreams_run == 1


# --------------------------------------------------------------------------
# Blackout spec parsing
# --------------------------------------------------------------------------


def test_blackout_spec_parsing_skips_invalid_entries():
    assert parse_blackouts("09:00-17:00,22:00-06:00") == [(9, 17), (22, 6)]
    assert parse_blackouts("9-17") == [(9, 17)]
    assert parse_blackouts("nonsense,24:00-30:00,") == []
    assert parse_blackouts("") == []
