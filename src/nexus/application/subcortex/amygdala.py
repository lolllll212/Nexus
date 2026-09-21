"""
AmygdalaUseCase - valence tagging of data patterns.

The amygdala rapidly tags patterns/memories with survival and utility scores
so the cortex knows what to prioritize: survival-critical items (outages,
security) jump the queue; high-utility items (reusable solutions) get kept
and reinforced.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority
from nexus.domain.value_objects.valence import ValenceTag

_SURVIVAL_TOKENS = {
    "crash",
    "outage",
    "down",
    "security",
    "breach",
    "vulnerability",
    "data loss",
    "corruption",
    "failed",
    "failing",
    "incident",
    "critical",
    "deadlock",
    "panic",
    "emergency",
    "production",
    "downtime",
}
_UTILITY_TOKENS = {
    "reusable",
    "pattern",
    "solution",
    "solved",
    "works",
    "framework",
    "library",
    "api",
    "tutorial",
    "best practice",
    "template",
    "recipe",
    "common",
    "often",
    "frequently",
    "general",
    "generic",
}


@dataclass
class TaggingResult:
    pattern: str
    tag: ValenceTag
    urgent: bool = False


def tag_text(text: str) -> ValenceTag:
    """Score survival/utility in [0,1] from lexical cues."""
    lower = text.lower()
    survival = min(1.0, sum(1 for t in _SURVIVAL_TOKENS if t in lower) / 3.0)
    utility = min(1.0, sum(1 for t in _UTILITY_TOKENS if t in lower) / 3.0)
    return ValenceTag(survival=survival, utility=utility)


class AmygdalaUseCase:
    """Tags patterns and memories with survival/utility priority."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def tag(self, pattern: str) -> TaggingResult:
        tag = tag_text(pattern)
        result = TaggingResult(pattern=pattern, tag=tag, urgent=tag.priority >= 0.5)

        await self._event_bus.publish(
            Event(
                topic=EventTopic.VALENCE_TAGGED,
                payload={
                    "pattern": pattern,
                    "survival": tag.survival,
                    "utility": tag.utility,
                    "priority": tag.priority,
                    "urgent": result.urgent,
                },
                priority=EventPriority.HIGH if result.urgent else EventPriority.NORMAL,
            )
        )
        return result
