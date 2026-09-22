"""Redis rate limiter fail-open / fail-closed behavior."""

from unittest.mock import AsyncMock

import pytest

from nexus.domain.exceptions import RateLimitExceededError
from nexus.infrastructure.adapters.security.redis_rate_limiter import RedisRateLimiter


@pytest.mark.asyncio
async def test_fail_open_skips_when_redis_unavailable():
    limiter = RedisRateLimiter(fail_closed=False)
    limiter._get_redis = AsyncMock(return_value=None)

    await limiter.check("user:1", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_fail_closed_denies_when_redis_unavailable():
    limiter = RedisRateLimiter(fail_closed=True)
    limiter._get_redis = AsyncMock(return_value=None)

    with pytest.raises(RateLimitExceededError):
        await limiter.check("user:1", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_fail_closed_denies_on_redis_execution_error():
    limiter = RedisRateLimiter(fail_closed=True)

    class BrokenRedis:
        def pipeline(self):
            raise ConnectionError("redis is down")

    limiter._get_redis = AsyncMock(return_value=BrokenRedis())

    with pytest.raises(RateLimitExceededError):
        await limiter.check("user:1", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_fail_open_skips_on_redis_execution_error():
    limiter = RedisRateLimiter(fail_closed=False)

    class BrokenRedis:
        def pipeline(self):
            raise ConnectionError("redis is down")

    limiter._get_redis = AsyncMock(return_value=BrokenRedis())

    await limiter.check("user:1", limit=1, window_seconds=60)
