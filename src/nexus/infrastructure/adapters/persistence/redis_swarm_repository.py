"""Redis-backed, tenant-scoped swarm repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nexus.domain.entities.swarm import Swarm, SwarmStatus
from nexus.domain.ports.swarm import SwarmRepository


def _swarm_from_dict(data: dict[str, Any]) -> Swarm:
    return Swarm(
        id=data["id"],
        name=data["name"],
        tenant_id=data["tenant_id"],
        owner_id=data["owner_id"],
        leader_id=data["leader_id"],
        worker_ids=data["worker_ids"],
        status=SwarmStatus(data["status"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        metadata=data["metadata"],
    )


class RedisSwarmRepository(SwarmRepository):
    """Swarms stored in Redis hashes, partitioned by tenant."""

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
        return f"nexus:swarms:{tenant_id}"

    async def save(self, swarm: Swarm, tenant_id: str = "default") -> None:
        redis = await self._redis()
        payload = {
            "id": swarm.id,
            "name": swarm.name,
            "tenant_id": swarm.tenant_id,
            "owner_id": swarm.owner_id,
            "leader_id": swarm.leader_id,
            "worker_ids": swarm.worker_ids,
            "status": swarm.status.value,
            "created_at": swarm.created_at.isoformat(),
            "metadata": swarm.metadata,
        }
        await redis.hset(self._key(tenant_id), swarm.id, json.dumps(payload))

    async def get(self, swarm_id: str, tenant_id: str = "default") -> Swarm | None:
        redis = await self._redis()
        payload = await redis.hget(self._key(tenant_id), swarm_id)
        if payload is None:
            return None
        return _swarm_from_dict(json.loads(payload))

    async def list_all(self, tenant_id: str = "default", limit: int = 100) -> list[Swarm]:
        redis = await self._redis()
        payloads = await redis.hvals(self._key(tenant_id))
        swarms = [_swarm_from_dict(json.loads(payload)) for payload in payloads]
        swarms.sort(key=lambda swarm: swarm.created_at)
        return swarms if limit <= 0 else swarms[:limit]

    async def delete(self, swarm_id: str, tenant_id: str = "default") -> None:
        redis = await self._redis()
        await redis.hdel(self._key(tenant_id), swarm_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
