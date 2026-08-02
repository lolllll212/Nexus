"""
Qdrant MemoryRepository adapter - vector space for semantic search.

Stores episodic + semantic memories with dense embeddings. Also provides
`find_stale` via payload filters on `last_accessed_at` for dreaming-phase pruning.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.llm_provider import EmbeddingProvider
from nexus.domain.ports.memory_repository import MemoryRepository


class QdrantMemoryRepository(MemoryRepository):
    """MemoryRepository backed by Qdrant."""

    COLLECTION = "nexus_memory"

    def __init__(
        self,
        host: str,
        port: int,
        embedder: EmbeddingProvider,
        shard_number: int = 1,
        replication_factor: int = 1,
    ) -> None:
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(host=host, port=port)
        self._embedder = embedder
        self._shard_number = shard_number
        self._replication_factor = replication_factor

    async def ensure_collection(self) -> None:
        from qdrant_client import models

        if await self._client.collection_exists(self.COLLECTION):
            return
        await self._client.create_collection(
            collection_name=self.COLLECTION,
            vectors_config=models.VectorParams(size=self._embedder.dimension, distance=models.Distance.COSINE),
            shard_number=self._shard_number,
            replication_factor=self._replication_factor,
        )

    async def store(self, memory: Memory) -> None:
        if memory.embedding is None:
            memory.embedding = await self._embedder.embed(memory.content)
        await self._client.upsert(
            collection_name=self.COLLECTION,
            points=[
                {
                    "id": memory.id,
                    "vector": memory.embedding,
                    "payload": self._to_payload(memory),
                }
            ],
        )

    async def retrieve(self, query: str, limit: int = 10, memory_types: Optional[list] = None) -> List[Memory]:
        query_vec = await self._embedder.embed(query)
        filter_ = None
        if memory_types:
            from qdrant_client import models

            filter_ = models.Filter(
                must=[models.FieldCondition(key="memory_type", match=models.MatchAny(any=[t.value for t in memory_types]))]
            )
        hits = await self._client.search(
            collection_name=self.COLLECTION, query_vector=query_vec, limit=limit, query_filter=filter_
        )
        return [self._from_payload(h.payload, point_id=h.id) for h in hits]

    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        points = await self._client.retrieve(collection_name=self.COLLECTION, ids=[memory_id])
        if not points:
            return None
        return self._from_payload(points[0].payload, point_id=points[0].id)

    async def find_stale(
        self, threshold_days: int, limit: int = 100, min_accesses: int = 1
    ) -> List[Memory]:
        from qdrant_client import models

        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=threshold_days)).isoformat()
        filter_ = models.Filter(
            must=[
                models.FieldCondition(key="last_accessed_at", range=models.Range(lt=cutoff)),
                models.FieldCondition(key="access_count", range=models.Range(lt=min_accesses)),
            ]
        )
        points = await self._client.scroll(
            collection_name=self.COLLECTION, limit=limit, filter_=filter_, with_payload=True
        )
        return [self._from_payload(p.payload, point_id=p.id) for p, _ in points]

    async def find_by_emotional_weight(self, min_intensity: float, limit: int = 100) -> List[Memory]:
        from qdrant_client import models

        filter_ = models.Filter(
            must=[
                models.FieldCondition(key="emotional_intensity", range=models.Range(gte=min_intensity)),
            ]
        )
        points = await self._client.scroll(
            collection_name=self.COLLECTION, limit=limit, filter_=filter_, with_payload=True
        )
        return [self._from_payload(p.payload, point_id=p.id) for p, _ in points]

    async def delete(self, memory_id: str) -> None:
        await self._client.delete(collection_name=self.COLLECTION, points_selector=[memory_id])

    async def delete_many(self, memory_ids: List[str]) -> None:
        if not memory_ids:
            return
        await self._client.delete(collection_name=self.COLLECTION, points_selector=memory_ids)

    async def record_access(self, memory_id: str) -> None:
        points = await self._client.retrieve(collection_name=self.COLLECTION, ids=[memory_id])
        if not points:
            return
        payload = points[0].payload
        payload["access_count"] = payload.get("access_count", 0) + 1
        payload["last_accessed_at"] = datetime.datetime.utcnow().isoformat()
        await self._client.set_payload(collection_name=self.COLLECTION, payload=payload, points=[memory_id])

    # ---------------- helpers ----------------

    def _to_payload(self, m: Memory) -> dict:
        return {
            "id": m.id,
            "content": m.content,
            "memory_type": m.memory_type.value,
            "concepts": m.concepts,
            "metadata": m.metadata,
            "emotional_weight": m.emotional_weight.__dict__ if m.emotional_weight else None,
            "emotional_intensity": m.emotional_weight.intensity if m.emotional_weight else 0.0,
            "context_state": m.context_state,
            "created_at": m.created_at.isoformat(),
            "last_accessed_at": m.last_accessed_at.isoformat(),
            "access_count": m.access_count,
            "consolidated": m.consolidated,
        }

    def _from_payload(self, p: dict, point_id: str | None = None) -> Memory:
        m = Memory(
            id=point_id or p.get("id", ""),
            content=p.get("content", ""),
            memory_type=MemoryType(p.get("memory_type", "episodic")),
            concepts=p.get("concepts", []),
            metadata=p.get("metadata", {}),
            context_state=p.get("context_state", {}),
            access_count=p.get("access_count", 0),
            consolidated=p.get("consolidated", False),
        )
        if p.get("created_at"):
            m.created_at = datetime.datetime.fromisoformat(p["created_at"])
        if p.get("last_accessed_at"):
            m.last_accessed_at = datetime.datetime.fromisoformat(p["last_accessed_at"])
        return m
