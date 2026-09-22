"""In-memory MemoryRepository - the vector store of the brain, in process.

Exposes the same port as QdrantMemoryRepository but keeps everything in a
dict. Recall is a flat match over content/concepts, which is enough for
offline dreaming, evals, and local demos.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.memory_repository import MemoryRepository


class InMemoryMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self.memories: Dict[str, Memory] = {}
        self._tenant: Dict[str, str] = {}

    async def ensure_collection(self, tenant_id: str = "default") -> None:
        return None

    async def close(self) -> None:
        return None

    async def store(self, memory: Memory, tenant_id: str = "default") -> None:
        self.memories[memory.id] = memory
        self._tenant[memory.id] = tenant_id

    async def retrieve(
        self, query: str, limit: int = 10, memory_types: Optional[list] = None, tenant_id: str = "default"
    ) -> List[Memory]:
        results = [m for m in self.memories.values() if self._tenant.get(m.id) == tenant_id]
        if memory_types:
            results = [m for m in results if m.memory_type in memory_types]
        if query:
            q = query.lower()
            scored = sorted(
                results,
                key=lambda m: _score(m, q),
                reverse=True,
            )
            return [m for m in scored if _score(m, q) > 0][:limit]
        return list(reversed(results))[:limit]

    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        return self.memories.get(memory_id)

    async def find_stale(
        self, threshold_days: int, limit: int = 100, min_accesses: int = 1, tenant_id: str = "default"
    ) -> List[Memory]:
        cutoff = _utcnow() - datetime.timedelta(days=threshold_days)
        stale = [
            m
            for m in self.memories.values()
            if self._tenant.get(m.id) == tenant_id
            and m.last_accessed_at < cutoff
            and m.access_count < min_accesses
        ]
        return stale[:limit]

    async def delete(self, memory_id: str, tenant_id: str = "default") -> None:
        self.memories.pop(memory_id, None)
        self._tenant.pop(memory_id, None)

    async def delete_many(self, memory_ids: List[str], tenant_id: str = "default") -> None:
        for memory_id in memory_ids:
            self.memories.pop(memory_id, None)
            self._tenant.pop(memory_id, None)

    async def record_access(self, memory_id: str, tenant_id: str = "default") -> None:
        if memory_id in self.memories:
            self.memories[memory_id].accessed()

    async def find_by_emotional_weight(
        self, min_intensity: float, limit: int = 100, tenant_id: str = "default"
    ) -> List[Memory]:
        charged = [
            m
            for m in self.memories.values()
            if self._tenant.get(m.id) == tenant_id
            and m.emotional_weight
            and m.emotional_weight.intensity >= min_intensity
        ]
        charged.sort(key=lambda m: m.emotional_weight.intensity, reverse=True)
        return charged[:limit]


def _score(memory: Memory, query: str) -> float:
    """Cheap lexical overlap score over content + concepts + type."""
    haystack = [memory.content.lower(), memory.memory_type.value.lower()]
    haystack.extend(c.lower() for c in memory.concepts)
    text = " ".join(haystack)
    terms = [t for t in query.split() if t]
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in text) / len(terms)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)