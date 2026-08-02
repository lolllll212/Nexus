"""In-memory GoalRepository - dev/test store for autonomous goals."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from nexus.domain.entities.goal import Goal, GoalStatus
from nexus.domain.ports.goal_repository import GoalRepository


class InMemoryGoalRepository(GoalRepository):
    """Goals keyed (tenant_id, goal_id), with an active index per tenant."""

    def __init__(self) -> None:
        self._goals: Dict[Tuple[str, str], Goal] = {}

    def _key(self, goal_id: str, tenant_id: str) -> Tuple[str, str]:
        return (tenant_id, goal_id)

    async def save(self, goal: Goal, tenant_id: str = "default") -> None:
        self._goals[self._key(goal.id, tenant_id)] = goal

    async def get(self, goal_id: str, tenant_id: str = "default") -> Optional[Goal]:
        return self._goals.get(self._key(goal_id, tenant_id))

    async def list_by_status(self, status: GoalStatus, tenant_id: str = "default", limit: int = 50) -> List[Goal]:
        results = [g for (t, _), g in self._goals.items() if t == tenant_id and g.status == status]
        results.sort(key=lambda g: g.updated_at, reverse=True)
        return results[:limit]

    async def list_active(self, tenant_id: str = "default", limit: int = 50) -> List[Goal]:
        return await self.list_by_status(GoalStatus.ACTIVE, tenant_id=tenant_id, limit=limit)

    async def list_all(self, tenant_id: str = "default", limit: int = 200) -> List[Goal]:
        results = [g for (t, _), g in self._goals.items() if t == tenant_id]
        results.sort(key=lambda g: g.updated_at, reverse=True)
        return results[:limit]

    async def delete(self, goal_id: str, tenant_id: str = "default") -> None:
        self._goals.pop(self._key(goal_id, tenant_id), None)
