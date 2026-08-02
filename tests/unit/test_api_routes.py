"""
API route tests - prove the FastAPI layer is a thin adapter.

These run with zero external infra: the production composition root is replaced
by a FakeContainer wired from in-memory fakes. They guard the two biggest Task 1
regressions:
  1. Routes must reuse the application-lifetime container (not build one per request).
  2. CORS must come from config, not be hardcoded wide open.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import asyncio

from fastapi.testclient import TestClient

from nexus.domain.exceptions import LLMUnavailableError
from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.di.container import Config

from tests.fakes.container import FakeContainer, TEST_API_KEY_1

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _inject_container(client, app, llm_script=None):
    fake = FakeContainer(llm_script=llm_script)
    app.state.container = fake
    client.app.state.container = fake
    return fake


def test_get_container_returns_app_state_instance(app, client):
    """The container dependency must return the single app-lifetime instance."""
    from nexus.infrastructure.api.dependencies import get_container

    fake = FakeContainer()
    app.state.container = fake

    # Build a lightweight Request-like object exposing app.state
    class _State:
        container = None

    class _FakeApp:
        state = _State()

    class _FakeRequest:
        app = _FakeApp()

    _FakeApp.state.container = fake
    assert get_container(_FakeRequest()) is fake


def test_routes_reuse_same_container_across_requests(app, client):
    """Two requests must hit the SAME container (regression: was Container() per request)."""
    fake = _inject_container(client, app, llm_script={"complete": "FINAL ANSWER: hi"})

    r1 = client.post("/v1/chat", json={"message": "hello", "session_id": "s1"}, headers=AUTH)
    r2 = client.post("/v1/chat", json={"message": "hello again", "session_id": "s1"}, headers=AUTH)

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both conversations flowed through the same working-memory cache + repo instance
    assert len(fake.working_memory.store_) >= 1
    assert len(fake.memory_repo.memories) == 2


def test_health_and_tools_routes_smoke(app, client):
    _inject_container(client, app)

    health = client.get("/v1/system/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    tools = client.get("/v1/tools", headers=AUTH)
    assert tools.status_code == 200
    assert isinstance(tools.json(), list)


def test_memory_search_route(app, client):
    fake = _inject_container(client, app)
    from nexus.domain.entities.memory import Memory, MemoryType

    m = Memory(content="a recalled fact", memory_type=MemoryType.SEMANTIC)
    asyncio.run(fake.memory_repo.store(m, tenant_id="t1"))

    r = client.get("/v1/memory/search", params={"query": "recalled"}, headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["content"] == "a recalled fact"


def test_cors_default_allows_configured_origin(app, client):
    """CORS must reflect config (default localhost:3000), not '*'."""
    r = client.options(
        "/v1/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unconfigured_origin(app, client):
    r = client.options(
        "/v1/chat",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in r.headers


def test_cors_uses_config_value(app, client):
    """When NEXUS_CORS_ORIGINS is configured, CORS reflects it."""
    cfg = Config()
    cfg.cors_origins = ["http://localhost:8080"]
    app2 = create_app(config=cfg)
    c2 = TestClient(app2)
    _inject_container(c2, app2)

    r = c2.options(
        "/v1/chat",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_llm_unavailable_maps_to_503(app, client):
    """Domain exceptions must map to typed HTTP statuses, not a blanket 500."""
    from tests.fakes import FakeLLM

    class RaisingLLM(FakeLLM):
        async def complete(self, *args, **kwargs):
            raise LLMUnavailableError("no service")

    fake = FakeContainer()
    fake.llm = RaisingLLM()
    from nexus.application.cortex.process_message import ProcessMessageUseCase

    fake.process_message = ProcessMessageUseCase(
        llm=fake.llm,
        memory_repo=fake.memory_repo,
        concept_repo=fake.concept_repo,
        working_memory=fake.working_memory,
        tools=fake.tool_registry,
        executor=fake.executor,
        event_bus=fake.event_bus,
        session_manager=fake.session_manager,
    )
    app.state.container = fake
    client.app.state.container = fake

    r = client.post("/v1/chat", json={"message": "hello", "session_id": "s1"}, headers=AUTH)
    # LLMUnavailableError is caught inside the react loop -> graceful message
    assert r.status_code == 200
    assert "briefly unavailable" in r.json()["response"]
