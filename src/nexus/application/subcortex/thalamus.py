"""
ThalamicGatingUseCase - central attention gate.

The thalamus is the brain's relay/attention switch. On every cortical event it
estimates task urgency from the payload and re-weights the hexagonal cortical
columns, so resources flow to the columns that matter for the current task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from nexus.domain.ports.cognition import CorticalColumnRegistry
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority


@dataclass
class GatingResult:
    urgency: float
    columns_gated: int = 0
    top_columns: List[str] = field(default_factory=list)


# Lexical cues that signal a high-urgency task.
_URGENT_TOKENS = {
    "urgent",
    "asap",
    "emergency",
    "critical",
    "crash",
    "down",
    "broken",
    "fail",
    "failing",
    "security",
    "vulnerability",
    "now",
    "incident",
    "production",
    "deadline",
    "blocked",
}


def estimate_urgency(text: str, priority: float = 0.0, emotional_arousal: float = 0.0) -> float:
    """Score task urgency in [0,1] from lexical cues + signals."""
    tokens = text.lower().split()
    hits = sum(1 for t in tokens if t.strip(".,!?()") in _URGENT_TOKENS)
    lexical = min(1.0, hits / 3.0)
    return max(lexical, priority, emotional_arousal)


class ThalamicGatingUseCase:
    """Reweights cortical columns based on the current task's urgency."""

    def __init__(self, column_registry: CorticalColumnRegistry, event_bus: EventBus) -> None:
        self._columns = column_registry
        self._event_bus = event_bus

    async def gate(self, message: str, priority: float = 0.0, emotional_arousal: float = 0.0) -> GatingResult:
        urgency = estimate_urgency(message, priority, emotional_arousal)

        columns = await self._columns.list_all()
        for column in columns:
            column.gate(urgency)
            await self._columns.upsert(column)

        top = sorted(columns, key=lambda c: c.effective_weight, reverse=True)
        top_names = [c.name for c in top[:3]]

        await self._event_bus.publish(
            Event(
                topic=EventTopic.ATTENTION_GATED,
                payload={
                    "urgency": urgency,
                    "top_columns": top_names,
                    "weights": {c.name: round(c.effective_weight, 3) for c in columns},
                },
                priority=EventPriority.HIGH if urgency > 0.6 else EventPriority.NORMAL,
            )
        )
        return GatingResult(urgency=urgency, columns_gated=len(columns), top_columns=top_names)
