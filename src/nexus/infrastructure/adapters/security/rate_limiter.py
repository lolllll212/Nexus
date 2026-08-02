"""In-memory sliding-window rate limiter - single-process deployments.

Redis-backed limiters swap in for multi-process runs by implementing the
same RateLimiter port.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque, Dict

from nexus.domain.exceptions import RateLimitExceededError
from nexus.domain.ports.rate_limiter import RateLimiter


class SlidingWindowRateLimiter(RateLimiter):
    """Sliding-window limiter: rejects once a key has `limit` attempts in the
    last `window_seconds`."""

    def __init__(self) -> None:
        self._attempts: Dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        async with self._lock:
            window = self._attempts.setdefault(key, deque())
            while window and window[0] <= now - window_seconds:
                window.popleft()
            if len(window) >= limit:
                raise RateLimitExceededError("Rate limit exceeded; retry later")
            window.append(now)
