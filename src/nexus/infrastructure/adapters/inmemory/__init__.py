"""
In-memory adapters - production-grade, zero-dependency persistentization.

Used when `NEXUS_INFRA_BACKEND=memory` (or eval harness runs). These let the
whole brain run with no Redis/Qdrant/Neo4j/OpenAI — the dream loop, evals,
and local demos all work against process-local state.
"""

from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository
from nexus.infrastructure.adapters.inmemory.embedder import InMemoryEmbedder
from nexus.infrastructure.adapters.inmemory.memory_repository import InMemoryMemoryRepository
from nexus.infrastructure.adapters.inmemory.short_term_memory import InMemoryShortTermMemory

__all__ = [
    "InMemoryMemoryRepository",
    "InMemoryConceptRepository",
    "InMemoryShortTermMemory",
    "InMemoryEmbedder",
]
