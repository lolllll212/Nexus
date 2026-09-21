"""
Memory persistence ports.

The application layer calls these interfaces to store/retrieve memory.
Concrete implementations (Neo4j, Qdrant, Redis) live in infrastructure/adapters.

Tenancy: every mutating/querying method accepts a `tenant_id` so each
tenant's memories and concepts are isolated at the storage boundary. The
default tenant ("default") keeps single-tenant deployments backward compatible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.memory import Memory
from nexus.domain.value_objects.synapse import ConnectionType


class MemoryRepository(ABC):
    """Persistent storage of memories (episodic + semantic)."""

    @abstractmethod
    async def store(self, memory: Memory, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        limit: int = 10,
        memory_types: Optional[list] = None,
        tenant_id: str = "default",
    ) -> List[Memory]: ...

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> Optional[Memory]: ...

    @abstractmethod
    async def find_stale(
        self,
        threshold_days: int,
        limit: int = 100,
        min_accesses: int = 1,
        tenant_id: str = "default",
    ) -> List[Memory]: ...

    @abstractmethod
    async def delete(self, memory_id: str, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def delete_many(self, memory_ids: List[str], tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def record_access(self, memory_id: str, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def find_by_emotional_weight(
        self, min_intensity: float, limit: int = 100, tenant_id: str = "default"
    ) -> List[Memory]: ...


class ConceptRepository(ABC):
    """Synaptic graph storage of concepts and their connections."""

    @abstractmethod
    async def upsert(self, concept: Concept, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def get(self, concept_id: str, tenant_id: str = "default") -> Optional[Concept]: ...

    @abstractmethod
    async def find_by_label(
        self, label: str, limit: int = 10, tenant_id: str = "default"
    ) -> List[Concept]: ...

    @abstractmethod
    async def upsert_connection(self, connection: SynapticConnection, tenant_id: str = "default") -> None: ...

    @abstractmethod
    async def get_connections(
        self, concept_id: str, min_weight: float = 0.0, tenant_id: str = "default"
    ) -> List[SynapticConnection]: ...

    @abstractmethod
    async def get_or_create(
        self,
        label: str,
        concept_type: str,
        properties: Optional[Dict] = None,
        tenant_id: str = "default",
    ) -> Concept: ...

    @abstractmethod
    async def connect(
        self,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.SEMANTIC,
        tenant_id: str = "default",
    ) -> SynapticConnection: ...

    @abstractmethod
    async def find_weakest(
        self, limit: int = 100, tenant_id: str = "default"
    ) -> List[SynapticConnection]: ...

    @abstractmethod
    async def delete_connection(self, connection_id: str, tenant_id: str = "default") -> None: ...


class ShortTermMemory(ABC):
    """Ephemeral working memory (e.g., Redis) for the conscious loop."""

    @abstractmethod
    async def set(self, key: str, value: Dict, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> Optional[Dict]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def publish(self, channel: str, payload: Dict) -> None: ...
