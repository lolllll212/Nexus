"""
Tests for Integrations (GitHub/Gmail), Autonomous Research, Workflows, and Audio routes.
"""

import pytest
from fastapi.testclient import TestClient
from nexus.infrastructure.api.main import create_app
from tests.fakes.container import FakeContainer


@pytest.fixture
def client():
    app = create_app()
    fake = FakeContainer()
    app.state.container = fake
    return TestClient(app)


def test_github_integration_endpoints(client):
    res_status = client.get("/api/integrations/github/status")
    assert res_status.status_code == 200
    assert res_status.json()["connected"] is True

    res_repos = client.get("/api/integrations/github/repos")
    assert res_repos.status_code == 200
    assert len(res_repos.json()) >= 2

    res_issues = client.get("/api/integrations/github/issues")
    assert res_issues.status_code == 200
    assert len(res_issues.json()) >= 2

    res_pulls = client.get("/api/integrations/github/pulls")
    assert res_pulls.status_code == 200
    assert len(res_pulls.json()) >= 1

    res_create = client.post(
        "/api/integrations/github/create-issue",
        json={"title": "Test Issue", "body": "Testing automated creation"},
    )
    assert res_create.status_code == 200
    assert res_create.json()["status"] == "created"


def test_gmail_integration_endpoints(client):
    res_status = client.get("/api/integrations/gmail/status")
    assert res_status.status_code == 200
    assert res_status.json()["connected"] is True

    res_msgs = client.get("/api/integrations/gmail/messages")
    assert res_msgs.status_code == 200
    assert len(res_msgs.json()) >= 2

    res_sum = client.post("/api/integrations/gmail/summarize")
    assert res_sum.status_code == 200
    assert "executive_summary" in res_sum.json()

    res_send = client.post(
        "/api/integrations/gmail/send",
        json={"to": "test@example.com", "subject": "Test Subj", "body": "Test Body"},
    )
    assert res_send.status_code == 200
    assert res_send.json()["status"] == "sent"


def test_autonomous_research_execution(client):
    res = client.post(
        "/api/research/execute",
        json={"query": "Quantum neural networks", "max_sources": 3, "auto_ingest_graph": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "Quantum neural networks"
    assert "summary" in data
    assert len(data["sources"]) >= 1
    assert len(data["extracted_concepts"]) >= 1


def test_workflows_endpoints(client):
    res_list = client.get("/api/workflows")
    assert res_list.status_code == 200
    workflows = res_list.json()
    assert len(workflows) >= 3

    target_id = workflows[0]["id"]
    res_run = client.post(f"/api/workflows/run/{target_id}")
    assert res_run.status_code == 200
    assert res_run.json()["status"] == "completed"
    assert len(res_run.json()["execution_logs"]) > 0


def test_audio_endpoints(client):
    res_status = client.get("/api/audio/status")
    assert res_status.status_code == 200
    assert "stt" in res_status.json()

    res_tts = client.post(
        "/api/audio/tts",
        json={"text": "J.A.R.V.I.S. online, all systems nominal."},
    )
    assert res_tts.status_code == 200
    assert res_tts.json()["status"] == "success"

    res_stt = client.post(
        "/api/audio/stt",
        data={"transcript_hint": "Jarvis, zoom in on AI Workshop"},
    )
    assert res_stt.status_code == 200
    assert res_stt.json()["text"] == "Jarvis, zoom in on AI Workshop"
