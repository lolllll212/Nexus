"""
Neo4j ConceptRepository adapter - the synaptic graph memory.

Each Concept is a node; each SynapticConnection is a labeled, weighted edge.
Cypher queries implement Hebbian strengthening and decay at the database level.
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

    async def upsert(self, concept: Concept) -> None:
        cypher = """
        MERGE (c:Concept {id: $id})
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
                label=concept.label,
                type=concept.concept_type,
                props=json.dumps(concept.properties),
                strength=concept.strength,
                access_count=concept.access_count,
            )

    async def get(self, concept_id: str) -> Optional[Concept]:
        cypher = "MATCH (c:Concept {id: $id}) RETURN c"
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, id=concept_id)
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

    async def find_by_label(self, label: str, limit: int = 10) -> List[Concept]:
        cypher = """
        MATCH (c:Concept)
        WHERE c.label CONTAINS $label
        RETURN c ORDER BY c.strength DESC LIMIT $limit
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, label=label, limit=limit)
            records = await result.data()
        concepts = []
        for r in records:
            node = r["c"]
            concepts.append(Concept(id=node["id"], label=node["label"], concept_type=node.get("type", "topic")))
        return concepts

    async def upsert_connection(self, connection: SynapticConnection) -> None:
        cypher = """
        MATCH (a:Concept {id: $source}), (b:Concept {id: $target})
        MERGE (a)-[r:CONNECTS {type: $type}]->(b)
        SET r.weight = $weight,
            r.reinforcement_count = $reinforcement_count,
            r.last_reinforced_at = datetime()
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(
                cypher,
                source=connection.source_id,
                target=connection.target_id,
                type=connection.connection_type.value,
                weight=connection.weight,
                reinforcement_count=connection.reinforcement_count,
            )

    async def get_connections(self, concept_id: str, min_weight: float = 0.0) -> List[SynapticConnection]:
        cypher = """
        MATCH (a:Concept {id: $id})-[r:CONNECTS]->(b:Concept)
        WHERE r.weight >= $min_weight
        RETURN r, b.id AS target ORDER BY r.weight DESC
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, id=concept_id, min_weight=min_weight)
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

    async def get_or_create(self, label: str, concept_type: str, properties: Optional[Dict] = None) -> Concept:
        cypher = """
        MERGE (c:Concept {label: $label, type: $type})
        ON CREATE SET c.id = $id, c.strength = $strength, c.properties = $props
        ON MATCH SET c.strength = c.strength + $boost
        RETURN c
        """
        concept_id = __import__("uuid").uuid4().__str__()
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                cypher,
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

    async def connect(self, source_id: str, target_id: str, connection_type: ConnectionType = ConnectionType.SEMANTIC) -> SynapticConnection:
        conn = SynapticConnection(source_id=source_id, target_id=target_id, connection_type=connection_type, weight=self._synapse.initial_weight)
        await self.upsert_connection(conn)
        return conn

    async def find_weakest(self, limit: int = 100) -> List[SynapticConnection]:
        cypher = """
        MATCH (a:Concept)-[r:CONNECTS]->(b:Concept)
        ORDER BY r.weight ASC LIMIT $limit
        RETURN r, a.id AS source, b.id AS target
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, limit=limit)
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

    async def delete_connection(self, connection_id: str) -> None:
        cypher = "MATCH ()-[r:CONNECTS] WHERE elementId(r) = $id DELETE r"
        async with self._driver.session(database=self._database) as session:
            await session.run(cypher, id=connection_id)
