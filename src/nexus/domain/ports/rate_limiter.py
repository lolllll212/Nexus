"""Rate limiting port - protects public endpoints from abuse."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RateLimiter(ABC):
    """Tracks attempts for a key over a sliding window.

    The adapter owns the storage and eviction policy. The application layer
    only asks "may this key proceed?".
    """

    @abstractmethod
    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        """Record an attempt for `key`; raise RateLimitExceededError when the
        sliding window for `key` already contains `limit` attempts."""
        ...
