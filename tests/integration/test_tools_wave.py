"""Integration tests for the CEO tool wave (plan-26f9918419c9)."""

from __future__ import annotations

import pytest

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.value_objects.synapse import ConnectionType
from nexus.infrastructure.adapters.execution.builtin_tools import default_builtin_tools
from nexus.infrastructure.adapters.execution.extended_tools import (
    EXTENDED_HANDLERS,
    _code_search_semantic,
    _csv_query,
    _dependency_audit,
    _memory_graph_query,
    _pytest_runner,
    _regex_extract,
    set_concept_repository,
    set_embedder,
)
from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository
from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox


def test_tool_wave_registry_contains_pytest_runner():
    tools = default_builtin_tools()
    tool_map = {t.name: t for t in tools}
    assert "pytest_runner" in tool_map
    assert "pytest_runner" in EXTENDED_HANDLERS
    assert "regex_extract" in tool_map
    assert "regex_extract" in EXTENDED_HANDLERS
    t = tool_map["pytest_runner"]
    assert "target" in t.input_schema.properties
    assert "failures" in t.output_schema.properties


@pytest.mark.asyncio
async def test_pytest_runner_on_passing_target():
    res = await _pytest_runner({"target": "tests/unit/test_tool_registry.py", "options": "-q"})
    assert res["returncode"] == 0
    assert res["passed"] >= 1
    assert res["failed"] == 0
    assert res["total_failed"] == 0
    assert len(res["failures"]) == 0
    assert "passed" in res["summary"]


@pytest.mark.asyncio
async def test_pytest_runner_structured_failure_in_sandbox(monkeypatch):
    monkeypatch.setattr(
        "nexus.infrastructure.adapters.execution.extended_tools.get_default_sandbox",
        lambda: SubprocessSandbox(),
    )
    failing_project = {
        "test_sample.py": "def test_fail():\n    assert 1 == 2\n",
    }
    res = await _pytest_runner(
        {
            "target": "test_sample.py",
            "options": "-q --tb=short",
            "files": failing_project,
        }
    )
    assert res["failed"] == 1 or res["total_failed"] == 1
    assert len(res["failures"]) >= 1
    f = res["failures"][0]
    assert "test_sample.py" in f["file"]
    assert "test_fail" in f["name"]
    assert "assert 1 == 2" in f["error"] or "AssertionError" in f["error"]


@pytest.mark.asyncio
async def test_csv_query_filtering_and_projection():
    csv_text = "name,age,department\nAlice,30,Engineering\nBob,25,QA\nCharlie,35,Engineering\n"
    res = await _csv_query({"data": csv_text, "query": "[?department == 'Engineering'].name"})
    assert res["result"] == ["Alice", "Charlie"]
    assert res["columns"] == ["name", "age", "department"]


@pytest.mark.asyncio
async def test_csv_query_numerical_comparison():
    csv_text = "item,price\nwidget,10\ngadget,25\nsprocket,5\n"
    res = await _csv_query({"data": csv_text, "query": "[?price > `10`].item"})
    assert res["result"] == ["gadget"]


@pytest.mark.asyncio
async def test_memory_graph_query_expansion():
    repo = InMemoryConceptRepository()
    c1 = Concept(id="c1", label="FastAPI", concept_type="technology")
    c2 = Concept(id="c2", label="Python", concept_type="language")
    await repo.upsert(c1)
    await repo.upsert(c2)
    conn = SynapticConnection(
        source_id="c1",
        target_id="c2",
        connection_type=ConnectionType.SEMANTIC,
        weight=0.95,
    )
    await repo.upsert_connection(conn)
    set_concept_repository(repo)

    res = await _memory_graph_query({"label": "FastAPI", "depth": 1})
    assert res["concept"]["label"] == "FastAPI"
    assert len(res["neighbors"]) == 1
    assert res["neighbors"][0]["label"] == "Python"
    assert len(res["connections"]) == 1
    assert res["connections"][0]["weight"] == 0.95


@pytest.mark.asyncio
async def test_code_search_semantic_tfidf_fallback():
    set_embedder(None)
    res = await _code_search_semantic(
        {
            "query": "BuiltinToolRegistry",
            "path": "src/nexus/infrastructure/adapters/execution",
            "k": 3,
        }
    )
    assert res["total_matches"] >= 1
    top = res["results"][0]
    assert "builtin_tools.py" in top["file"]
    assert top["score"] > 0


@pytest.mark.asyncio
async def test_code_search_semantic_with_hybrid_embedder():
    class DummyEmbedder:
        def embed_text(self, text: str) -> list[float]:
            # Simple deterministic projection
            val = float(len(text) % 10)
            return [val, 1.0 - val]

    set_embedder(DummyEmbedder())
    res = await _code_search_semantic(
        {
            "query": "BuiltinToolRegistry",
            "path": "src/nexus/infrastructure/adapters/execution",
            "k": 3,
            "alpha": 0.5,
        }
    )
    assert res["total_matches"] >= 1
    top = res["results"][0]
    assert top["score"] > 0
    set_embedder(None)


@pytest.mark.asyncio
async def test_dependency_audit_tool():
    res = await _dependency_audit(
        {
            "source_path": "src/nexus/infrastructure/adapters/execution/registry_tool_executor.py",
            "requirements_path": "requirements.in",
            "pyproject_path": "pyproject.toml",
        }
    )
    assert "declared" in res
    assert "imported" in res
    assert "aiohttp" in res["declared"]
    assert res["clean"] is True


@pytest.mark.asyncio
async def test_regex_extract_named_groups():
    text = "192.168.1.1 - [200] GET /index.html\n10.0.0.1 - [404] POST /api/login\n"
    res = await _regex_extract(
        {
            "pattern": r"(?P<ip>\d+\.\d+\.\d+\.\d+) - \[(?P<status>\d{3})\] (?P<method>[A-Z]+) (?P<path>\S+)",
            "text": text,
        }
    )
    assert res["named_groups"] is True
    assert res["total_matches"] == 2
    assert res["matches"][0] == {
        "ip": "192.168.1.1",
        "status": "200",
        "method": "GET",
        "path": "/index.html",
    }
    assert res["matches"][1]["status"] == "404"


@pytest.mark.asyncio
async def test_regex_extract_unnamed_groups():
    text = "alpha: 123, beta: 456, gamma: 789"
    res = await _regex_extract(
        {
            "pattern": r"([a-z]+): (\d+)",
            "text": text,
        }
    )
    assert res["named_groups"] is False
    assert res["total_matches"] == 3
    assert res["matches"] == [["alpha", "123"], ["beta", "456"], ["gamma", "789"]]


@pytest.mark.asyncio
async def test_regex_extract_flags_and_errors():
    text = "ERROR: connection failed\nerror: timeout"
    res = await _regex_extract(
        {
            "pattern": r"^error: (.+)$",
            "text": text,
            "flags": "im",
        }
    )
    assert res["total_matches"] == 2
    assert res["matches"] == ["connection failed", "timeout"]

    err_res = await _regex_extract(
        {
            "pattern": "[invalid regex",
            "text": text,
        }
    )
    assert "error" in err_res
    assert err_res["total_matches"] == 0


@pytest.mark.asyncio
async def test_regex_extract_file_path(tmp_path):
    p = tmp_path / "sample.log"
    p.write_text("HOST=prod-db-1\nHOST=prod-db-2\n", encoding="utf-8")
    res = await _regex_extract(
        {
            "pattern": r"HOST=(?P<host>[^\n]+)",
            "path": str(p),
        }
    )
    assert res["named_groups"] is True
    assert res["total_matches"] == 2
    assert res["matches"][0]["host"] == "prod-db-1"
    assert res["matches"][1]["host"] == "prod-db-2"
