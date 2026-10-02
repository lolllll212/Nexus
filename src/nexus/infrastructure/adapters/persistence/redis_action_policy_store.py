"""Redis-backed state/action Q-value store."""

from __future__ import annotations

import json
from typing import Any

from nexus.domain.ports.cognition import ActionPolicyStore


class RedisActionPolicyStore(ActionPolicyStore):
    """Persist Q-values in Redis hashes, shared by API and worker processes."""

    def __init__(self, redis_url: str = "redis://localhost:6379", client: Any | None = None) -> None:
        self._redis_url = redis_url
        self._client = client

    async def _redis(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _key(state_key: str) -> str:
        return f"nexus:action-policy:{state_key}"

    async def get_value(self, state_key: str, action_id: str) -> float:
        redis = await self._redis()
        value = await redis.hget(self._key(state_key), action_id)
        return float(value) if value is not None else 0.0

    async def set_value(self, state_key: str, action_id: str, value: float) -> None:
        redis = await self._redis()
        await redis.hset(self._key(state_key), action_id, json.dumps(float(value)))

    async def get_state(self, state_key: str) -> dict[str, float]:
        redis = await self._redis()
        values = await redis.hgetall(self._key(state_key))
        return {action_id: float(value) for action_id, value in values.items()}

    async def reset(self, state_key: str) -> None:
        redis = await self._redis()
        await redis.delete(self._key(state_key))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
