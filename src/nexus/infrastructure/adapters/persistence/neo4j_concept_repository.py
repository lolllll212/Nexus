"""
Neo4j ConceptRepository adapter - the synaptic graph memory.

Each Concept is a node; each SynapticConnection is a labeled, weighted edge.
Cypher queries implement Hebbian strengthening and decay at the database level.

Tenancy: every node carries a `tenant` property; all reads/writes scope to the
requesting tenant. A Neo4j database can also be allocated per tenant via the
`database` constructor argument (defense in depth).
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.ports.memory_repository import ConceptRepository
from nexus.domain.value_objects.synapse import ConnectionType, SynapseConfig


class Neo4jConceptRepository(ConceptRepository):
    """ConceptRepository backed by Neo4j."""

    def __init__(self, uri: str, user: str, password: str, database: str = "nexus", synapse: SynapseConfig | None = None) -> None:
        from neo4j import AsyncGraphDatabase

        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._synapse = synapse or SynapseConfig()

    async def close(self) -> None:
        await self._driver.close()

    async def upsert(self, concept: Concept, tenant_id: str = "default") -> None:
        cypher = """
        MERGE (c:Concept {id: $id, tenant: $tenant})
        SET c.label = $label,
            c.type = $type,
            c.properties = $props,
            c.strength = $strength,
            c.access_count = $access_count,
            c.last_accessed_at = datetime()
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(
                cypher,
                id=concept.id,
                tenant=tenant_id,
                label=concept.label,
                type=concept.concept_type,
                props=json.dumps(concept.properties),
                strength=concept.strength,
                access_count=concept.access_count,
            )

    async def get(self, concept_id: str, tenant_id: str = "default") -> Optional[Concept]:
        cypher = "MATCH (c:Concept {id: $id, tenant: $tenant}) RETURN c"
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, id=concept_id, tenant=tenant_id)
            record = await result.single()
        if record is None:
            return None
        node = record["c"]
        props = json.loads(node.get("properties", "{}"))
        return Concept(
            id=node["id"],
            label=node["label"],
            concept_type=node.get("type", "topic"),
            properties=props,
            strength=node.get("strength", 1.0),
            access_count=node.get("access_count", 0),
        )

    async def find_by_label(self, label: str, limit: int = 10, tenant_id: str = "default") -> List[Concept]:
        cypher = """
        MATCH (c:Concept)
        WHERE c.tenant = $tenant AND c.label CONTAINS $label
        RETURN c ORDER BY c.strength DESC LIMIT $limit
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, tenant=tenant_id, label=label, limit=limit)
            records = await result.data()
        concepts = []
        for r in records:
            node = r["c"]
            concepts.append(Concept(id=node["id"], label=node["label"], concept_type=node.get("type", "topic")))
        return concepts

    async def upsert_connection(self, connection: SynapticConnection, tenant_id: str = "default") -> None:
        cypher = """
        MATCH (a:Concept {id: $source, tenant: $tenant}), (b:Concept {id: $target, tenant: $tenant})
        MERGE (a)-[r:CONNECTS {type: $type, tenant: $tenant}]->(b)
        SET r.weight = $weight,
            r.reinforcement_count = $reinforcement_count,
            r.last_reinforced_at = datetime()
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(
                cypher,
                tenant=tenant_id,
                source=connection.source_id,
                target=connection.target_id,
                type=connection.connection_type.value,
                weight=connection.weight,
                reinforcement_count=connection.reinforcement_count,
            )

    async def get_connections(
        self, concept_id: str, min_weight: float = 0.0, tenant_id: str = "default"
    ) -> List[SynapticConnection]:
        cypher = """
        MATCH (a:Concept {id: $id, tenant: $tenant})-[r:CONNECTS]->(b:Concept {tenant: $tenant})
        WHERE r.weight >= $min_weight
        RETURN r, b.id AS target ORDER BY r.weight DESC
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, id=concept_id, tenant=tenant_id, min_weight=min_weight)
            records = await result.data()
        return [
            SynapticConnection(
                id=str(r["r"].element_id),
                source_id=concept_id,
                target_id=r["target"],
                connection_type=ConnectionType(r["r"]["type"]),
                weight=r["r"]["weight"],
                reinforcement_count=r["r"].get("reinforcement_count", 0),
            )
            for r in records
        ]

    async def get_or_create(
        self, label: str, concept_type: str, properties: Optional[Dict] = None, tenant_id: str = "default"
    ) -> Concept:
        cypher = """
        MERGE (c:Concept {label: $label, type: $type, tenant: $tenant})
        ON CREATE SET c.id = $id, c.strength = $strength, c.properties = $props
        ON MATCH SET c.strength = c.strength + $boost
        RETURN c
        """
        concept_id = __import__("uuid").uuid4().__str__()
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                cypher,
                tenant=tenant_id,
                label=label,
                type=concept_type,
                id=concept_id,
                strength=self._synapse.initial_weight,
                props=json.dumps(properties or {}),
                boost=self._synapse.hebbian_learning_rate,
            )
            record = await result.single()
        node = record["c"]
        return Concept(
            id=node["id"],
            label=node["label"],
            concept_type=node.get("type", concept_type),
            strength=node.get("strength", self._synapse.initial_weight),
            access_count=node.get("access_count", 0),
        )

    async def connect(
        self,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.SEMANTIC,
        tenant_id: str = "default",
    ) -> SynapticConnection:
        conn = SynapticConnection(source_id=source_id, target_id=target_id, connection_type=connection_type, weight=self._synapse.initial_weight)
        await self.upsert_connection(conn, tenant_id=tenant_id)
        return conn

    async def find_weakest(self, limit: int = 100, tenant_id: str = "default") -> List[SynapticConnection]:
        cypher = """
        MATCH (a:Concept)-[r:CONNECTS]->(b:Concept)
        WHERE a.tenant = $tenant AND b.tenant = $tenant
        ORDER BY r.weight ASC LIMIT $limit
        RETURN r, a.id AS source, b.id AS target
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, tenant=tenant_id, limit=limit)
            records = await result.data()
        return [
            SynapticConnection(
                id=str(r["r"].element_id),
                source_id=r["source"],
                target_id=r["target"],
                connection_type=ConnectionType(r["r"]["type"]),
                weight=r["r"]["weight"],
            )
            for r in records
        ]

    async def delete_connection(self, connection_id: str, tenant_id: str = "default") -> None:
        cypher = """
        MATCH (a:Concept {tenant: $tenant})-[r:CONNECTS {tenant: $tenant}]->(b:Concept {tenant: $tenant})
        WHERE elementId(r) = $id
        DELETE r
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(cypher, id=connection_id, tenant=tenant_id)
