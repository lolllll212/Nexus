"""Per-tenant quota enforcement built on the RateLimiter port.

Quotas are daily-window limits (86400s) keyed by tenant + resource, enforced
by the same sliding-window machinery as rate limits — so both the in-memory
and Redis adapters work without extra storage. A limit of 0 means "no quota"
(unlimited), which is the safe default for a fresh deployment.
"""

from __future__ import annotations

from nexus.domain.exceptions import QuotaExceededError, RateLimitExceededError
from nexus.domain.ports.quota import QuotaService
from nexus.domain.ports.rate_limiter import RateLimiter

QUOTA_DAILY_WINDOW_SECONDS = 86400


class RateLimitQuota(QuotaService):
    """Enforces per-tenant daily consumption limits for named resources."""

    def __init__(self, limiter: RateLimiter, limits: dict[str, int]) -> None:
        self._limiter = limiter
        self._limits = limits

    async def check(self, tenant_id: str, resource: str) -> None:
        limit = self._limits.get(resource, 0)
        if limit <= 0:
            return  # unlimited
        key = f"quota:{tenant_id}:{resource}"
        try:
            await self._limiter.check(key, limit, QUOTA_DAILY_WINDOW_SECONDS)
        except RateLimitExceededError as exc:
            raise QuotaExceededError(
                f"Tenant '{tenant_id}' exhausted daily quota for '{resource}' ({limit})"
            ) from exc