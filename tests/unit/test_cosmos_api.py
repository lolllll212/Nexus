"""Cosmos API + local-UI auth bypass + HOLO deck wiring tests.

Runs with zero external infra: the app state is injected with a FakeContainer,
exactly like test_api_routes.py. LLM status probes are pre-cached (or stubbed)
so no test ever touches the network.
"""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator
from nexus.infrastructure.api.dependencies import local_ui_bypass_allowed
from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.api.routes import cosmos as cosmos_mod
from tests.fakes.container import TEST_API_KEY_1, FakeContainer

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}

_FAKE_LLM_STATUS = {
    "kind": "LM Studio",
    "base_url": "http://localhost:1234/v1",
    "model": "test-model",
    "background_model": "test-model",
    "embedding_model": "test-embed",
    "reachable": True,
    "latency_ms": 1.0,
    "models_loaded": ["test-model"],
    "error": None,
    "checked_at": "2026-09-23T00:00:00+00:00",
}


@pytest.fixture(autouse=True)
def _prime_llm_cache():
    """No test may hit a real LLM endpoint — serve a cached status."""
    cosmos_mod._LLM_CACHE.update({"ts": time.time(), "data": dict(_FAKE_LLM_STATUS)})
    yield
    cosmos_mod._LLM_CACHE.update({"ts": 0.0, "data": None})


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _inject(client, app, llm_script=None):
    fake = FakeContainer(llm_script=llm_script)
    app.state.container = fake
    client.app.state.container = fake
    return fake


# ---------------------------------------------------------------------------
# GET /api/llm/status
# ---------------------------------------------------------------------------


def test_llm_status_shape(app, client):
    _inject(client, app)
    # bypass the cache once to prove the endpoint reports gracefully when the
    # local provider is unreachable (no network in tests -> reachable False)
    r = client.get("/api/llm/status?force=true")
    assert r.status_code == 200
    body = r.json()
    for key in ("kind", "base_url", "model", "reachable", "latency_ms", "models_loaded"):
        assert key in body
    assert isinstance(body["reachable"], bool)


# ---------------------------------------------------------------------------
# GET /api/cosmos
# ---------------------------------------------------------------------------


def test_cosmos_mesh_has_live_core_and_triggerable_nodes(app, client, monkeypatch, tmp_path):
    # hermetic: real mesh config from the repo, but isolated integration state
    real_cfg = (
        Path(__file__).resolve().parents[2] / "frontend" / "config" / "nexus.config.json"
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "nexus.config.json").write_text(
        real_cfg.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("NEXUS_FRONTEND_DIR", str(tmp_path))
    _inject(client, app)
    r = client.get("/api/cosmos")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] and body["links"]
    by_id = {n["id"]: n for n in body["nodes"]}
    core = by_id["N.E.X.U.S"]
    assert core["status"] in ("online", "degraded")
    assert core["triggerable"] is True
    # the automation fabric joints exist and are runnable
    for joint in ("dream", "swarm", "tools", "memory", "concept"):
        assert by_id[joint]["triggerable"] is True
    for name in ("gmail", "drive", "github", "whatsapp", "telegram", "threads", "youtube"):
        assert by_id[name]["action"] == "toggle"
        assert by_id[name]["stats"]["enabled"] is False
    # the social media automation joint is a runner, not just a flag
    assert by_id["social"]["action"] == "run_social"
    assert by_id["social"]["triggerable"] is True
    # llm status is embedded for the reactor dial
    assert body["llm"]["kind"] == "LM Studio"
    assert "counts" in body and "activity" in body


def test_cosmos_mesh_falls_back_without_config(app, client, monkeypatch):
    monkeypatch.setenv("NEXUS_FRONTEND_DIR", "/nonexistent-dir")
    _inject(client, app)
    r = client.get("/api/cosmos")
    assert r.status_code == 200
    ids = {n["id"] for n in r.json()["nodes"]}
    assert {"N.E.X.U.S", "memory", "dream", "gmail"} <= ids


# ---------------------------------------------------------------------------
# POST /api/cosmos/trigger — the automations
# ---------------------------------------------------------------------------


def test_trigger_requires_auth_when_keys_configured(app, client):
    """Fail-closed: with any API key configured, anonymous triggers are denied."""
    _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "dream", "params": {}})
    assert r.status_code == 401


def test_trigger_unknown_node_404(app, client):
    _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "nope", "params": {}}, headers=AUTH)
    assert r.status_code == 404


def test_trigger_dream_cycle(app, client):
    fake = _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "dream", "params": {}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["session_id"]
    # the run is logged to the automation feed for the UI log panel
    events = fake.activity_feed.recent("cosmos", limit=5)
    assert any(e.get("node") == "dream" for e in events)


def test_trigger_swarm_autocreates_and_runs(app, client):
    fake = _inject(client, app, llm_script={"complete": "FINAL ANSWER: mesh ok"})
    r = client.post(
        "/api/cosmos/trigger",
        json={"node": "swarm", "params": {"task": "say your role"}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "swarm"
    assert "mesh ok" in (body["summary"] + json.dumps(body.get("worker_responses", {})))
    assert body["worker_responses"] == {} or isinstance(body["worker_responses"], dict)
    # cosmos agent + swarm persisted for the next run
    assert any(t == "t1" for (t, _sid) in fake.swarm_repo._swarms)


def test_trigger_tools_without_problem_is_safe(app, client):
    _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "tools", "params": {}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body.get("skipped") is True
    assert "tools" in body


def test_trigger_concept_stats(app, client):
    _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "concept", "params": {}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["concepts"] >= 0


def test_trigger_integration_toggle_persists(app, client, monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_FRONTEND_DIR", str(tmp_path))
    (tmp_path / "config").mkdir()
    _inject(client, app)
    r1 = client.post("/api/cosmos/trigger", json={"node": "gmail", "params": {}}, headers=AUTH)
    assert r1.status_code == 200 and r1.json()["enabled"] is True
    state = json.loads((tmp_path / "state" / "cosmos-integrations.json").read_text())
    assert state == {"gmail": True}
    r2 = client.post("/api/cosmos/trigger", json={"node": "gmail", "params": {}}, headers=AUTH)
    assert r2.json()["enabled"] is False
    # dynamically-registered integrations work the same way
    rt = client.post("/api/cosmos/trigger", json={"node": "whatsapp", "params": {}}, headers=AUTH)
    assert rt.status_code == 200 and rt.json()["enabled"] is True
    # explicit set endpoint
    r3 = client.post("/api/cosmos/integrations/github", json={"enabled": True}, headers=AUTH)
    assert r3.json() == {
        "ok": True,
        "name": "github",
        "enabled": True,
        "persisted": True,
        "integrations": {"gmail": False, "github": True, "whatsapp": True},
    }
    r4 = client.post("/api/cosmos/integrations/nope", json={"enabled": True}, headers=AUTH)
    assert r4.status_code == 404


def test_trigger_social_drafts_cross_post(app, client, monkeypatch, tmp_path):
    """The social automation runs the swarm and flips its flag on."""
    monkeypatch.setenv("NEXUS_FRONTEND_DIR", str(tmp_path))
    (tmp_path / "config").mkdir()
    _inject(client, app, llm_script={"complete": "FINAL ANSWER: we shipped the cosmos mesh today"})
    r = client.post("/api/cosmos/trigger", json={"node": "social", "params": {}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "social"
    assert "cosmos mesh" in body["draft"]
    state = json.loads((tmp_path / "state" / "cosmos-integrations.json").read_text())
    assert state["social"] is True


def test_trigger_core_pulse_reports_status(app, client, monkeypatch):
    async def fake_status(container, force=False):
        return dict(_FAKE_LLM_STATUS, reachable=False)

    monkeypatch.setattr(cosmos_mod, "llm_status", fake_status)
    _inject(client, app)
    r = client.post("/api/cosmos/trigger", json={"node": "N.E.X.U.S", "params": {}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "pulse"
    assert "unreachable" in body["summary"]


# ---------------------------------------------------------------------------
# Local-UI auth bypass (NEXUS_LOCAL_UI_AUTH)
# ---------------------------------------------------------------------------


class _NoKeyContainer(FakeContainer):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.authenticator = ApiKeyAuthenticator({})


def _req(host: str):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_bypass_auto_allows_loopback_only_when_no_keys():
    container = _NoKeyContainer()
    assert local_ui_bypass_allowed(_req("127.0.0.1"), container) is True
    assert local_ui_bypass_allowed(_req("::1"), container) is True
    assert local_ui_bypass_allowed(_req("10.1.2.3"), container) is False
    assert local_ui_bypass_allowed(_req("example.com"), container) is False


def test_bypass_auto_off_when_keys_exist():
    container = FakeContainer()  # keys configured
    assert local_ui_bypass_allowed(_req("127.0.0.1"), container) is False


def test_bypass_modes_force_and_disable():
    container = _NoKeyContainer()
    container.config = SimpleNamespace(local_ui_auth="true")
    assert local_ui_bypass_allowed(_req("203.0.113.9"), container) is True
    container.config = SimpleNamespace(local_ui_auth="false")
    assert local_ui_bypass_allowed(_req("127.0.0.1"), container) is False


def test_chat_works_without_bearer_for_local_ui(app, client):
    """End-to-end: loopback client + empty key table = the shipped UI just works."""
    fake = _NoKeyContainer(llm_script={"complete": "FINAL ANSWER: hi"})
    app.state.container = fake
    client.app.state.container = fake
    r = client.post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert r.json()["response"]


def test_chat_still_closed_for_remote_client_without_keys(app):
    """Auto mode never admits a non-loopback client, even with zero keys."""
    remote = TestClient(app, client=("203.0.113.9", 50000))
    fake = _NoKeyContainer()
    app.state.container = fake
    r = remote.post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# HOLO deck wiring (served by the backend itself)
# ---------------------------------------------------------------------------


def test_holo_tree_state_and_props(app, client, monkeypatch, tmp_path):
    notes = tmp_path / "notes"
    (notes / "JARVIS").mkdir(parents=True)
    (notes / "JARVIS" / "01-jarvis.md").write_text("# JARVIS\nvoice second brain\n", encoding="utf-8")
    (notes / "loose.md").write_text("# Loose\nfree note\n", encoding="utf-8")
    (tmp_path / "props").mkdir()
    (tmp_path / "props" / "apollo-11-module.glb").write_bytes(b"glb")
    (tmp_path / "holo.json").write_text(json.dumps({"folder": str(notes)}), encoding="utf-8")
    monkeypatch.setenv("NEXUS_FRONTEND_DIR", str(tmp_path))
    _inject(client, app)

    tree = client.get("/api/tree").json()
    assert any(f["name"] == "JARVIS" for f in tree)
    assert any(f["name"] == "NOTES" for f in tree)
    assert client.get("/api/props").json() == ["apollo-11-module.glb"]

    assert client.post("/api/state", json={"event": "grab", "card": "JARVIS"}).json() == {"ok": True}
    state = client.get("/api/state").json()
    assert state["event"] == "grab" and "ts" in state


def test_root_serves_the_ui(app, client):
    _inject(client, app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
