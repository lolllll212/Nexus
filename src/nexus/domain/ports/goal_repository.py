"""
Goal persistence port.

Goals are stored as JSON documents keyed `goal:{tenant_id}:{goal_id}` with an
index `goal:{tenant_id}:active`, so each tenant's autonomous objectives are
isolated at the storage boundary just like memories and concepts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from nexus.domain.entities.goal import Goal, GoalStatus


class GoalRepository(ABC):
    """Persistent storage of autonomous goals."""

    @abstractmethod
    async def save(self, goal: Goal, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def get(self, goal_id: str, tenant_id: str = "default") -> Optional[Goal]: ...

    @abstractmethod
    async def list_by_status(self, status: GoalStatus, tenant_id: str = "default", limit: int = 50) -> List[Goal]: ...

    @abstractmethod
    async def list_active(self, tenant_id: str = "default", limit: int = 50) -> List[Goal]: ...

    @abstractmethod
    async def list_all(self, tenant_id: str = "default", limit: int = 200) -> List[Goal]: ...

    @abstractmethod
    async def delete(self, goal_id: str, tenant_id: str = "default") -> None: ...
