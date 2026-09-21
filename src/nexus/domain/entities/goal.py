"""Domain goal entity - autonomous objectives NEXUS pursues on its own."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4


class GoalStatus(Enum):
    """Lifecycle states of a goal."""

    PROPOSED = "proposed"  # awaiting approval (if approval required)
    ACTIVE = "active"  # autonomy loop is working it
    BLOCKED = "blocked"  # needs human input / budget exhausted
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GoalPriority(Enum):
    """Urgency ranking, drives scheduling order."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class StepStatus(Enum):
    """Lifecycle states of a single goal step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GoalStep:
    """A single bounded unit of work within a goal's plan."""

    description: str
    status: StepStatus = StepStatus.PENDING
    tool: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None


@dataclass
class GoalEvent:
    """Append-only audit entry in a goal's lifecycle ledger."""

    kind: str  # step_started|step_completed|step_failed|budget_decremented|approved|rejected|cancelled|regenerated_tool
    detail: str
    actor: str = "system"
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Goal:
    """A persistent autonomous objective, bounded by budget and guarded by policy."""

    statement: str
    tenant_id: str
    owner_id: str
    budget_units: int
    id: str = field(default_factory=lambda: str(uuid4()))
    status: GoalStatus = GoalStatus.PROPOSED
    priority: GoalPriority = GoalPriority.NORMAL
    budget_spent: int = 0
    max_cost_per_step: float = 1.0
    requires_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None
    plan: List[GoalStep] = field(default_factory=list)
    result: Optional[str] = None
    history: List[GoalEvent] = field(default_factory=list)

    @property
    def budget_remaining(self) -> int:
        return max(0, self.budget_units - self.budget_spent)

    @property
    def has_budget(self) -> bool:
        return self.budget_spent < self.budget_units

    def log(self, kind: str, detail: str, actor: str = "system") -> None:
        self.history.append(GoalEvent(kind=kind, detail=detail, actor=actor))
        self.updated_at = datetime.utcnow()

    def mark_active(self, approved_by: Optional[str] = None) -> None:
        self.status = GoalStatus.ACTIVE
        if approved_by:
            self.approved_by = approved_by
            self.approved_at = datetime.utcnow()
        self.log("approved" if approved_by else "activated", f"activated by {approved_by or 'system'}")

    def mark_blocked(self, reason: str) -> None:
        self.status = GoalStatus.BLOCKED
        self.log("blocked", reason)

    def mark_completed(self, result: str) -> None:
        self.status = GoalStatus.COMPLETED
        self.result = result
        self.log("completed", result[:200])

    def mark_failed(self, reason: str) -> None:
        self.status = GoalStatus.FAILED
        self.log("failed", reason[:200])

    def cancel(self, actor: str) -> None:
        if self.status in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED):
            raise ValueError(f"Cannot cancel goal in state {self.status.value}")
        self.status = GoalStatus.CANCELLED
        self.log("cancelled", f"cancelled by {actor}", actor=actor)

    def spend(self, units: int = 1) -> bool:
        """Consume budget. Returns False if the budget would be exceeded."""
        if self.budget_spent + units > self.budget_units:
            return False
        self.budget_spent += units
        self.log("budget_decremented", f"spent {units} unit(s)")
        return True
