"""Redis-backed, tenant-scoped goal repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nexus.domain.entities.goal import Goal, GoalEvent, GoalPriority, GoalStatus, GoalStep, StepStatus
from nexus.domain.ports.goal_repository import GoalRepository


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _goal_to_dict(goal: Goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "statement": goal.statement,
        "tenant_id": goal.tenant_id,
        "owner_id": goal.owner_id,
        "budget_units": goal.budget_units,
        "status": goal.status.value,
        "priority": goal.priority.value,
        "budget_spent": goal.budget_spent,
        "max_cost_per_step": goal.max_cost_per_step,
        "requires_approval": goal.requires_approval,
        "approved_by": goal.approved_by,
        "approved_at": goal.approved_at.isoformat() if goal.approved_at else None,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "plan": [
            {
                "description": step.description,
                "status": step.status.value,
                "tool": step.tool,
                "output": step.output,
                "error": step.error,
            }
            for step in goal.plan
        ],
        "result": goal.result,
        "history": [
            {
                "kind": event.kind,
                "detail": event.detail,
                "actor": event.actor,
                "ts": event.ts.isoformat(),
            }
            for event in goal.history
        ],
    }


def _goal_from_dict(data: dict[str, Any]) -> Goal:
    return Goal(
        id=data["id"],
        statement=data["statement"],
        tenant_id=data["tenant_id"],
        owner_id=data["owner_id"],
        budget_units=data["budget_units"],
        status=GoalStatus(data["status"]),
        priority=GoalPriority(data["priority"]),
        budget_spent=data["budget_spent"],
        max_cost_per_step=data["max_cost_per_step"],
        requires_approval=data["requires_approval"],
        approved_by=data["approved_by"],
        approved_at=_datetime(data["approved_at"]),
        created_at=_datetime(data["created_at"]),
        updated_at=_datetime(data["updated_at"]),
        deadline=_datetime(data["deadline"]),
        plan=[
            GoalStep(
                description=step["description"],
                status=StepStatus(step["status"]),
                tool=step["tool"],
                output=step["output"],
                error=step["error"],
            )
            for step in data["plan"]
        ],
        result=data["result"],
        history=[
            GoalEvent(
                kind=event["kind"],
                detail=event["detail"],
                actor=event["actor"],
                ts=_datetime(event["ts"]),
            )
            for event in data["history"]
        ],
    )


class RedisGoalRepository(GoalRepository):
    """Goals stored in Redis hashes, partitioned by tenant."""

    def __init__(self, redis_url: str = "redis://localhost:6379", client: Any | None = None) -> None:
        self._redis_url = redis_url
        self._client = client

    async def _redis(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _key(tenant_id: str) -> str:
        return f"nexus:goals:{tenant_id}"

    async def save(self, goal: Goal, tenant_id: str = "default") -> None:
        redis = await self._redis()
        await redis.hset(self._key(tenant_id), goal.id, json.dumps(_goal_to_dict(goal)))

    async def get(self, goal_id: str, tenant_id: str = "default") -> Goal | None:
        redis = await self._redis()
        payload = await redis.hget(self._key(tenant_id), goal_id)
        return _goal_from_dict(json.loads(payload)) if payload is not None else None

    async def list_by_status(
        self, status: GoalStatus, tenant_id: str = "default", limit: int = 50
    ) -> list[Goal]:
        goals = await self.list_all(tenant_id=tenant_id, limit=0)
        return [goal for goal in goals if goal.status == status][:limit]

    async def list_active(self, tenant_id: str = "default", limit: int = 50) -> list[Goal]:
        return await self.list_by_status(GoalStatus.ACTIVE, tenant_id=tenant_id, limit=limit)

    async def list_all(self, tenant_id: str = "default", limit: int = 200) -> list[Goal]:
        redis = await self._redis()
        payloads = await redis.hvals(self._key(tenant_id))
        goals = [_goal_from_dict(json.loads(payload)) for payload in payloads]
        goals.sort(key=lambda goal: goal.updated_at, reverse=True)
        return goals if limit <= 0 else goals[:limit]

    async def delete(self, goal_id: str, tenant_id: str = "default") -> None:
        redis = await self._redis()
        await redis.hdel(self._key(tenant_id), goal_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
