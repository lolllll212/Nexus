"""
PatternDetectionUseCase - subconscious cross-session insight mining.

Runs periodically on accumulated memory, looking for recurring themes:
repeated user problems, repeated technical errors, behavioral patterns.
Surfaces findings as context injections the cortex can use proactively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from nexus.domain.entities.memory import Memory
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import MemoryRepository
from nexus.domain.value_objects.schema import JSONSchema


@dataclass
class PatternInsight:
    pattern: str
    evidence_count: int
    recommendation: str = ""


@dataclass
class PatternDetectionResult:
    insights: List[PatternInsight] = field(default_factory=list)


_PATTERN_SCHEMA = JSONSchema(
    type="object",
    properties={
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": ["pattern"],
            },
        }
    },
    required=["patterns"],
)


class PatternDetectionUseCase:
    """Find recurring structures across recent memory."""

    def __init__(self, llm: LLMProvider, memory_repo: MemoryRepository, event_bus: EventBus) -> None:
        self._llm = llm
        self._memory_repo = memory_repo
        self._event_bus = event_bus

    async def run(self, limit: int = 100) -> PatternDetectionResult:
        result = PatternDetectionResult()

        # Pull the most active memories (highest access counts)
        memories: List[Memory] = []
        for m in await self._memory_repo.retrieve("", limit=limit):
            memories.append(m)

        if len(memories) < 5:
            return result

        try:
            structured = await self._llm.extract_structured(
                "\n---\n".join(m.content for m in memories),
                schema=_PATTERN_SCHEMA,
                instructions=(
                    "Detect recurring patterns in these memories: repeated problems, "
                    "user habits, technical dead-ends. Max 3 patterns."
                ),
            )
        except Exception:
            return result

        for p in structured.get("patterns", []):
            insight = PatternInsight(
                pattern=p["pattern"],
                evidence_count=len(memories),
                recommendation=p.get("recommendation", ""),
            )
            result.insights.append(insight)
            await self._event_bus.publish(
                Event(
                    topic=EventTopic.CONTEXT_INJECTION,
                    payload={"insight": insight.pattern, "recommendation": insight.recommendation},
                    priority=EventPriority.NORMAL,
                )
            )
        return result
