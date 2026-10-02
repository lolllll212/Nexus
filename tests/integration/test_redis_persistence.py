from __future__ import annotations

from collections import defaultdict

from redis.exceptions import ConnectionError as RedisConnectionError

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.goal import Goal, GoalEvent, GoalPriority, GoalStatus, GoalStep, StepStatus
from nexus.domain.entities.swarm import Swarm, SwarmStatus
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.persistence.redis_action_policy_store import RedisActionPolicyStore
from nexus.infrastructure.adapters.persistence.redis_agent_repository import RedisAgentRepository
from nexus.infrastructure.adapters.persistence.redis_autonomy_policy import RedisAutonomyPolicy
from nexus.infrastructure.adapters.persistence.redis_goal_repository import RedisGoalRepository
from nexus.infrastructure.adapters.persistence.redis_swarm_repository import RedisSwarmRepository
from nexus.infrastructure.di.container import Config, Container


class SharedRedis:
    """Small async Redis test double shared between independent adapters."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self.lists: dict[str, list[str]] = defaultdict(list)

    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes[key][field] = value

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes[key].get(field)

    async def hvals(self, key: str) -> list[str]:
        return list(self.hashes[key].values())

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes[key])

    async def hdel(self, key: str, field: str) -> None:
        self.hashes[key].pop(field, None)

    async def delete(self, key: str) -> None:
        self.hashes.pop(key, None)

    async def rpush(self, key: str, value: str) -> None:
        self.lists[key].append(value)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.lists[key]
        stop = len(values) if end == -1 else end + 1
        return values[start:stop]

    async def aclose(self) -> None:
        pass


async def test_shared_redis_persists_goals_agents_swarms_and_policy_state() -> None:
    redis = SharedRedis()
    goals_a = RedisGoalRepository(client=redis)
    goals_b = RedisGoalRepository(client=redis)
    agents_a = RedisAgentRepository(client=redis)
    agents_b = RedisAgentRepository(client=redis)
    swarms_a = RedisSwarmRepository(client=redis)
    swarms_b = RedisSwarmRepository(client=redis)
    policies_a = RedisActionPolicyStore(client=redis)
    policies_b = RedisActionPolicyStore(client=redis)

    goal = Goal(
        id="goal-1",
        statement="ship persisted state",
        tenant_id="tenant-a",
        owner_id="owner",
        budget_units=4,
        status=GoalStatus.ACTIVE,
        priority=GoalPriority.HIGH,
        plan=[GoalStep(description="test", status=StepStatus.DONE)],
        history=[GoalEvent(kind="created", detail="started")],
    )
    agent = Agent(
        id="agent-1",
        name="worker",
        tenant_id="tenant-a",
        owner_id="owner",
        system_prompt="work",
        role="worker",
        tools=["calculator"],
    )
    swarm = Swarm(
        id="swarm-1",
        name="team",
        tenant_id="tenant-a",
        owner_id="owner",
        leader_id="agent-1",
        worker_ids=["agent-1"],
        status=SwarmStatus.RUNNING,
    )

    await goals_a.save(goal, tenant_id="tenant-a")
    await agents_a.save(agent, tenant_id="tenant-a")
    await swarms_a.save(swarm, tenant_id="tenant-a")
    await policies_a.set_value("state", "action", 0.75)

    assert (await goals_b.get("goal-1", "tenant-a")).plan[0].status == StepStatus.DONE
    assert await goals_b.get("goal-1", "tenant-b") is None
    assert [item.id for item in await goals_b.list_active("tenant-a")] == ["goal-1"]
    assert (await agents_b.get("agent-1", "tenant-a")).tools == ["calculator"]
    assert (await agents_b.list_by_role("worker", "tenant-a"))[0].id == "agent-1"
    assert (await swarms_b.get("swarm-1", "tenant-a")).worker_ids == ["agent-1"]
    assert (await swarms_b.list_all("tenant-a"))[0].status == SwarmStatus.RUNNING
    assert await policies_b.get_value("state", "action") == 0.75
    assert await policies_b.get_state("state") == {"action": 0.75}

    await agents_a.delete("agent-1", "tenant-a")
    await swarms_a.delete("swarm-1", "tenant-a")
    await goals_a.delete("goal-1", "tenant-a")
    assert await goals_b.get("goal-1", "tenant-a") is None
    assert await agents_b.get("agent-1", "tenant-a") is None
    assert await swarms_b.get("swarm-1", "tenant-a") is None


async def test_autonomy_approvals_and_audit_are_shared_and_tenant_scoped() -> None:
    redis = SharedRedis()
    rate_limiter = object()
    policy_a = RedisAutonomyPolicy(
        DefaultAutonomyPolicy(rate_limiter=rate_limiter),
        client=redis,
    )
    policy_b = RedisAutonomyPolicy(
        DefaultAutonomyPolicy(rate_limiter=rate_limiter),
        client=redis,
    )

    assert not await policy_b.require_approval("deploy", "agent", tenant_id="tenant-a")
    await policy_a.grant_approval("deploy", "owner", tenant_id="tenant-a")
    assert await policy_b.require_approval("deploy", "agent", tenant_id="tenant-a")
    assert not await policy_b.require_approval("deploy", "agent", tenant_id="tenant-b")
    assert (await policy_b.pending_approvals("tenant-a"))[0]["approver"] == "owner"
    events = await policy_b.audit_log("tenant-a")
    assert len(events) == 1 and events[0].kind == "approved"

    await policy_a.audit(GoalEvent(kind="step_completed", detail="done"), tenant_id="tenant-a")
    assert [event.kind for event in await policy_b.audit_log("tenant-a")] == [
        "approved",
        "step_completed",
    ]


async def test_autonomy_policy_falls_back_explicitly_when_redis_is_unavailable() -> None:
    class UnavailableRedis:
        async def hset(self, *args, **kwargs) -> None:
            raise RedisConnectionError("redis unavailable")

        async def hget(self, *args, **kwargs):
            raise RedisConnectionError("redis unavailable")

        async def hgetall(self, *args, **kwargs):
            raise RedisConnectionError("redis unavailable")

        async def rpush(self, *args, **kwargs) -> None:
            raise RedisConnectionError("redis unavailable")

        async def lrange(self, *args, **kwargs):
            raise RedisConnectionError("redis unavailable")

    policy = RedisAutonomyPolicy(
        DefaultAutonomyPolicy(rate_limiter=object()),
        client=UnavailableRedis(),
    )
    await policy.grant_approval("deploy", "owner", tenant_id="tenant-a")
    assert await policy.require_approval("deploy", "agent", tenant_id="tenant-a")
    assert (await policy.pending_approvals("tenant-a"))[0]["approver"] == "owner"
    assert [event.kind for event in await policy.audit_log("tenant-a")] == ["approved"]


async def test_container_selects_redis_adapters_and_preserves_memory_backend() -> None:
    memory = Container(Config(infra_backend="memory", sandbox_backend="subprocess"))
    assert memory.goal_repo.__class__.__name__ == "InMemoryGoalRepository"
    assert memory.agent_repo.__class__.__name__ == "InMemoryAgentRepository"
    assert memory.swarm_repo.__class__.__name__ == "InMemorySwarmRepository"
    assert memory.policy_store.__class__.__name__ == "InMemoryActionPolicyStore"
    assert memory.autonomy_policy.__class__.__name__ == "DefaultAutonomyPolicy"

    external = Container(Config(infra_backend="external", sandbox_backend="subprocess"))
    assert external.goal_repo.__class__.__name__ == "RedisGoalRepository"
    assert external.agent_repo.__class__.__name__ == "RedisAgentRepository"
    assert external.swarm_repo.__class__.__name__ == "RedisSwarmRepository"
    assert external.policy_store.__class__.__name__ == "RedisActionPolicyStore"
    assert external.autonomy_policy.__class__.__name__ == "RedisAutonomyPolicy"
