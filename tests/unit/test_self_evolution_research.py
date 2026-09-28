"""
Tests for Recursive Self-Evolution & Self-Improvement via Deep Research.

Verifies:
1. Deep Research executes and generates meta-cognitive self-evolution reflection
   ("How can I upgrade myself from this?").
2. Synthesized tool specification is generated from research findings.
3. POST /api/research/apply-upgrade registers the synthesized tool into ToolRegistry
   and wires it into the live ToolExecutor.
4. Second Brain Knowledge Graph dynamically ingests the evolution node and links it.
5. Coding Assistant incorporates self-evolution reflections into thinking and artifacts.
"""

import pytest
from starlette.testclient import TestClient

from nexus.infrastructure.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_deep_research_generates_self_evolution_reflection(client):
    """Verify that deep research triggers self-evolution analysis and tool synthesis."""
    res = client.post(
        "/api/research/execute",
        json={"query": "adaptive neural routing and token speculative pruning"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "self_evolution" in data

    evo = data["self_evolution"]
    assert "how_to_upgrade_myself" in evo
    assert len(evo["how_to_upgrade_myself"]) > 50
    assert "Capability Gap Identified" in evo["how_to_upgrade_myself"]
    assert "Self-Evolution Solution" in evo["how_to_upgrade_myself"]

    assert len(evo["architectural_gaps"]) >= 2
    assert len(evo["capability_boosts"]) >= 2

    # Check synthesized tool proposal
    tool = evo["synthesized_tool"]
    assert tool is not None
    assert "tool_synth_" in tool["id"]
    assert len(tool["name"]) > 0
    assert "python_code" in tool
    assert "evolved_execution_success" in tool["python_code"]
    assert tool["status"] == "proposed"


def test_apply_self_upgrade_registers_tool_and_updates_graph(client):
    """Verify applying a self-upgrade registers the tool in the live runtime and adds graph nodes."""
    tool_id = "tool_synth_quantum_telemetry"
    tool_payload = {
        "id": tool_id,
        "name": "Quantum Telemetry Weaver",
        "description": "Synthesized quantum circuit optimization tool from research.",
        "language": "python",
        "python_code": "return {'status': 'evolved_execution_success', 'speedup': '2.4x'}",
        "parameters": {
            "type": "object",
            "properties": {"input": {"type": "string"}},
        },
        "status": "proposed",
    }

    upgrade_res = client.post(
        "/api/research/apply-upgrade",
        json={
            "query": "quantum telemetry weaving",
            "tool": tool_payload,
            "auto_register": True,
            "connect_to_graph": True,
        },
    )
    assert upgrade_res.status_code == 200
    up_data = upgrade_res.json()
    assert up_data["success"] is True
    assert up_data["tool_id"] == tool_id
    assert up_data["registered_in_registry"] is True
    assert "Evolution: Quantum Telemetry Weaver" in up_data["graph_node_id"]

    # Verify the Second Brain graph now contains this evolution node
    graph_res = client.get("/api/graph")
    assert graph_res.status_code == 200
    g_data = graph_res.json()
    node_ids = [n["id"] for n in g_data["nodes"]]
    assert up_data["graph_node_id"] in node_ids

    # Verify Prometheus metrics sees the upgraded tools count
    metrics_res = client.get("/api/system/telemetry")
    assert metrics_res.status_code == 200
    telemetry = metrics_res.json()
    assert telemetry["tools_count"] >= 21


def test_coding_assistant_with_self_evolution_query(client):
    """Verify that Claude Coding Studio handles self-evolution requests with tools and artifacts."""
    res = client.post(
        "/api/coding/chat",
        json={
            "prompt": "Conduct deep research on speculative multi-token drafting and explain how you can upgrade yourself from this.",
            "enable_web_search": True,
            "enable_code_exec": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["thinking"]) > 0
    assert len(data["response"]) > 0
    assert any(t["tool"] == "web_search" for t in data["tools_used"])
    assert any(a["type"] == "research" for a in data["artifacts"])
