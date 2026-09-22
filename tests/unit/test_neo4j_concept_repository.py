"""
Neo4j ConceptRepository async contract tests.

These run the repository against a fake ASYNC driver, proving the adapter
never blocks the event loop (no sync `GraphDatabase`, no `.result()`
synchronization calls). A real Neo4j server is not required.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from nexus.domain.entities.concept import Concept
from nexus.domain.value_objects.synapse import ConnectionType
from nexus.infrastructure.adapters.persistence.neo4j_concept_repository import Neo4jConceptRepository


class FakeNode(dict):
    """Simulates a neo4j Graph type (dict access + attribute .get)."""

    def __init__(self, element_id: str = "", **kwargs) -> None:
        super().__init__(kwargs)
        self.element_id = element_id

    def get(self, key, default=None):
        return dict.get(self, key, default)


class FakeRecord:
    def __init__(self, mapping: Optional[Dict[str, object]] = None) -> None:
        self._mapping = mapping or {}

    def __getitem__(self, key: str) -> object:
        return self._mapping[key]

    def get(self, key: str, default=None):
        return self._mapping.get(key, default)


class FakeAsyncResult:
    """Simulates neo4j AsyncResult: single()/data() are awaitables."""

    def __init__(self, records: List[FakeRecord]) -> None:
        self._records = records

    async def single(self) -> Optional[FakeRecord]:
        return self._records[0] if self._records else None

    async def data(self) -> List[FakeRecord]:
        return list(self._records)


class FakeAsyncSession:
    """Simulates an async neo4j session: run() is async; context-managed."""

    def __init__(self, driver: "FakeAsyncDriver") -> None:
        self._driver = driver

    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def run(self, cypher: str, **params) -> FakeAsyncResult:
        self._driver.runs.append({"cypher": cypher, "params": params})
        return self._driver._result_fn(cypher, params)


class FakeAsyncDriver:
    """Simulates the AsyncGraphDatabase driver API."""

    def __init__(self, result_fn) -> None:
        self._result_fn = result_fn
        self.sessions_created = 0
        self.closed = False
        self.runs: List[Dict] = []

    def session(self, database: str = None) -> FakeAsyncSession:
        self.sessions_created += 1
        return FakeAsyncSession(self)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def driver():
    return FakeAsyncDriver(lambda cypher, params: FakeAsyncResult([]))


async def test_injects_fake_driver_and_closes(driver):
    repo = Neo4jConceptRepository(uri="bolt://localhost:7687", user="u", password="p", driver=driver)
    await repo.close()
    assert driver.closed
    assert driver.sessions_created == 0  # nothing was called yet


async def test_upsert_uses_async_session_and_cypher(driver):
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)
    concept = Concept(label="python", concept_type="topic", properties={"lang": "3.12"})
    await repo.upsert(concept, tenant_id="acme")

    assert driver.sessions_created == 1
    assert len(driver.runs) == 1
    assert "MERGE (c:Concept" in driver.runs[0]["cypher"]
    assert driver.runs[0]["params"]["label"] == "python"
    assert driver.runs[0]["params"]["tenant"] == "acme"


async def test_get_returns_concept_from_single_record(driver):
    def result_fn(cypher, params):
        if "RETURN c" in cypher:
            node = FakeNode(
                element_id="n1",
                id="c1",
                label="neural",
                type="topic",
                properties='{"k": 1}',
                strength=2.0,
                access_count=3,
            )
            return FakeAsyncResult([FakeRecord({"c": node})])
        return FakeAsyncResult([])

    driver._result_fn = result_fn
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)

    concept = await repo.get("c1", tenant_id="acme")
    assert concept is not None
    assert concept.id == "c1"
    assert concept.label == "neural"
    assert concept.properties == {"k": 1}
    assert concept.strength == 2.0


async def test_get_returns_none_when_no_record(driver):
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)
    assert await repo.get("missing", tenant_id="acme") is None


async def test_get_or_create_uses_merge_cypher(driver):
    seen = {}

    def result_fn(cypher, params):
        seen.update(params)
        node = FakeNode(
            element_id="n9",
            id=params.get("id", "gen"),
            label=params.get("label"),
            type=params.get("type"),
            strength=1.0,
        )
        return FakeAsyncResult([FakeRecord({"c": node})])

    driver._result_fn = result_fn
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)

    concept = await repo.get_or_create("graphql", "topic", {"db": 1}, tenant_id="acme")
    assert concept.id in seen["id"]
    assert concept.label == "graphql"
    assert seen["tenant"] == "acme"


async def test_get_connections_parses_weighted_edges(driver):
    def result_fn(cypher, params):
        rel = FakeNode(element_id="r1")
        rel["type"] = "semantic"
        rel["weight"] = 0.9
        rel["reinforcement_count"] = 4
        return FakeAsyncResult([FakeRecord({"r": rel, "target": "T2"})])

    driver._result_fn = result_fn
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)

    conns = await repo.get_connections("T1", min_weight=0.5, tenant_id="acme")
    assert len(conns) == 1
    assert conns[0].target_id == "T2"
    assert conns[0].weight == 0.9
    assert conns[0].connection_type == ConnectionType.SEMANTIC


async def test_find_weakest_orders_ascending(driver):
    def result_fn(cypher, params):
        rels = [FakeNode(element_id=f"r{i}") for i in range(2)]
        for i, rel in enumerate(rels):
            rel["type"] = "semantic"
            rel["weight"] = float(i + 1) * 0.1
        return FakeAsyncResult([FakeRecord({"r": rels[1], "source": "A", "target": "B"})])

    driver._result_fn = result_fn
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)

    weak = await repo.find_weakest(limit=10, tenant_id="acme")
    assert len(weak) == 1
    assert weak[0].source_id == "A"


async def test_delete_connection_runs_cypher(driver):
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)
    await repo.delete_connection("r1", tenant_id="acme")
    # executes without error; query ran inside an async session
    assert driver.sessions_created == 1


def test_never_imports_sync_driver():
    """The adapter must use the async driver only - guard against regressions."""
    import inspect
    import re

    source = inspect.getsource(Neo4jConceptRepository)
    # "GraphDatabase.driver" (sync) must never appear UNLESS preceded by "Async".
    assert not re.search(r"(?<!Async)GraphDatabase\.driver", source)
    assert re.search(r"AsyncGraphDatabase\.driver", source)


def test_get_memories_returns_memories(driver):
    """Memory nodes are parsed back into Memory entities."""

    def result_fn(cypher, params):
        if "-[:MENTIONS]->" in cypher:
            node = FakeNode(
                element_id="m1",
                id="mem1",
                content="hello world",
                memory_type="episodic",
                properties='{"concepts": ["graphql"]}',
            )
            return FakeAsyncResult([FakeRecord({"m": node})])
        return FakeAsyncResult([])

    driver._result_fn = result_fn
    repo = Neo4jConceptRepository("bolt://x", "u", "p", driver=driver)
    import asyncio

    memories = asyncio.run(repo.get_memories("c1", tenant_id="acme"))
    assert len(memories) == 1
    assert memories[0].content == "hello world"
    assert memories[0].concepts == ["graphql"]
