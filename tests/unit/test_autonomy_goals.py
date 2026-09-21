"""
Autonomous goals tests (Phase 2, Priority 2).

Covers the P2 deliverables against fakes:
  - Goal entity lifecycle + budget accounting
  - AutonomyPolicy guardrails (step budget, hourly budget, approval, audit)
  - goal use cases (create/approve/cancel/list/get)
  - AutonomyLoopUseCase driving a goal to completion within budget
  - SelfHealUseCase gating (budget + approval + audit)
  - /v1/goals API incl. tenant isolation
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.application.autonomy.goals import (
    ApproveGoalUseCase,
    AutonomyLoopUseCase,
    CancelGoalUseCase,
    CreateGoalUseCase,
    GetGoalUseCase,
    ListGoalsUseCase,
    StepOutcome,
)
from nexus.application.tools.self_heal import SelfHealUseCase
from nexus.domain.entities.goal import Goal, GoalStatus
from nexus.domain.entities.tool import Tool
from nexus.domain.exceptions import GoalNotFoundError, GoalStatusError
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.autonomy.goal_repository import InMemoryGoalRepository
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.security.rate_limiter import SlidingWindowRateLimiter
from nexus.infrastructure.api.main import create_app

from tests.fakes import FakeToolRegistry
from tests.fakes.container import FakeContainer, TEST_API_KEY_1, TEST_API_KEY_2

AUTH_T1 = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
AUTH_T2 = {"Authorization": f"Bearer {TEST_API_KEY_2}"}


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _inject(client, app, llm_script=None):
    fake = FakeContainer(llm_script=llm_script)
    app.state.container = fake
    client.app.state.container = fake
    return fake


class _CountingExecutor:
    """Runs each step; completes after a configurable number of steps."""

    def __init__(self, complete_after: int = 1):
        self.calls = 0
        self.complete_after = complete_after

    async def run_step(self, goal, step, tenant_id):
        self.calls += 1
        return StepOutcome(completed=self.calls >= self.complete_after, summary=f"outcome {self.calls}")


# --------------------------------------------------------------------------- #
#  Goal entity
# --------------------------------------------------------------------------- #


def test_goal_lifecycle_and_budget():
    goal = Goal(statement="summarize docs", tenant_id="t1", owner_id="u1", budget_units=3)
    assert goal.status == GoalStatus.PROPOSED
    assert goal.has_budget and goal.budget_remaining == 3

    goal.mark_active(approved_by="u1")
    assert goal.status == GoalStatus.ACTIVE
    assert goal.approved_by == "u1"
    assert any(e.kind == "approved" for e in goal.history)

    assert goal.spend() is True
    assert goal.spend() is True
    assert goal.spend() is True
    assert goal.spend() is False  # budget exhausted
    assert goal.budget_spent == 3
    assert not goal.has_budget

    goal.mark_completed("did it")
    assert goal.status == GoalStatus.COMPLETED
    assert goal.result == "did it"


def test_goal_cancel_rules():
    goal = Goal(statement="x", tenant_id="t1", owner_id="u1", budget_units=5)
    goal.cancel("u1")
    assert goal.status == GoalStatus.CANCELLED
    with pytest.raises(ValueError):
        goal.cancel("u1")  # already terminal


# --------------------------------------------------------------------------- #
#  AutonomyPolicy
# --------------------------------------------------------------------------- #


def test_policy_authorize_action_hourly_budget():
    limiter = SlidingWindowRateLimiter()
    policy = DefaultAutonomyPolicy(rate_limiter=limiter, hourly_budget=2, allowlist=[])
    assert asyncio.run(policy.authorize_action("t1")).allowed
    assert asyncio.run(policy.authorize_action("t1")).allowed
    denied = asyncio.run(policy.authorize_action("t1"))
    assert denied.denied
    assert "hourly" in denied.reason


def test_policy_authorize_step_checks_goal_state_and_budget():
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), hourly_budget=0)
    proposed = Goal(statement="s", tenant_id="t1", owner_id="u1", budget_units=5)
    assert asyncio.run(policy.authorize_step(proposed, "t1")).allowed

    proposed.status = GoalStatus.BLOCKED
    denied = asyncio.run(policy.authorize_step(proposed, "t1"))
    assert denied.denied and "not active" in denied.reason


def test_policy_approval_allowlist_and_grant():
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), allowlist=["tool_selfheal"])
    assert asyncio.run(policy.require_approval("tool_selfheal", "system", "t1")) is True
    assert asyncio.run(policy.require_approval("deploy_tool", "system", "t1")) is False

    asyncio.run(policy.grant_approval("deploy_tool", "admin", "t1"))
    assert asyncio.run(policy.require_approval("deploy_tool", "system", "t1")) is True

    pending = asyncio.run(policy.pending_approvals("t1"))
    assert any(p["action"] == "deploy_tool" and p["granted"] for p in pending)


def test_policy_audit_log_is_tenant_scoped():
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter())
    from nexus.domain.entities.goal import GoalEvent

    asyncio.run(policy.audit(GoalEvent(kind="regenerated_tool", detail="a"), "t1"))
    asyncio.run(policy.audit(GoalEvent(kind="regenerated_tool", detail="b"), "t2"))
    t1_log = asyncio.run(policy.audit_log("t1"))
    t2_log = asyncio.run(policy.audit_log("t2"))
    assert [e.detail for e in t1_log] == ["a"]
    assert [e.detail for e in t2_log] == ["b"]


# --------------------------------------------------------------------------- #
#  Goal use cases
# --------------------------------------------------------------------------- #


def test_create_goal_requires_approval_by_default():
    repo = InMemoryGoalRepository()
    uc = CreateGoalUseCase(repo)
    goal = asyncio.run(uc.execute("reduce memory", "t1", "u1", budget_units=10))
    assert goal.status == GoalStatus.PROPOSED
    assert asyncio.run(repo.get(goal.id, "t1")) is goal


def test_create_goal_without_approval_is_active():
    repo = InMemoryGoalRepository()
    uc = CreateGoalUseCase(repo)
    goal = asyncio.run(uc.execute("reduce memory", "t1", "u1", budget_units=10, requires_approval=False))
    assert goal.status == GoalStatus.ACTIVE


def test_approve_goal_flow():
    repo = InMemoryGoalRepository()
    goal = asyncio.run(CreateGoalUseCase(repo).execute("x", "t1", "u1", 5))
    approved = asyncio.run(ApproveGoalUseCase(repo).execute(goal.id, "t1", "admin"))
    assert approved.status == GoalStatus.ACTIVE

    with pytest.raises(GoalStatusError):
        asyncio.run(ApproveGoalUseCase(repo).execute(goal.id, "t1", "admin"))

    with pytest.raises(GoalNotFoundError):
        asyncio.run(ApproveGoalUseCase(repo).execute("missing", "t1", "admin"))


def test_cancel_and_tenant_isolation():
    repo = InMemoryGoalRepository()
    g1 = asyncio.run(CreateGoalUseCase(repo).execute("a", "t1", "u1", 5, requires_approval=False))
    asyncio.run(CreateGoalUseCase(repo).execute("b", "t2", "u2", 5, requires_approval=False))

    with pytest.raises(GoalNotFoundError):
        asyncio.run(GetGoalUseCase(repo).execute(g1.id, "t2"))

    cancelled = asyncio.run(CancelGoalUseCase(repo).execute(g1.id, "t1", "u1"))
    assert cancelled.status == GoalStatus.CANCELLED

    listed = asyncio.run(ListGoalsUseCase(repo).execute("t1"))
    assert len(listed) == 0  # cancelled goals are not active


# --------------------------------------------------------------------------- #
#  AutonomyLoopUseCase
# --------------------------------------------------------------------------- #


def test_loop_completes_goal_within_budget():
    repo = InMemoryGoalRepository()
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), hourly_budget=0)
    goal = asyncio.run(
        CreateGoalUseCase(repo).execute("analyze logs", "t1", "u1", 5, requires_approval=False)
    )
    goal.mark_active(approved_by="u1")
    executor = _CountingExecutor(complete_after=2)
    loop = AutonomyLoopUseCase(repo, policy, executor)

    result = asyncio.run(loop.run_goal(goal, "t1"))
    assert result.status == GoalStatus.COMPLETED
    assert result.budget_spent == 2
    assert executor.calls == 2
    assert any(e.kind == "completed" for e in result.history)


def test_loop_blocks_when_budget_exhausted():
    repo = InMemoryGoalRepository()
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), hourly_budget=0)
    goal = asyncio.run(CreateGoalUseCase(repo).execute("big task", "t1", "u1", 2, requires_approval=False))
    goal.mark_active(approved_by="u1")
    executor = _CountingExecutor(complete_after=99)  # never completes
    loop = AutonomyLoopUseCase(repo, policy, executor)

    result = asyncio.run(loop.run_goal(goal, "t1"))
    assert result.status == GoalStatus.ACTIVE  # budget spent but no failure
    assert result.budget_spent == 2
    assert not result.has_budget


def test_loop_marks_blocked_when_policy_denies():
    repo = InMemoryGoalRepository()
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), hourly_budget=0)
    goal = asyncio.run(CreateGoalUseCase(repo).execute("x", "t1", "u1", 5, requires_approval=False))
    goal.status = GoalStatus.BLOCKED  # simulate policy block condition
    loop = AutonomyLoopUseCase(repo, policy, _CountingExecutor())

    result = asyncio.run(loop.run_goal(goal, "t1"))
    assert result.status == GoalStatus.BLOCKED
    assert result.budget_spent == 0


# --------------------------------------------------------------------------- #
#  SelfHeal gating
# --------------------------------------------------------------------------- #


def _failing_tool(name="bad_tool") -> Tool:
    schema = JSONSchema(type="object", properties={})
    tool = Tool(
        name=name,
        description="self-generated tool that fails",
        input_schema=schema,
        output_schema=schema,
        is_self_generated=True,
        use_count=10,
        success_rate=0.1,
    )
    return tool


class _StubGenerator:
    def __init__(self):
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        new_tool = Tool(
            name=request.name + "_v2",
            description="regenerated",
            input_schema=JSONSchema(type="object", properties={}),
            output_schema=JSONSchema(type="object", properties={}),
            is_self_generated=True,
        )
        return SimpleNamespace(tool=new_tool)


def test_self_heal_regenerates_when_allowlisted():
    registry = FakeToolRegistry()
    tool = _failing_tool()
    asyncio.run(registry.register(tool))
    generator = _StubGenerator()
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), allowlist=["tool_selfheal"])
    heal = SelfHealUseCase(registry, generator, policy=policy, tenant_id="t1")

    result = asyncio.run(heal.run())
    assert len(result.regenerated) == 1
    assert generator.calls == 1
    assert tool.status.value == "deprecated"
    assert any(
        e.kind == "regenerated_tool" and "regenerated" in e.detail
        for e in asyncio.run(policy.audit_log("t1"))
    )


def test_self_heal_blocks_without_approval_and_audits():
    registry = FakeToolRegistry()
    asyncio.run(registry.register(_failing_tool()))
    generator = _StubGenerator()
    policy = DefaultAutonomyPolicy(rate_limiter=SlidingWindowRateLimiter(), allowlist=[])
    heal = SelfHealUseCase(registry, generator, policy=policy, tenant_id="t1")

    result = asyncio.run(heal.run())
    assert len(result.blocked) == 1
    assert generator.calls == 0
    log = asyncio.run(policy.audit_log("t1"))
    assert any(e.kind == "regenerated_tool" and "blocked" in e.detail for e in log)


def test_self_heal_skips_without_policy():
    registry = FakeToolRegistry()
    asyncio.run(registry.register(_failing_tool()))
    generator = _StubGenerator()
    heal = SelfHealUseCase(registry, generator)

    result = asyncio.run(heal.run())
    assert len(result.regenerated) == 1


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #


def test_goals_require_auth(app, client):
    _inject(client, app)
    assert client.get("/v1/goals").status_code == 401
    assert client.post("/v1/goals", json={"statement": "x"}).status_code == 401


def test_goals_crud_and_approval_flow(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/goals",
        json={"statement": "optimize recall", "budget_units": 4, "requires_approval": True},
        headers=AUTH_T1,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "proposed"
    assert body["budget_remaining"] == 4
    gid = body["id"]

    r = client.post(f"/v1/goals/{gid}/approve", json={"action": "goal"}, headers=AUTH_T1)
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["approved_by"] == "u1"

    r = client.get(f"/v1/goals/{gid}", headers=AUTH_T1)
    assert r.status_code == 200
    assert r.json()["statement"] == "optimize recall"

    listed = client.get("/v1/goals", headers=AUTH_T1).json()
    assert [g["id"] for g in listed] == [gid]


def test_goal_run_drives_to_completion(app, client):
    _inject(client, app, llm_script={"complete": "GOAL COMPLETE - triage finished"})
    r = client.post(
        "/v1/goals",
        json={"statement": "triage issues", "budget_units": 5, "requires_approval": False},
        headers=AUTH_T1,
    )
    gid = r.json()["id"]
    r = client.post(f"/v1/goals/{gid}/run", headers=AUTH_T1)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["budget_spent"] >= 1
    assert len(body["plan"]) >= 1


def test_goal_run_requires_approval_first(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/goals",
        json={"statement": "anything", "budget_units": 3, "requires_approval": True},
        headers=AUTH_T1,
    )
    gid = r.json()["id"]
    r = client.post(f"/v1/goals/{gid}/run", headers=AUTH_T1)
    assert r.status_code == 409


def test_goal_tenant_isolation(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/goals",
        json={"statement": "tenant one goal", "budget_units": 3, "requires_approval": False},
        headers=AUTH_T1,
    )
    gid = r.json()["id"]

    assert client.get(f"/v1/goals/{gid}", headers=AUTH_T2).status_code == 404
    assert client.get(f"/v1/goals/{gid}", headers=AUTH_T1).status_code == 200
    t2_list = client.get("/v1/goals", headers=AUTH_T2).json()
    assert all(g["statement"] != "tenant one goal" for g in t2_list)


def test_audit_endpoint(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/goals",
        json={"statement": "keep stats", "budget_units": 3, "requires_approval": False},
        headers=AUTH_T1,
    )
    gid = r.json()["id"]
    client.post(f"/v1/goals/{gid}/run", headers=AUTH_T1)

    log = client.get("/v1/goals/audit", headers=AUTH_T1).json()
    assert any(e["kind"] == "approved" for e in log)  # created without approval -> activated
    assert client.get("/v1/goals/audit", headers=AUTH_T2).json() == []
