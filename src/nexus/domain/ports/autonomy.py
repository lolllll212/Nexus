"""
Autonomy policy port - the central guardrail contract for autonomous behavior.

Both explicit goals (the autonomy loop) and implicit self-modification
(SelfHealUseCase regenerating tools) pass every action through this policy so
that budget limits, approval gates, and audit logging are enforced uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from nexus.domain.entities.goal import Goal, GoalEvent


@dataclass
class AutonomyDecision:
    """Result of an authorization check."""
    allowed: bool
    reason: str
    remaining_budget: int = 0

    @property
    def denied(self) -> bool:
        return not self.allowed


class AutonomyPolicy(ABC):
    """Budget + approval + audit guardrail for autonomous actions."""

    @abstractmethod
    async def authorize_action(self, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        """Check the shared per-tenant budget (hourly). Used by implicit
        self-modification (e.g. SelfHealUseCase)."""

    @abstractmethod
    async def authorize_step(self, goal: Goal, tenant_id: str = "default") -> AutonomyDecision:
        """Check goal step budget AND the shared per-tenant budget."""

    @abstractmethod
    async def spend(self, goal: Goal, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        """Decrement a goal's step budget."""

    @abstractmethod
    async def require_approval(self, action: str, actor: str, tenant_id: str = "default") -> bool:
        """Return True when `action` is pre-approved (allowlist or granted)."""

    @abstractmethod
    async def grant_approval(self, action: str, approver: str, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def audit(self, event: GoalEvent, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def pending_approvals(self, tenant_id: str = "default", limit: int = 50) -> list: ...

    @abstractmethod
    async def audit_log(self, tenant_id: str = "default", limit: int = 200) -> list: ...
