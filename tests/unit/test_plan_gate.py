"""Tests for the plan-first gate: bounded plans, frozen in_progress state,
and the edit gate that refuses files no active plan covers.

All tests are hermetic: no LLM, no network.
"""

from __future__ import annotations

from pathlib import Path

from nexus.infrastructure.adapters.swarm.planning import (
    DEFAULT_MAX_STEPS,
    PlanningBoard,
    PlanStep,
    check_file,
)


class TestPlanCreation:
    def test_create_plan_with_steps(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, error = b.create_plan(
            title="Fix auth 401s",
            agent="astra",
            steps=[
                ("merge NEXUS_API_KEYS", ["tests/conftest.py"]),
                ("verify auth tests", ["tests/unit/test_route_authentication.py"]),
            ],
        )
        assert error is None
        assert p.status == "draft"
        assert p.progress() == "0/2"
        assert p.files() == ["tests/conftest.py", "tests/unit/test_route_authentication.py"]

    def test_step_cap_rejects_overgrown_plans(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        steps = [(f"step {i}", []) for i in range(DEFAULT_MAX_STEPS + 1)]
        p, error = b.create_plan(title="Too big", agent="xenom", steps=steps)
        assert error is not None
        assert "cap" in error
        assert p.id == ""

    def test_explicit_higher_cap_allowed(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        steps = [(f"step {i}", []) for i in range(8)]
        p, error = b.create_plan(title="Big but explicit", agent="xenom", steps=steps, max_steps=8)
        assert error is None
        assert len(p.steps) == 8

    def test_empty_plan_rejected(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, error = b.create_plan(title="Empty", agent="astra", steps=[])
        assert error is not None
        assert p.id == ""

    def test_idempotent_draft_same_title(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p1, e1 = b.create_plan(title="Same work", agent="astra", steps=[("s", [])])
        p2, e2 = b.create_plan(title="Same work", agent="astra", steps=[("s", [])])
        assert e1 is None
        assert p1.id == p2.id
        assert e2 is not None and "already" in e2

    def test_recreate_after_done_allowed(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p1, _ = b.create_plan(title="Rework", agent="astra", steps=[("s", [])])
        b.begin(p1.id)
        b.complete_step(p1.id)
        b.finish(p1.id)
        p2, error = b.create_plan(title="Rework", agent="astra", steps=[("s2", [])])
        assert error is None
        assert p2.id == p1.id  # same slug - the done plan is replaced
        assert p2.status == "draft"


class TestPlanLifecycle:
    def test_begin_freezes_plan(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Freeze me", agent="astra", steps=[("s", [])])
        b.begin(p.id)
        p2, error = b.add_step(p.id, "unplanned work")
        assert error is not None
        assert "FROZEN" in error
        assert len(p2.steps) == 1

    def test_steps_done_in_order_no_skipping(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(
            title="Ordered",
            agent="tron",
            steps=[("first", []), ("second", []), ("third", [])],
        )
        b.begin(p.id)
        b.complete_step(p.id)
        p2, _ = b.complete_step(p.id)
        assert p2.progress() == "2/3"
        # The board completes the FIRST not-done step - order is enforced by
        # construction; there is no way to mark step 3 while 2 is open.
        for _ in p2.steps:
            b.complete_step(p2.id)
        assert p2.all_done()

    def test_complete_step_before_begin_refused(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Not begun", agent="astra", steps=[("s", [])])
        _, error = b.complete_step(p.id)
        assert error is not None and "begin" in error

    def test_finish_requires_all_steps_done(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Half done", agent="xenom", steps=[("s1", []), ("s2", [])])
        b.begin(p.id)
        b.complete_step(p.id)
        _, error = b.finish(p.id)
        assert error is not None and "cannot finish" in error
        b.complete_step(p.id)
        p2, error2 = b.finish(p.id)
        assert error2 is None
        assert p2.status == "done"
        assert p2.finished_at != ""

    def test_abandon_allows_replan(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Scope changed", agent="astra", steps=[("s", [])])
        b.begin(p.id)
        _, error = b.add_step(p.id, "new work")  # frozen - refused
        assert error is not None
        p2, err2 = b.abandon(p.id, reason="discovered unplanned work")
        assert err2 is None
        assert p2.status == "abandoned"
        assert p2.abandon_reason == "discovered unplanned work"
        # Re-plan: new title, new plan id.
        p3, err3 = b.create_plan(title="Scope changed v2", agent="astra", steps=[("s", []), ("new work", [])])
        assert err3 is None and p3.id != p.id

    def test_persistence_across_instances(self, tmp_path: Path):
        path = tmp_path / "plans.json"
        b = PlanningBoard(path)
        p, _ = b.create_plan(title="Persist", agent="tron", steps=[("s", ["a.py"])])
        b.begin(p.id)
        b.complete_step(p.id, note="done note")
        b2 = PlanningBoard(path)
        p2 = b2.get(p.id)
        assert p2.status == "in_progress"
        assert p2.steps[0].done is True
        assert p2.steps[0].note == "done note"


class TestPlanGate:
    def test_uncovered_file_refused(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Other files", agent="astra", steps=[("s", ["src/nexus/other.py"])])
        b.begin(p.id)
        allowed, reason = check_file("src/nexus/unrelated.py", b)
        assert allowed is False
        assert "no in_progress plan covers" in reason
        assert p.id != ""

    def test_covered_file_exact_match(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Exact", agent="astra", steps=[("s", ["src/nexus/x.py"])])
        b.begin(p.id)
        allowed, reason = check_file("src/nexus/x.py", b)
        assert allowed is True
        assert p.id in reason

    def test_covered_file_under_planned_directory(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Dir plan", agent="tron", steps=[("s", ["src/nexus/infrastructure"])])
        b.begin(p.id)
        allowed, _ = check_file("src/nexus/infrastructure/adapters/x.py", b)
        assert allowed is True

    def test_windows_path_normalized(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Win", agent="xenom", steps=[("s", ["src\\nexus\\y.py"])])
        b.begin(p.id)
        allowed, _ = check_file("./src/nexus/y.py", b)
        assert allowed is True

    def test_draft_plan_does_not_cover(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        b.create_plan(title="Draft only", agent="astra", steps=[("s", ["src/nexus/z.py"])])
        # Never begun - the gate refuses: plan-first means begun, not just written.
        allowed, reason = check_file("src/nexus/z.py", b)
        assert allowed is False
        assert "no in_progress plan covers" in reason

    def test_outside_editable_roots_refused(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        allowed, reason = check_file("frontend/holo.html", b)
        assert allowed is False
        assert "outside the editable roots" in reason

    def test_done_plan_no_longer_covers(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Done soon", agent="astra", steps=[("s", ["src/nexus/d.py"])])
        b.begin(p.id)
        b.complete_step(p.id)
        b.finish(p.id)
        allowed, _ = check_file("src/nexus/d.py", b)
        assert allowed is False

    def test_abandoned_plan_no_longer_covers(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(title="Abandoned", agent="astra", steps=[("s", ["src/nexus/a.py"])])
        b.begin(p.id)
        b.abandon(p.id)
        allowed, _ = check_file("src/nexus/a.py", b)
        assert allowed is False

    def test_two_agents_one_board(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        pa, _ = b.create_plan(title="Astra work", agent="astra", steps=[("s", ["src/nexus/a.py"])])
        px, _ = b.create_plan(title="Xenom work", agent="xenom", steps=[("s", ["src/nexus/x.py"])])
        b.begin(pa.id)
        b.begin(px.id)
        assert check_file("src/nexus/a.py", b)[0] is True
        assert check_file("src/nexus/x.py", b)[0] is True
        assert check_file("src/nexus/other.py", b)[0] is False

    def test_step_files_optional(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        p, _ = b.create_plan(
            title="No files", agent="astra", steps=[(PlanStep(description="think", files=[]).description, [])]
        )
        b.begin(p.id)
        assert p.files() == []

    def test_root_level_dependency_files_are_gateable(self, tmp_path: Path):
        """requirements.* and pyproject.toml live at the repo root (no
        directory prefix) but are legitimately editable - the gate must
        treat them as plan-gateable, not 'outside editable roots'."""
        b = PlanningBoard(tmp_path / "plans.json")
        for f in ("requirements.in", "requirements.txt", "requirements-dev.in", "pyproject.toml"):
            allowed, reason = check_file(f, b)
            # No plan -> refused, but with the plan-first message, NOT the
            # editable-roots rejection.
            assert allowed is False
            assert "outside the editable roots" not in reason
        p, error = b.create_plan(
            title="Declare aiohttp",
            agent="xenom",
            steps=[("add aiohttp to requirements.in", ["requirements.in", "requirements.txt"])],
        )
        assert error is None
        b.begin(p.id)
        allowed, reason = check_file("requirements.in", b)
        assert allowed is True
        assert p.id in reason
        allowed2, _ = check_file("requirements.txt", b)
        assert allowed2 is True

    def test_root_files_still_uncovered_without_plan(self, tmp_path: Path):
        b = PlanningBoard(tmp_path / "plans.json")
        allowed, reason = check_file("requirements.txt", b)
        assert allowed is False
        assert "no in_progress plan covers" in reason
