"""
Production hardening tests (Phase 2, Priority 1).

Covers the P1 deliverables end to end against fakes + MockTransport:
  - auth: bearer tokens -> Identity, no more client-supplied user_id
  - multi-tenancy: memory/concept isolation + Qdrant collection naming
  - observability: /metrics exposition + use-case spans/counters
  - rate limiting: sliding window on /v1/chat and /v1/tools/generate
  - secrets: env / JSON file / chained stores
  - deployers: Railway + Vercel adapters (MockTransport), container selection
"""

import sys
import asyncio
import json
from pathlib import Path

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.di.container import Config, Container
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.entities.concept import Concept
from nexus.domain.ports.deployment import DeploymentRequest
from nexus.domain.ports.observability import Span, Tracer
from nexus.infrastructure.adapters.observability.observability import InMemoryMetrics
from nexus.infrastructure.adapters.security.secrets import ChainedSecretStore, EnvSecretStore, JsonFileSecretStore
from nexus.infrastructure.adapters.persistence.qdrant_memory_repository import QdrantMemoryRepository

from tests.fakes import (
    FakeConceptRepository,
    FakeEventBus,
    FakeExecutor,
    FakeLLM,
    FakeMemoryRepository,
    FakeShortTermMemory,
    FakeToolRegistry,
)
from tests.fakes.container import FakeContainer, TEST_API_KEY_1, TEST_API_KEY_2

AUTH_T1 = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
AUTH_T2 = {"Authorization": f"Bearer {TEST_API_KEY_2}"}


class _RecSpan(Span):
    def __init__(self, name, attributes, recorder):
        super().__init__(name)
        self.attributes = dict(attributes or {})
        self._rec = recorder

    async def __aenter__(self):
        self._rec.starts.append((self.name, dict(self.attributes)))
        return self

    async def __aexit__(self, *exc):
        self._rec.ends.append((self.name, dict(self.attributes)))
        return False


class RecordingTracer(Tracer):
    def __init__(self):
        self.starts = []
        self.ends = []

    def span(self, name, attributes=None):
        return _RecSpan(name, attributes, self)


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


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #


def test_chat_rejects_missing_token(app, client):
    _inject_container(client, app)
    r = client.post("/v1/chat", json={"message": "hi", "session_id": "s1"})
    assert r.status_code == 401


def test_chat_rejects_invalid_token(app, client):
    _inject_container(client, app)
    r = client.post(
        "/v1/chat",
        json={"message": "hi", "session_id": "s1"},
        headers={"Authorization": "Bearer sk-nope"},
    )
    assert r.status_code == 401


def test_memory_and_tools_require_auth(app, client):
    _inject_container(client, app)
    assert client.get("/v1/memory/search", params={"query": "x"}).status_code == 401
    assert client.get("/v1/tools").status_code == 401
    assert client.post("/v1/system/dream").status_code == 401
    # health stays public for load balancers / k8s probes
    assert client.get("/v1/system/health").status_code == 200


def test_identity_comes_from_token_not_body(app, client):
    fake = _inject_container(client, app, llm_script={"complete": "FINAL ANSWER: hi"})
    r = client.post(
        "/v1/chat",
        json={"message": "hello", "user_id": "spoofed-identity", "session_id": "s1"},
        headers=AUTH_T1,
    )
    assert r.status_code == 200
    stored = list(fake.memory_repo.memories.values())[0]
    assert stored.metadata["user_id"] == "u1"  # from the token, not the body
    assert stored.metadata["tenant_id"] == "t1"


# --------------------------------------------------------------------------- #
#  Multi-tenancy
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_memory_repository_isolates_tenants():
    repo = FakeMemoryRepository()
    await repo.store(Memory(content="tenant one secret", memory_type=MemoryType.SEMANTIC), tenant_id="t1")
    await repo.store(Memory(content="tenant two secret", memory_type=MemoryType.SEMANTIC), tenant_id="t2")

    t1 = await repo.retrieve("", tenant_id="t1")
    t2 = await repo.retrieve("", tenant_id="t2")
    default = await repo.retrieve("")

    assert [m.content for m in t1] == ["tenant one secret"]
    assert [m.content for m in t2] == ["tenant two secret"]
    assert default == []


@pytest.mark.asyncio
async def test_concept_repository_isolates_tenants():
    repo = FakeConceptRepository()
    await repo.upsert(Concept(label="nextjs", concept_type="tech"), tenant_id="t1")
    await repo.upsert(Concept(label="nextjs", concept_type="tech"), tenant_id="t2")

    assert len(await repo.find_by_label("nextjs", tenant_id="t1")) == 1
    assert len(await repo.find_by_label("nextjs", tenant_id="t2")) == 1
    # same label in two tenants produces two distinct concepts
    labels = await repo.find_by_label("nextjs")
    assert len(labels) == 0  # default tenant sees none


def test_qdrant_collection_names_are_tenant_scoped():
    assert QdrantMemoryRepository.collection_name_for("default") == "nexus_memory"
    assert QdrantMemoryRepository.collection_name_for("acme") == "nexus_memory_acme"
    assert QdrantMemoryRepository.collection_name_for("Weird Tenant!") == "nexus_memory_weirdtenant"


def test_chat_isolates_tenants_end_to_end(app, client):
    fake = _inject_container(client, app, llm_script={"complete": "FINAL ANSWER: ok"})
    r1 = client.post("/v1/chat", json={"message": "tenant one secret", "session_id": "sA"}, headers=AUTH_T1)
    r2 = client.post("/v1/chat", json={"message": "tenant two secret", "session_id": "sB"}, headers=AUTH_T2)
    assert r1.status_code == 200 and r2.status_code == 200

    t1 = asyncio.run(fake.memory_repo.retrieve("", limit=10, tenant_id="t1"))
    t2 = asyncio.run(fake.memory_repo.retrieve("", limit=10, tenant_id="t2"))
    assert "tenant one secret" in t1[0].content
    assert "tenant two secret" in t2[0].content


# --------------------------------------------------------------------------- #
#  Observability
# --------------------------------------------------------------------------- #


def test_metrics_endpoint_reports_request_and_brain_counters(app, client):
    _inject_container(client, app)
    client.get("/v1/system/health")
    client.post("/v1/chat", json={"message": "hi", "session_id": "s1"}, headers=AUTH_T1)

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'route="/v1/chat"' in body
    assert "http_requests_total" in body
    assert 'chat_messages_total{tenant_id="t1"}' in body


@pytest.mark.asyncio
async def test_process_message_emits_span_and_metrics():
    event_bus = FakeEventBus()
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(script={"complete": "FINAL ANSWER: ok"})
    sessions = _session_manager(working)
    tracer = RecordingTracer()
    metrics = InMemoryMetrics()

    use_case = _process_message(llm, memory_repo, concept_repo, working, event_bus, sessions, tracer, metrics)
    await use_case.execute(user_id="u1", message="hello", tenant_id="acme")

    assert any(name == "process_message" for name, _ in tracer.starts)
    assert any(name == "process_message" for name, _ in tracer.ends)
    rendered = metrics.render()
    assert 'chat_messages_total{tenant_id="acme"}' in rendered
    assert "chat_processing_duration_seconds_sum" in rendered


# --------------------------------------------------------------------------- #
#  Rate limiting
# --------------------------------------------------------------------------- #


def test_chat_rate_limit_enforced(app, client):
    fake = _inject_container(client, app)
    cfg = Config()
    cfg.chat_rate_limit = 2
    cfg.rate_limit_window_seconds = 60
    fake.config = cfg

    for _ in range(2):
        assert client.post("/v1/chat", json={"message": "hi", "session_id": "s1"}, headers=AUTH_T1).status_code == 200
    assert client.post("/v1/chat", json={"message": "hi", "session_id": "s1"}, headers=AUTH_T1).status_code == 429


def test_tool_generate_rate_limit_enforced(app, client):
    fake = _inject_container(client, app, llm_script={"complete": "def solve(input_data):\n    return {'ok': True}"})
    cfg = Config()
    cfg.tool_gen_rate_limit = 1
    cfg.rate_limit_window_seconds = 60
    fake.config = cfg

    payload = {
        "name": "rate_tool",
        "problem_statement": "write a tool that always returns ok",
        "input_examples": [{"x": 1}],
        "expected_outputs": [{"ok": True}],
    }
    assert client.post("/v1/tools/generate", json=payload, headers=AUTH_T1).status_code == 200
    assert client.post("/v1/tools/generate", json=payload, headers=AUTH_T1).status_code == 429


# --------------------------------------------------------------------------- #
#  Secrets
# --------------------------------------------------------------------------- #


def test_env_secret_store(monkeypatch):
    monkeypatch.setenv("SECRET_TEST_A", "alpha")
    store = EnvSecretStore()
    assert store.get("SECRET_TEST_A") == "alpha"
    assert store.get("SECRET_TEST_MISSING") is None


def test_json_file_secret_store(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text('{"OPENAI_API_KEY": "sk-json"}')
    store = JsonFileSecretStore(str(path))
    assert store.get("OPENAI_API_KEY") == "sk-json"


def test_chained_secret_store_first_store_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TEST_A", "env-value")
    path = tmp_path / "secrets.json"
    path.write_text('{"SECRET_TEST_A": "json-value", "SECRET_TEST_B": "json-b"}')

    store = ChainedSecretStore([JsonFileSecretStore(str(path)), EnvSecretStore()])
    assert store.get("SECRET_TEST_A") == "json-value"  # file is first in the chain
    assert store.get("SECRET_TEST_B") == "json-b"
    assert store.get("SECRET_TEST_MISSING") is None


# --------------------------------------------------------------------------- #
#  Deployers
# --------------------------------------------------------------------------- #


def test_railway_deployer_posts_graphql_mutation():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"serviceCreate": {"id": "svc-123"}}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from nexus.infrastructure.adapters.deployment.railway_deployer import RailwayDeployer

    deployer = RailwayDeployer(token="tok", project_id="proj", http_client=client)
    info = asyncio.run(deployer.deploy(DeploymentRequest(tool_id="t1", name="my_tool", code="x")))
    asyncio.run(client.aclose())

    assert info.platform == "railway"
    assert info.deployment_id == "svc-123"
    assert info.endpoint == "https://my_tool.up.railway.app"
    assert captured["auth"] == "Bearer tok"
    assert "serviceCreate" in captured["body"]["query"]
    assert captured["body"]["variables"]["name"] == "my_tool"


def test_vercel_deployer_posts_files_and_undeploys():
    log = []

    def handler(request):
        log.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(201, json={"id": "dpl-1", "url": "my-tool.vercel.app"})
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from nexus.infrastructure.adapters.deployment.vercel_deployer import VercelDeployer

    deployer = VercelDeployer(token="tok", team_id="team", http_client=client)
    info = asyncio.run(
        deployer.deploy(
            DeploymentRequest(
                tool_id="t1", name="my_tool", code="def solve(d): return d", requirements=["fastapi"]
            )
        )
    )
    assert info.platform == "vercel"
    assert info.deployment_id == "dpl-1"
    assert info.endpoint == "https://my-tool.vercel.app"

    asyncio.run(deployer.undeploy("dpl-1"))
    asyncio.run(client.aclose())

    assert ("DELETE", "https://api.vercel.com/v13/deployments/dpl-1") in log


def test_container_deployer_defaults_to_local():
    c = Container.__new__(Container)
    c.config = Config()
    c.secrets = EnvSecretStore()

    from nexus.infrastructure.adapters.deployment.local_deployer import LocalDeployer

    assert isinstance(c._build_deployer(), LocalDeployer)


def test_container_deployer_selects_railway_when_configured(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    c = Container.__new__(Container)
    c.config = Config()
    c.config.deploy_platform = "railway"
    c.secrets = EnvSecretStore()

    from nexus.infrastructure.adapters.deployment.railway_deployer import RailwayDeployer

    assert isinstance(c._build_deployer(), RailwayDeployer)


def test_container_deployer_fails_fast_when_cloud_token_missing():
    c = Container.__new__(Container)
    c.config = Config()
    c.config.deploy_platform = "railway"
    c.secrets = EnvSecretStore()

    with pytest.raises(ValueError, match="RAILWAY_TOKEN"):
        c._build_deployer()


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #


def _session_manager(working):
    from nexus.application.cortex.session_manager import SessionManager

    return SessionManager(working)


def _process_message(llm, memory_repo, concept_repo, working, event_bus, sessions, tracer, metrics):
    from nexus.application.cortex.process_message import ProcessMessageUseCase

    return ProcessMessageUseCase(
        llm=llm,
        memory_repo=memory_repo,
        concept_repo=concept_repo,
        working_memory=working,
        tools=FakeToolRegistry(),
        executor=FakeExecutor(),
        event_bus=event_bus,
        session_manager=sessions,
        tracer=tracer,
        metrics=metrics,
    )
