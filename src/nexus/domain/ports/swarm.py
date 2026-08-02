"""
Agent + swarm persistence ports (Phase 4).

Both persist as JSON documents keyed `agent:{tenant_id}:{id}` /
`swarm:{tenant_id}:{id}`, so each tenant's agents are isolated at the storage
boundary just like memories, concepts, and goals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.swarm import Swarm


class AgentRepository(ABC):
    """Persistent storage of swarm agents."""

    @abstractmethod
    async def save(self, agent: Agent, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def get(self, agent_id: str, tenant_id: str = "default") -> Optional[Agent]: ...

    @abstractmethod
    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Agent]: ...

    @abstractmethod
    async def list_by_role(self, role: str, tenant_id: str = "default", limit: int = 100) -> List[Agent]: ...

    @abstractmethod
    async def delete(self, agent_id: str, tenant_id: str = "default") -> None: ...


class SwarmRepository(ABC):
    """Persistent storage of swarms."""

    @abstractmethod
    async def save(self, swarm: Swarm, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def get(self, swarm_id: str, tenant_id: str = "default") -> Optional[Swarm]: ...

    @abstractmethod
    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Swarm]: ...

    @abstractmethod
    async def delete(self, swarm_id: str, tenant_id: str = "default") -> None: ...
