"""Model catalog + per-request NVIDIA NIM model changer tests."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.infrastructure.api.main import create_app
from tests.fakes.container import TEST_API_KEY_1, FakeContainer

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
SELECTED_MODEL = "openai/gpt-oss-20b"


@pytest.fixture
def client_and_fake():
    app = create_app()
    fake = FakeContainer(
        llm_script={
            "complete": "I considered the alternatives carefully.\nFINAL ANSWER: Hello from the configured cortex."
        }
    )
    # Force deterministic, offline NIM simulation for per-request models.
    fake.nim_provider.set_api_key("")
    app.state.container = fake
    client = TestClient(app, raise_server_exceptions=False)
    client.app.state.container = fake
    return client, fake


def test_model_catalog_lists_auto_and_nim_capabilities(client_and_fake):
    client, _fake = client_and_fake

    assert client.get("/api/models").status_code == 401

    response = client.get("/api/models", headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["models"][0]["id"] == "auto"
    assert payload["models"][0]["source"] == "nexus-default"
    assert payload["provider_status"] == "simulation"
    assert payload["has_api_key"] is False
    assert payload["capability_labels"]["reasoning"] == "Extended thinking"

    models = {model["id"]: model for model in payload["models"]}
    assert SELECTED_MODEL in models
    assert models[SELECTED_MODEL]["source"] == "nvidia-nim"
    assert "reasoning" in models[SELECTED_MODEL]["capabilities"]
    assert models["meta/llama-3.2-90b-vision-instruct"]["capabilities"]
    assert "vision" in models["meta/llama-3.2-90b-vision-instruct"]["capabilities"]


def test_auto_chat_uses_configured_llm_and_gates_thinking(client_and_fake):
    client, _fake = client_and_fake

    without_thinking = client.post(
        "/v1/chat",
        headers=AUTH,
        json={"message": "hello", "session_id": "auto-plain", "model": "auto"},
    )
    assert without_thinking.status_code == 200
    plain = without_thinking.json()
    assert plain["response"] == "Hello from the configured cortex."
    assert plain["model_source"] == "nexus-default"
    assert plain["thinking"] == []

    with_thinking = client.post(
        "/v1/chat",
        headers=AUTH,
        json={
            "message": "think first",
            "session_id": "auto-thinking",
            "model": "auto",
            "extended_thinking": True,
        },
    )
    assert with_thinking.status_code == 200
    payload = with_thinking.json()
    assert payload["thinking"] == ["I considered the alternatives carefully."]
    assert "FINAL ANSWER" not in payload["thinking"][0]


def test_nim_chat_runs_selected_model_without_mutating_shared_provider(client_and_fake):
    client, fake = client_and_fake
    shared_provider = fake.nim_provider
    shared_model_before = shared_provider.model
    assert shared_model_before != SELECTED_MODEL

    response = client.post(
        "/v1/chat",
        headers=AUTH,
        json={
            "message": "hello from the selected model",
            "session_id": "nim-selected",
            "model": SELECTED_MODEL,
            "extended_thinking": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == SELECTED_MODEL
    assert payload["model_source"] == "nvidia-nim"
    assert payload["provider_status"] == "simulation"
    assert SELECTED_MODEL in payload["response"]
    # The request must have used a fresh provider instance: the shared
    # container provider and its model remain exactly as they were.
    assert fake.nim_provider is shared_provider
    assert fake.nim_provider.model == shared_model_before


def test_unknown_model_is_rejected_before_processing(client_and_fake):
    client, _fake = client_and_fake

    response = client.post(
        "/v1/chat",
        headers=AUTH,
        json={"message": "hello", "model": "bogus/model"},
    )
    assert response.status_code == 400
    assert "Unknown model 'bogus/model'" in response.json()["detail"]

    stream = client.post(
        "/v1/chat/stream",
        headers=AUTH,
        json={"message": "hello", "model": "bogus/model"},
    )
    assert stream.status_code == 400
    assert stream.headers["content-type"].startswith("application/json")


def test_stream_frames_carry_model_changer_metadata(client_and_fake):
    client, _fake = client_and_fake

    response = client.post(
        "/v1/chat/stream",
        headers=AUTH,
        json={
            "message": "stream with the selected model",
            "session_id": "nim-stream",
            "model": SELECTED_MODEL,
        },
    )

    assert response.status_code == 200
    events = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))

    assert events[0]["type"] == "start"
    assert events[0]["model"] == SELECTED_MODEL
    assert events[0]["model_source"] == "nvidia-nim"
    answers = [event for event in events if event["type"] == "answer"]
    assert len(answers) == 1
    assert answers[0]["model"] == SELECTED_MODEL
    assert answers[0]["provider_status"] == "simulation"
    assert events[-1] == {"type": "done"}


def test_auto_nim_routing_uses_effort_and_returns_quality_metadata(client_and_fake):
    client, fake = client_and_fake
    fake.nim_provider.model = "meta/llama-3.3-70b-instruct"
    fake.llm = fake.nim_provider
    fake.process_message._llm = fake.nim_provider

    catalog = client.get("/api/models", headers=AUTH)
    assert catalog.status_code == 200
    assert catalog.json()["execution"]["adaptive_model_routing"] is True
    assert catalog.json()["execution"]["efforts"] == [
        "auto",
        "fast",
        "balanced",
        "deep",
        "max",
    ]

    fast = client.post(
        "/v1/chat",
        headers=AUTH,
        json={
            "message": "hello",
            "session_id": "auto-fast",
            "model": "auto",
            "effort": "fast",
        },
    )
    assert fast.status_code == 200
    fast_body = fast.json()
    assert fast_body["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert fast_body["model_source"] == "nexus-auto"
    assert fast_body["execution"]["requested_effort"] == "fast"
    assert fast_body["execution"]["effective_effort"] == "fast"
    assert fast_body["quality"]["status"] in {"verified", "degraded"}

    maximum = client.post(
        "/v1/chat",
        headers=AUTH,
        json={
            "message": "Design a secure distributed consensus architecture and compare the trade-offs in detail",
            "session_id": "auto-max",
            "model": "auto",
            "effort": "max",
        },
    )
    assert maximum.status_code == 200
    max_body = maximum.json()
    assert max_body["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert max_body["model_source"] == "nexus-auto"
    assert max_body["execution"]["effective_effort"] == "max"
    assert max_body["quality"]["score"] >= 0
    assert fake.nim_provider.model == "meta/llama-3.3-70b-instruct"


def test_invalid_effort_is_rejected_and_stream_metadata_contains_quality(client_and_fake):
    client, _fake = client_and_fake

    invalid = client.post(
        "/v1/chat",
        headers=AUTH,
        json={"message": "hello", "model": "auto", "effort": "ludicrous"},
    )
    assert invalid.status_code == 422

    response = client.post(
        "/v1/chat/stream",
        headers=AUTH,
        json={
            "message": "hello",
            "session_id": "effort-stream",
            "model": "auto",
            "effort": "balanced",
        },
    )
    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data:").strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert events[0]["effort"] == "balanced"
    metadata = next(event for event in events if event["type"] == "metadata")
    assert metadata["execution"]["requested_effort"] == "balanced"
    assert metadata["quality"]["status"] in {"verified", "degraded", "guardrail_blocked"}
