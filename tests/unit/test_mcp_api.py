"""Test MCP tool listing and UI action execution."""

from starlette.testclient import TestClient

from nexus.infrastructure.api.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer sk-test-1"}


def test_mcp_list_tools():
    app = create_app()
    client = TestClient(app, headers=AUTH_HEADERS)
    resp = client.get("/api/mcp/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) >= 4
    tool_names = [t["name"] for t in tools]
    assert "process_multimodal_media" in tool_names
    assert "open_ui_module" in tool_names
    assert "switch_operating_mode" in tool_names
    assert "trigger_system_alert" in tool_names


def test_mcp_execute_open_module():
    app = create_app()
    client = TestClient(app, headers=AUTH_HEADERS)
    resp = client.post(
        "/api/mcp/execute",
        json={
            "tool": "open_ui_module",
            "parameters": {"module": "multimodal_bridge"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["ui_action"]["type"] == "OPEN_MODAL"
    assert data["ui_action"]["target"] == "multimodal_bridge"


def test_mcp_execute_alert():
    app = create_app()
    client = TestClient(app, headers=AUTH_HEADERS)
    resp = client.post(
        "/api/mcp/execute",
        json={
            "tool": "trigger_system_alert",
            "parameters": {"severity": "critical", "message": "High entropy detected"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ui_action"]["type"] == "TRIGGER_ALERT"
    assert data["ui_action"]["severity"] == "critical"
