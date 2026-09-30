"""Neo4j backup - graph export via Cypher.

Production Neo4j uses `neo4j-admin database dump` on the volume (requires
offline DB or `neo4j-admin database backup` for online). For the app layer we
provide a portable Cypher export that works without shell access and is enough
to verify DR in tests/offline mode.

The dump is a JSONL file: one JSON object per node/relationship, with
`_kind: node|rel` discriminator. Restore replays it via MERGE.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any


@dataclass
class Neo4jDumpInfo:
    path: str
    nodes: int
    relationships: int


class Neo4jBackup:
    """Export/import the concept graph via Cypher. Inject driver for tests."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        driver: Any | None = None,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = driver

    def _get_driver(self):  # type: ignore[no-untyped-def]
        if self._driver is not None:
            return self._driver
        from neo4j import AsyncGraphDatabase

        return AsyncGraphDatabase.driver(self._uri, auth=(self._user, self._password))

    async def export(self, dest: str | pathlib.Path, tenant_id: str = "default") -> Neo4jDumpInfo:
        path = pathlib.Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        driver = self._get_driver()
        close = self._driver is None
        nodes = 0
        rels = 0
        try:
            # Export nodes
            async with driver.session(database="neo4j") as session:
                result = await session.run(
                    "MATCH (c:Concept {tenant: $tenant}) RETURN c",
                    tenant=tenant_id,
                )
                records = await result.data()
                with open(path, "w", encoding="utf-8") as f:
                    for r in records:
                        node = r["c"]
                        # neo4j driver returns Node, convert via dict access
                        payload = {
                            "_kind": "node",
                            "id": node.get("id") if isinstance(node, dict) else node["id"],
                            "label": node.get("label") if isinstance(node, dict) else node["label"],
                            "type": node.get("type") if isinstance(node, dict) else node.get("type"),
                        }
                        f.write(json.dumps(payload) + "\n")
                        nodes += 1
                    # Export relationships
                    result2 = await session.run(
                        "MATCH (a:Concept {tenant:$tenant})-[r:CONNECTS {tenant:$tenant}]->(b:Concept {tenant:$tenant}) RETURN r, a.id AS src, b.id AS dst",
                        tenant=tenant_id,
                    )
                    records2 = await result2.data()
                    for r in records2:
                        rel = r["r"]
                        payload = {
                            "_kind": "rel",
                            "src": r["src"],
                            "dst": r["dst"],
                            "type": rel.get("type") if isinstance(rel, dict) else rel["type"],
                            "weight": rel.get("weight") if isinstance(rel, dict) else rel.get("weight", 1.0),
                        }
                        f.write(json.dumps(payload) + "\n")
                        rels += 1
        finally:
            if close:
                await driver.close()
        return Neo4jDumpInfo(path=str(path), nodes=nodes, relationships=rels)

    async def import_dump(self, src: str | pathlib.Path, tenant_id: str = "default") -> Neo4jDumpInfo:
        path = pathlib.Path(src)
        if not path.exists():
            raise FileNotFoundError(str(path))
        driver = self._get_driver()
        close = self._driver is None
        nodes = 0
        rels = 0
        try:
            async with driver.session(database="neo4j") as session:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        obj = json.loads(line)
                        if obj.get("_kind") == "node":
                            await session.run(
                                "MERGE (c:Concept {id:$id, tenant:$tenant}) SET c.label=$label, c.type=$type",
                                id=obj["id"],
                                tenant=tenant_id,
                                label=obj.get("label", ""),
                                type=obj.get("type", "topic"),
                            )
                            nodes += 1
                        elif obj.get("_kind") == "rel":
                            await session.run(
                                "MATCH (a:Concept {id:$src, tenant:$tenant}), (b:Concept {id:$dst, tenant:$tenant}) "
                                "MERGE (a)-[r:CONNECTS {tenant:$tenant}]->(b) SET r.weight=$w, r.type=$type",
                                src=obj["src"],
                                dst=obj["dst"],
                                tenant=tenant_id,
                                w=obj.get("weight", 1.0),
                                type=obj.get("type", "semantic"),
                            )
                            rels += 1
        finally:
            if close:
                await driver.close()
        return Neo4jDumpInfo(path=str(path), nodes=nodes, relationships=rels)
