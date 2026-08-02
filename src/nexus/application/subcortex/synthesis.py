"""
EntitySynthesisUseCase - subconscious continuous synthesis.

Listens to user-message events and quietly:
  1. Extracts entities/concepts from the new content
  2. Upserts them into the synaptic graph
  3. Cross-references with existing strong connections
  4. If a non-obvious connection is found with high confidence,
     injects a "realization" back into the conscious loop.

This runs in the subcortex. It never blocks the cortex.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from nexus.domain.entities.concept import Concept
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository
from nexus.domain.value_objects.synapse import ConnectionType


@dataclass
class ExtractedEntity:
    label: str
    concept_type: str
    description: str = ""


class EntitySynthesisUseCase:
    """Background entity extraction + graph enrichment."""

    CONTEXT_INJECTION_THRESHOLD = 0.85

    def __init__(
        self,
        llm: LLMProvider,
        concept_repo: ConceptRepository,
        memory_repo: MemoryRepository,
        event_bus: EventBus,
    ) -> None:
        self._llm = llm
        self._concept_repo = concept_repo
        self._memory_repo = memory_repo
        self._event_bus = event_bus

    async def synthesize(self, payload: dict) -> List[Concept]:
        """Process a user-message event in the background."""
        content: str = payload.get("message", "")
        session_id = payload.get("session_id")
        context_concepts: List[str] = payload.get("active_concepts", [])

        if not content.strip():
            return []

        entities = await self._extract_entities(content)
        concepts: List[Concept] = []

        for entity in entities:
            concept = await self._concept_repo.get_or_create(
                label=entity.label,
                concept_type=entity.concept_type,
                properties={"description": entity.description},
            )
            concepts.append(concept)

            # Tie the new concept into the current context (temporal co-occurrence)
            for ctx_id in context_concepts:
                if ctx_id != concept.id:
                    await self._concept_repo.connect(
                        concept.id, ctx_id, ConnectionType.TEMPORAL
                    )

            # Persist a compact semantic memory
            await self._memory_repo.store(
                Memory(
                    content=f"Entity {entity.label} ({entity.concept_type}): {entity.description}",
                    memory_type=MemoryType.SEMANTIC,
                    concepts=[concept.id],
                    metadata={"source_session": session_id},
                )
            )

        # Background cross-referencing may reveal a "realization"
        await self._cross_reference(concepts, session_id)

        return concepts

    async def _extract_entities(self, content: str) -> List[ExtractedEntity]:
        """Ask the LLM to pull out salient entities from raw content."""
        try:
            result = await self._llm.extract_structured(
                content,
                schema=_ENTITY_SCHEMA,
                instructions=(
                    "Identify the most salient entities in this text. "
                    "Types include: person, project, technology, topic, emotion, skill, place. "
                    "Max 5 entities."
                ),
            )
        except Exception:
            return []
        return [
            ExtractedEntity(label=e["label"], concept_type=e.get("type", "topic"), description=e.get("description", ""))
            for e in result.get("entities", [])
        ]

    async def _cross_reference(self, concepts: List[Concept], session_id: Optional[str]) -> None:
        """Look for strong, non-obvious connections and inject insights."""
        for concept in concepts:
            for conn in await self._concept_repo.get_connections(concept.id, min_weight=0.7):
                related = await self._concept_repo.get(conn.target_id)
                if related is None:
                    continue
                confidence = conn.weight / 10.0
                if confidence >= self.CONTEXT_INJECTION_THRESHOLD:
                    await self._event_bus.publish(
                        Event(
                            topic=EventTopic.CONTEXT_INJECTION,
                            payload={
                                "session_id": session_id,
                                "insight": f"{concept.label} is strongly connected to {related.label}",
                                "concepts": [concept.id, related.id],
                                "confidence": confidence,
                            },
                            priority=EventPriority.HIGH,
                        )
                    )


_ENTITY_SCHEMA = __import__("nexus.domain.value_objects.schema", fromlist=["JSONSchema"]).JSONSchema(
    type="object",
    properties={
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        }
    },
    required=["entities"],
)
