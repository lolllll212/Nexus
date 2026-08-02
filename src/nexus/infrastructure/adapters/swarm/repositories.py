"""In-memory Agent + Swarm repositories - dev/test stores."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.swarm import Swarm
from nexus.domain.ports.swarm import AgentRepository, SwarmRepository


class InMemoryAgentRepository(AgentRepository):
    """Agents keyed (tenant_id, agent_id)."""

    def __init__(self) -> None:
        self._agents: Dict[Tuple[str, str], Agent] = {}

    async def save(self, agent: Agent, tenant_id: str = "default") -> None:
        self._agents[(tenant_id, agent.id)] = agent

    async def get(self, agent_id: str, tenant_id: str = "default") -> Optional[Agent]:
        return self._agents.get((tenant_id, agent_id))

    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Agent]:
        results = [a for (t, _), a in self._agents.items() if t == tenant_id]
        results.sort(key=lambda a: a.created_at)
        return results[:limit]

    async def list_by_role(self, role: str, tenant_id: str = "default", limit: int = 100) -> List[Agent]:
        results = [a for (t, _), a in self._agents.items() if t == tenant_id and a.role == role]
        results.sort(key=lambda a: a.created_at)
        return results[:limit]

    async def delete(self, agent_id: str, tenant_id: str = "default") -> None:
        self._agents.pop((tenant_id, agent_id), None)


class InMemorySwarmRepository(SwarmRepository):
    """Swarms keyed (tenant_id, swarm_id)."""

    def __init__(self) -> None:
        self._swarms: Dict[Tuple[str, str], Swarm] = {}

    async def save(self, swarm: Swarm, tenant_id: str = "default") -> None:
        self._swarms[(tenant_id, swarm.id)] = swarm

    async def get(self, swarm_id: str, tenant_id: str = "default") -> Optional[Swarm]:
        return self._swarms.get((tenant_id, swarm_id))

    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Swarm]:
        results = [s for (t, _), s in self._swarms.items() if t == tenant_id]
        results.sort(key=lambda s: s.created_at)
        return results[:limit]

    async def delete(self, swarm_id: str, tenant_id: str = "default") -> None:
        self._swarms.pop((tenant_id, swarm_id), None)
