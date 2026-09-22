"""In-memory ConceptRepository - the synaptic graph, in process.

Mirrors the fakes used in tests but ships in production so the dream loop
and eval harness can run with zero external infrastructure. Connections are
scoped per tenant and decays/strengthening happen in place.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.memory_repository import ConceptRepository
from nexus.domain.value_objects.synapse import ConnectionType, SynapseConfig


class InMemoryConceptRepository(ConceptRepository):
    def __init__(self, synapse: SynapseConfig | None = None) -> None:
        self.concepts: Dict[str, Concept] = {}
        self.connections: Dict[str, List[SynapticConnection]] = {}
        self._tenant_concepts: Dict[str, str] = {}
        self._tenant_connections: Dict[str, str] = {}
        self._synapse = synapse or SynapseConfig()

    async def ensure_collection(self, tenant_id: str = "default") -> None:
        return None

    async def close(self) -> None:
        return None

    async def upsert(self, concept: Concept, tenant_id: str = "default") -> None:
        self.concepts[concept.id] = concept
        self._tenant_concepts[concept.id] = tenant_id

    async def get(self, concept_id: str, tenant_id: str = "default") -> Optional[Concept]:
        concept = self.concepts.get(concept_id)
        if concept is None or self._tenant_concepts.get(concept_id) != tenant_id:
            return None
        return concept

    async def get_memories(self, concept_id: str, tenant_id: str = "default") -> List[Memory]:
        concept = self.concepts.get(concept_id)
        if concept is None:
            return []
        return [
            Memory(id=concept.id, content=concept.label, memory_type=MemoryType.SEMANTIC, concepts=[concept.label])
        ]

    async def find_by_label(self, label: str, limit: int = 10, tenant_id: str = "default") -> List[Concept]:
        return [
            c
            for cid, c in self.concepts.items()
            if self._tenant_concepts.get(cid) == tenant_id and label.lower() in c.label.lower()
        ][:limit]

    async def upsert_connection(self, connection: SynapticConnection, tenant_id: str = "default") -> None:
        existing = [
            c
            for c in self.connections.get(connection.source_id, [])
            if c.id == connection.id and self._tenant_connections.get(c.id) == tenant_id
        ]
        if existing:
            self.connections[connection.source_id] = [
                connection if c.id == connection.id else c for c in self.connections[connection.source_id]
            ]
        else:
            self.connections.setdefault(connection.source_id, []).append(connection)
        self._tenant_connections[connection.id] = tenant_id

    async def get_connections(
        self, concept_id: str, min_weight: float = 0.0, tenant_id: str = "default"
    ) -> List[SynapticConnection]:
        return [
            c
            for c in self.connections.get(concept_id, [])
            if c.weight >= min_weight and self._tenant_connections.get(c.id) == tenant_id
        ]

    async def get_or_create(
        self, label: str, concept_type: str, properties: Optional[Dict] = None, tenant_id: str = "default"
    ) -> Concept:
        existing = [
            c
            for cid, c in self.concepts.items()
            if self._tenant_concepts.get(cid) == tenant_id and c.label == label
        ]
        if existing:
            existing[0].strengthen()
            return existing[0]
        c = Concept(label=label, concept_type=concept_type, properties=properties or {})
        self.concepts[c.id] = c
        self._tenant_concepts[c.id] = tenant_id
        return c

    async def connect(
        self,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.SEMANTIC,
        tenant_id: str = "default",
    ) -> SynapticConnection:
        conn = SynapticConnection(source_id=source_id, target_id=target_id, connection_type=connection_type)
        await self.upsert_connection(conn, tenant_id=tenant_id)
        return conn

    async def find_weakest(self, limit: int = 100, tenant_id: str = "default") -> List[SynapticConnection]:
        all_conns = [
            c
            for conns in self.connections.values()
            for c in conns
            if self._tenant_connections.get(c.id) == tenant_id
        ]
        return sorted(all_conns, key=lambda c: c.weight)[:limit]

    async def delete_connection(self, connection_id: str, tenant_id: str = "default") -> None:
        for key in self.connections:
            self.connections[key] = [c for c in self.connections[key] if c.id != connection_id]
        self._tenant_connections.pop(connection_id, None)

    async def decay_connections(self, decay_rate: float = 0.05, tenant_id: str = "default") -> None:
        for conns in self.connections.values():
            for c in conns:
                if self._tenant_connections.get(c.id) == tenant_id:
                    c.decay(decay_rate)