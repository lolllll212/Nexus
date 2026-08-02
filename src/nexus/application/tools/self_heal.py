"""
SelfHealUseCase - monitor tool health and regenerate failing tools.

A self-generated tool that keeps failing gets sent back to the
generation pipeline with its failure logs as extra context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from nexus.application.tools.generate_tool import GenerateToolUseCase, ToolSpecRequest
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.tool_registry import ToolRegistry


@dataclass
class SelfHealResult:
    regenerated: List[str]  # tool ids
    healthy: List[str]


class SelfHealUseCase:
    """Continuous quality control over the tool ecosystem."""

    FAILURE_THRESHOLD = 0.4  # below 40% success rate -> regenerate

    def __init__(self, registry: ToolRegistry, generator: GenerateToolUseCase) -> None:
        self._registry = registry
        self._generator = generator

    async def run(self) -> SelfHealResult:
        result = SelfHealResult(regenerated=[], healthy=[])
        tools: List[Tool] = await self._registry.list_all()

        for tool in tools:
            if not tool.is_self_generated or tool.use_count == 0:
                result.healthy.append(tool.id)
                continue

            if tool.success_rate < self.FAILURE_THRESHOLD:
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
                    tool.status = __import__("nexus.domain.entities.tool", fromlist=["ToolStatus"]).ToolStatus.DEPRECATED
                    await self._registry.update(tool)
                except Exception:
                    continue
            else:
                result.healthy.append(tool.id)

        return result
