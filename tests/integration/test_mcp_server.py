from __future__ import annotations

import json

from starlette.testclient import TestClient

from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.di.container import Config


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-key"}


def test_mcp_tools_are_exposed_from_the_registry(monkeypatch) -> None:
    monkeypatch.setenv(
        "NEXUS_API_KEYS", '{"test-key":{"user_id":"xenom","tenant_id":"default","role":"admin"}}'
    )
    app = create_app(config=Config())
    client = TestClient(app)

    resp = client.get("/api/mcp/tools", headers=_auth_headers())
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) >= 1
    names = {tool["name"] for tool in tools}
    assert "web_search" in names
    assert "calculator" in names


def test_mcp_memory_and_status_resources_are_callable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "NEXUS_API_KEYS", '{"test-key":{"user_id":"xenom","tenant_id":"default","role":"admin"}}'
    )
    app = create_app(config=Config())
    from nexus.infrastructure.di.container import Container

    container = Container(config=Config())
    memory_path = tmp_path / "agent_memory.json"
    memory_path.write_text(json.dumps({"chunks": []}), encoding="utf-8")
    container.mcp_server.memory_store = container.mcp_server.memory_store.__class__(memory_path)
    container.mcp_server.memory_store.put(
        "xenom", "note", "MCP memory test for CI health", tags=["mcp", "ci"]
    )
    app.state.container = container
    client = TestClient(app)

    resp = client.post(
        "/api/mcp/memory/query",
        json={"query": "CI health MCP", "limit": 5},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] >= 1
    assert "CI" in payload["results"][0]["text"]

    status = client.get("/api/mcp/consensus", headers=_auth_headers())
    assert status.status_code == 200
    assert isinstance(status.json(), dict)


def test_mcp_server_respects_fail_closed_auth(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_API_KEYS", raising=False)
    app = create_app(config=Config(api_keys={}))
    client = TestClient(app)

    resp = client.get("/api/mcp/tools")
    assert resp.status_code == 401
