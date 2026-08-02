"""LLM-backed GoalStepExecutor - runs one autonomy iteration through the cortex."""

from __future__ import annotations

from nexus.application.autonomy.goals import StepOutcome
from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.domain.entities.goal import Goal, GoalStep

_DONE_MARKERS = ("GOAL COMPLETE", "[DONE]", "objective achieved")


class CortexStepExecutor:
    """Executes an autonomy iteration as a full ReAct turn on the cortex.

    The goal statement seeds a dedicated working-memory session
    (`goal:{tenant_id}:{goal_id}`); the LLM's response is the step output.
    """

    def __init__(self, process_message: ProcessMessageUseCase) -> None:
        self._process_message = process_message

    async def run_step(self, goal: Goal, step: GoalStep, tenant_id: str) -> StepOutcome:
        message = f"[Autonomous goal] {goal.statement}. Work item: {step.description}"
        result = await self._process_message.execute(
            user_id=goal.owner_id,
            message=message,
            session_id=f"goal:{goal.id}",
            tenant_id=tenant_id,
        )
        output = result.response if hasattr(result, "response") else str(result)
        completed = any(marker in output.upper() for marker in _DONE_MARKERS)
        return StepOutcome(completed=completed, summary=output)
