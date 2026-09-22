"""Redis-backed sliding-window rate limiter.

Survives multi-process deployments and server restarts. Falls back to
in-memory when Redis is unavailable (single-process dev mode) — unless
`fail_closed` is set, in which case outages deny requests instead.
"""

from __future__ import annotations

import time

from nexus.domain.exceptions import RateLimitExceededError
from nexus.domain.ports.rate_limiter import RateLimiter


class RedisRateLimiter(RateLimiter):
    """Sliding-window rate limiter backed by Redis sorted sets.

    Each key maps to a Redis sorted set of timestamps. Old entries are
    pruned on each check — O(log N) per operation.

    When Redis is unreachable and `fail_closed` is False (default) the
    check is skipped so single-process dev setups keep working without
    Redis. With `fail_closed=True` a Redis outage raises
    `RateLimitExceededError` instead, so a burst of traffic during an
    outage is denied rather than let through unthrottled.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", fail_closed: bool = False) -> None:
        self._redis_url = redis_url
        self._fail_closed = fail_closed
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except Exception:
                return None
        return self._redis

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        r = await self._get_redis()
        if r is None:
            if self._fail_closed:
                raise RateLimitExceededError(
                    "Rate limiting backend unavailable; request denied (fail-closed)"
                )
            # Fallback: no-op when Redis unavailable (dev mode only)
            return

        now = time.time()
        redis_key = f"nexus:ratelimit:{key}"
        window_start = now - window_seconds

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds)
            results = await pipe.execute()
        except Exception:
            if self._fail_closed:
                raise RateLimitExceededError(
                    "Rate limiting backend unavailable; request denied (fail-closed)"
                )
            # Fallback: no-op when Redis unavailable (dev mode only)
            return

        count = results[2]
        if count > limit:
            raise RateLimitExceededError(
                f"Rate limit exceeded: {count}/{limit} requests in {window_seconds}s window"
            )
