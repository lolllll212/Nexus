"""
DreamPhase 1: Compression - Episodic to Semantic consolidation.

Reads the day's raw episodic transcripts and uses the LLM to distill them
into compact semantic facts (abstract knowledge, user preferences, rules).
The raw episodes are flagged `consolidated` for cold storage.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import MemoryRepository
from nexus.domain.value_objects.schema import JSONSchema


@dataclass
class CompressionResult:
    episodes_processed: int
    semantic_fragments_created: int
    raw_transcripts_stored: int


_COMPRESSION_SCHEMA = JSONSchema(
    type="object",
    properties={
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "concept_labels": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number"},
                },
                "required": ["content"],
            },
        }
    },
    required=["facts"],
)


class CompressionUseCase:
    """Compress episodic memories into semantic knowledge."""

    def __init__(self, llm: LLMProvider, memory_repo: MemoryRepository) -> None:
        self._llm = llm
        self._memory_repo = memory_repo

    async def run(
        self, episodes: list[Memory], batch_size: int = 50, tenant_id: str = "default"
    ) -> CompressionResult:
        result = CompressionResult(0, 0, 0)
        result.episodes_processed = len(episodes)
        distilled: list[Memory] = []

        # Batch the episodes to keep each LLM call within token budget
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i : i + batch_size]
            transcript = "\n---\n".join(m.content for m in batch)
            try:
                structured = await self._llm.extract_structured(
                    transcript,
                    schema=_COMPRESSION_SCHEMA,
                    instructions=(
                        "Consolidate these conversation transcripts into durable, "
                        "abstract facts about the user, their projects, preferences, "
                        "and recurring problems. Omit trivia. Keep each fact concise."
                    ),
                )
            except Exception:
                # This batch's episodes must NOT be marked consolidated: their
                # content was never distilled, and flagging them done would lose
                # it on cold storage. Leave them for a later dream cycle.
                continue

            for fact in structured.get("facts", []):
                semantic = Memory(
                    content=fact["content"],
                    memory_type=MemoryType.SEMANTIC,
                    concepts=[],
                    metadata={"importance": fact.get("importance", 0.5), "origin": "dream_compression"},
                )
                await self._memory_repo.store(semantic, tenant_id=tenant_id)
                result.semantic_fragments_created += 1

            distilled.extend(batch)

        # Flag only the episodes that actually distilled (cold storage decision is
        # an adapter concern). Episodes from failed batches stay un-flagged so the
        # next dream cycle retries them.
        for episode in distilled:
            episode.consolidated = True
        result.raw_transcripts_stored = len(distilled)
        return result
