"""DefaultAutonomyPolicy - budget + approval + audit guardrail adapter.

Uses the existing RateLimiter for the per-tenant hourly autonomy budget and an
in-memory approval/audit store. Self-modifying actions (tool regeneration,
deployment, code changes) require explicit approval unless they appear in the
tenant's allowlist.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from nexus.domain.entities.goal import Goal, GoalEvent, GoalStatus
from nexus.domain.ports.autonomy import AutonomyDecision, AutonomyPolicy
from nexus.domain.ports.rate_limiter import RateLimiter
from nexus.domain.exceptions import RateLimitExceededError

HOURLY_WINDOW_SECONDS = 3600


class DefaultAutonomyPolicy(AutonomyPolicy):
    """Enforces step budget, hourly budget, approval gate, and audit log."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        hourly_budget: int = 0,
        allowlist: Optional[List[str]] = None,
    ) -> None:
        self._rate_limiter = rate_limiter
        self._hourly_budget = hourly_budget
        self._allowlist: set = set(allowlist or [])
        self._approvals: Dict[tuple, Dict[str, object]] = {}
        self._audit_log: Dict[str, List[GoalEvent]] = {}

    async def authorize_action(self, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        if self._hourly_budget > 0:
            try:
                await self._rate_limiter.check(
                    f"autonomy_hourly:{tenant_id}", self._hourly_budget, HOURLY_WINDOW_SECONDS
                )
            except RateLimitExceededError:
                return AutonomyDecision(False, "per-tenant hourly autonomy budget exceeded")
        return AutonomyDecision(True, "ok")

    async def authorize_step(self, goal: Goal, tenant_id: str = "default") -> AutonomyDecision:
        if goal.status not in (GoalStatus.ACTIVE, GoalStatus.PROPOSED):
            return AutonomyDecision(False, f"goal not active ({goal.status.value})", goal.budget_remaining)
        if not goal.has_budget:
            return AutonomyDecision(False, "goal step budget exhausted", 0)
        return await self.authorize_action(tenant_id)

    async def spend(self, goal: Goal, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        if not goal.spend(units):
            return AutonomyDecision(False, "goal step budget exhausted", 0)
        return AutonomyDecision(True, "budget decremented", goal.budget_remaining)

    async def require_approval(self, action: str, actor: str, tenant_id: str = "default") -> bool:
        if action in self._allowlist:
            return True
        pending = self._approvals.get((tenant_id, action))
        return bool(pending and pending.get("granted") is True)

    async def grant_approval(self, action: str, approver: str, tenant_id: str = "default") -> None:
        self._approvals[(tenant_id, action)] = {"granted": True, "approver": approver}
        await self.audit(GoalEvent(kind="approved", detail=f"action={action}", actor=approver), tenant_id)

    async def audit(self, event: GoalEvent, tenant_id: str = "default") -> None:
        self._audit_log.setdefault(tenant_id, []).append(event)

    async def pending_approvals(self, tenant_id: str = "default", limit: int = 50) -> list:
        pending = [
            {"action": action, "granted": meta.get("granted"), "approver": meta.get("approver")}
            for (tid, action), meta in self._approvals.items()
            if tid == tenant_id
        ]
        return pending[:limit]

    async def audit_log(self, tenant_id: str = "default", limit: int = 200) -> List[GoalEvent]:
        log = self._audit_log.get(tenant_id, [])
        return log[-limit:]


class AllowAllAutonomyPolicy(DefaultAutonomyPolicy):
    """Test/opt-out policy: everything allowed, still audited."""

    async def require_approval(self, action: str, actor: str, tenant_id: str = "default") -> bool:
        return True
