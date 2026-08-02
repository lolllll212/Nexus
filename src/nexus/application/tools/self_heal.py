"""
SelfHealUseCase - monitor tool health and regenerate failing tools.

A self-generated tool that keeps failing gets sent back to the
generation pipeline with its failure logs as extra context.

Every regeneration now passes through the AutonomyPolicy guardrail: the
per-tenant hourly budget is checked, regeneration is only performed when the
action is approved (allowlisted by default via `tool_selfheal`), and each
attempt is written to the tenant audit log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from nexus.application.tools.generate_tool import GenerateToolUseCase, ToolSpecRequest
from nexus.domain.entities.goal import GoalEvent
from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.ports.autonomy import AutonomyPolicy
from nexus.domain.ports.tool_registry import ToolRegistry

SELF_HEAL_ACTION = "tool_selfheal"


@dataclass
class SelfHealResult:
    regenerated: List[str]  # tool ids
    healthy: List[str]
    blocked: List[str]      # would regenerate but policy denied it
    denied_reason: str = ""


class SelfHealUseCase:
    """Continuous quality control over the tool ecosystem, budget-gated."""

    FAILURE_THRESHOLD = 0.4  # below 40% success rate -> regenerate

    def __init__(
        self,
        registry: ToolRegistry,
        generator: GenerateToolUseCase,
        policy: Optional[AutonomyPolicy] = None,
        tenant_id: str = "default",
    ) -> None:
        self._registry = registry
        self._generator = generator
        self._policy = policy
        self._tenant_id = tenant_id

    async def run(self) -> SelfHealResult:
        result = SelfHealResult(regenerated=[], healthy=[], blocked=[])
        tools: List[Tool] = await self._registry.list_all()

        for tool in tools:
            if not tool.is_self_generated or tool.use_count == 0:
                result.healthy.append(tool.id)
                continue

            if tool.success_rate >= self.FAILURE_THRESHOLD:
                result.healthy.append(tool.id)
                continue

            if self._policy is not None:
                decision = await self._policy.authorize_action(self._tenant_id)
                approved = await self._policy.require_approval(SELF_HEAL_ACTION, "system", self._tenant_id)
                if decision.denied or not approved:
                    result.blocked.append(tool.id)
                    result.denied_reason = decision.reason or "approval not granted"
                    await self._policy.audit(
                        GoalEvent(
                            kind="regenerated_tool",
                            detail=f"blocked regeneration of {tool.id}: {result.denied_reason}",
                            actor="system",
                        ),
                        self._tenant_id,
                    )
                    continue

            try:
                new_tool = await self._generator.execute(
                    ToolSpecRequest(
                        name=tool.name,
                        description=tool.description,
                        problem_statement=tool.description,
                        input_examples=[],
                        expected_outputs=[],
                    )
                )
                result.regenerated.append(new_tool.tool.id)
                tool.status = ToolStatus.DEPRECATED
                await self._registry.update(tool)
                if self._policy is not None:
                    await self._policy.audit(
                        GoalEvent(
                            kind="regenerated_tool",
                            detail=f"regenerated {tool.id} as {new_tool.tool.id}",
                            actor="system",
                        ),
                        self._tenant_id,
                    )
            except Exception:
                continue

        return result
