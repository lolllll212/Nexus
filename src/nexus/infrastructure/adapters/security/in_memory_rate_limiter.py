"""In-memory sliding-window rate limiter - used by the memory infra backend.

No external dependencies, single-process only. Prunes expired entries on
each check. Because there is no backing store, an in-memory limiter can
never be "unavailable", so it never raises fail-closed errors.
"""

from __future__ import annotations

import time

from nexus.domain.exceptions import RateLimitExceededError
from nexus.domain.ports.rate_limiter import RateLimiter


class InMemoryRateLimiter(RateLimiter):
    """Sliding-window rate limiter against a local dict of timestamps."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        edge = now - window_seconds
        stamps = [s for s in self._windows.get(key, []) if s > edge]
        stamps.append(now)
        self._windows[key] = stamps
        if len(stamps) > limit:
            raise RateLimitExceededError(
                f"Rate limit exceeded: {len(stamps)}/{limit} requests in {window_seconds}s window"
            )
