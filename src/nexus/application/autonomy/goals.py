"""Autonomy application layer - goal lifecycle and the autonomous loop driver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from nexus.domain.entities.goal import Goal, GoalPriority, GoalStatus, GoalStep, StepStatus
from nexus.domain.exceptions import GoalNotFoundError, GoalStatusError, QuotaExceededError
from nexus.domain.ports.autonomy import AutonomyPolicy
from nexus.domain.ports.goal_repository import GoalRepository


class StepExecutor(Protocol):
    """Executes a single bounded unit of autonomous work."""

    async def run_step(self, goal: Goal, step: GoalStep, tenant_id: str) -> "StepOutcome": ...


@dataclass
class StepOutcome:
    completed: bool
    summary: str


class CreateGoalUseCase:
    """Create a goal; PROPOSED when approval is required, else ACTIVE."""

    def __init__(self, repo: GoalRepository, max_active: int = 0) -> None:
        self._repo = repo

        # Per-tenant ceiling on concurrently active goals. 0 = unlimited.
        self._max_active = max_active

    async def execute(
        self,
        statement: str,
        tenant_id: str,
        owner_id: str,
        budget_units: int,
        priority: GoalPriority = GoalPriority.NORMAL,
        requires_approval: bool = True,
    ) -> Goal:
        if budget_units < 1:
            raise ValueError("budget_units must be >= 1")
        if self._max_active > 0 and not requires_approval:
            existing = await self._repo.list_active(tenant_id=tenant_id, limit=self._max_active)
            if len(existing) >= self._max_active:
                raise QuotaExceededError(f"Tenant '{tenant_id}' hit active goal ceiling ({self._max_active})")
        goal = Goal(
            statement=statement,
            tenant_id=tenant_id,
            owner_id=owner_id,
            budget_units=budget_units,
            priority=priority,
            requires_approval=requires_approval,
        )
        if not requires_approval:
            goal.mark_active(approved_by=owner_id)
        await self._repo.save(goal, tenant_id=tenant_id)
        return goal


class ApproveGoalUseCase:
    """Flip a PROPOSED goal to ACTIVE on human approval."""

    def __init__(self, repo: GoalRepository) -> None:
        self._repo = repo

    async def execute(self, goal_id: str, tenant_id: str, approver: str) -> Goal:
        goal = await self._repo.get(goal_id, tenant_id=tenant_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        if goal.status != GoalStatus.PROPOSED:
            raise GoalStatusError(f"goal {goal_id} is {goal.status.value}, not proposed")
        goal.mark_active(approved_by=approver)
        await self._repo.save(goal, tenant_id=tenant_id)
        return goal


class CancelGoalUseCase:
    """Cancel an unfinished goal (owner/admin only)."""

    def __init__(self, repo: GoalRepository) -> None:
        self._repo = repo

    async def execute(self, goal_id: str, tenant_id: str, actor: str) -> Goal:
        goal = await self._repo.get(goal_id, tenant_id=tenant_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        try:
            goal.cancel(actor)
        except ValueError as exc:
            raise GoalStatusError(str(exc))
        await self._repo.save(goal, tenant_id=tenant_id)
        return goal


class ListGoalsUseCase:
    """Tenant-scoped goal listing."""

    def __init__(self, repo: GoalRepository) -> None:
        self._repo = repo

    async def execute(
        self, tenant_id: str, status: Optional[GoalStatus] = None, limit: int = 50
    ) -> List[Goal]:
        if status is not None:
            return await self._repo.list_by_status(status, tenant_id=tenant_id, limit=limit)
        return await self._repo.list_active(tenant_id=tenant_id, limit=limit)

    async def list_all(self, tenant_id: str, limit: int = 200) -> List[Goal]:
        return await self._repo.list_all(tenant_id=tenant_id, limit=limit)


class GetGoalUseCase:
    """Tenant-scoped goal detail (includes plan + history)."""

    def __init__(self, repo: GoalRepository) -> None:
        self._repo = repo

    async def execute(self, goal_id: str, tenant_id: str) -> Goal:
        goal = await self._repo.get(goal_id, tenant_id=tenant_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return goal


class AutonomyLoopUseCase:
    """Drives an ACTIVE goal to completion within budget."""

    def __init__(self, repo: GoalRepository, policy: AutonomyPolicy, executor: StepExecutor) -> None:
        self._repo = repo
        self._policy = policy
        self._executor = executor

    async def run_goal(self, goal: Goal, tenant_id: str) -> Goal:
        if goal.status != GoalStatus.ACTIVE:
            return goal
        while goal.has_budget and goal.status == GoalStatus.ACTIVE:
            decision = await self._policy.authorize_step(goal, tenant_id)
            if decision.denied:
                goal.mark_blocked(decision.reason)
                break
            step = GoalStep(description=f"autonomous work iteration {goal.budget_spent + 1}")
            goal.plan.append(step)
            step.status = StepStatus.IN_PROGRESS
            outcome = await self._executor.run_step(goal, step, tenant_id)
            await self._policy.spend(goal, tenant_id)
            if outcome.completed:
                step.status = StepStatus.DONE
                step.output = outcome.summary
                goal.mark_completed(outcome.summary)
            else:
                step.status = StepStatus.DONE
                step.output = outcome.summary
        await self._repo.save(goal, tenant_id=tenant_id)
        return goal

    async def run_all_active(self, tenant_id: str = "default", limit: int = 10) -> List[Goal]:
        active = await self._repo.list_active(tenant_id=tenant_id, limit=limit)
        results: List[Goal] = []
        for goal in active:
            results.append(await self.run_goal(goal, tenant_id))
        return results
