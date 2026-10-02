"""Redis-backed, tenant-scoped agent repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nexus.domain.entities.agent import Agent, AgentStatus
from nexus.domain.ports.swarm import AgentRepository


def _agent_from_dict(data: dict[str, Any]) -> Agent:
    return Agent(
        id=data["id"],
        name=data["name"],
        tenant_id=data["tenant_id"],
        owner_id=data["owner_id"],
        system_prompt=data["system_prompt"],
        role=data["role"],
        tools=data["tools"],
        status=AgentStatus(data["status"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        metadata=data["metadata"],
    )


class RedisAgentRepository(AgentRepository):
    """Agents stored in Redis hashes, partitioned by tenant."""

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
        return f"nexus:agents:{tenant_id}"

    async def save(self, agent: Agent, tenant_id: str = "default") -> None:
        redis = await self._redis()
        payload = {
            "id": agent.id,
            "name": agent.name,
            "tenant_id": agent.tenant_id,
            "owner_id": agent.owner_id,
            "system_prompt": agent.system_prompt,
            "role": agent.role,
            "tools": agent.tools,
            "status": agent.status.value,
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
            "metadata": agent.metadata,
        }
        await redis.hset(self._key(tenant_id), agent.id, json.dumps(payload))

    async def get(self, agent_id: str, tenant_id: str = "default") -> Agent | None:
        redis = await self._redis()
        payload = await redis.hget(self._key(tenant_id), agent_id)
        if payload is None:
            return None
        return _agent_from_dict(json.loads(payload))

    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> list[Agent]:
        redis = await self._redis()
        payloads = await redis.hvals(self._key(tenant_id))
        agents = [_agent_from_dict(json.loads(payload)) for payload in payloads]
        agents.sort(key=lambda agent: agent.created_at)
        return agents if limit <= 0 else agents[:limit]

    async def list_by_role(self, role: str, tenant_id: str = "default", limit: int = 100) -> list[Agent]:
        agents = await self.list_all(tenant_id=tenant_id, limit=0)
        return [agent for agent in agents if agent.role == role][:limit]

    async def delete(self, agent_id: str, tenant_id: str = "default") -> None:
        redis = await self._redis()
        await redis.hdel(self._key(tenant_id), agent_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
