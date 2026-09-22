"""Per-tenant quota port - hard limits on long-horizon resource usage.

Rate limits (RateLimiter) protect against request bursts. Quotas are the
slower, coarser guardrail: how many of a resource a tenant may consume over
a day or per-tenant budget (memories stored, tool generations, autonomous
units). Enforced before the expensive work starts so abuse fails fast.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class QuotaService(ABC):
    """Checks a tenant's consumption of a named resource against a limit."""

    @abstractmethod
    async def check(self, tenant_id: str, resource: str) -> None:
        """Record one unit of consumption and raise QuotaExceededError when
        the tenant has exhausted its quota for `resource`."""
        ...