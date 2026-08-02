"""
Redis ShortTermMemory adapter - ephemeral working memory + pub/sub.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

from nexus.domain.ports.memory_repository import ShortTermMemory


class RedisShortTermMemory(ShortTermMemory):
    """ShortTermMemory backed by Redis."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)

    async def set(self, key: str, value: Dict, ttl_seconds: int) -> None:
        await self._redis.setex(key, ttl_seconds, json.dumps(value))

    async def get(self, key: str) -> Optional[Dict]:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def publish(self, channel: str, payload: Dict) -> None:
        await self._redis.publish(channel, json.dumps(payload))

    async def close(self) -> None:
        await self._redis.aclose()
