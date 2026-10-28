"""Chat history API + store tests for the web history window."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.infrastructure.adapters.persistence.chat_history_store import ChatHistoryStore
from nexus.infrastructure.api.main import create_app
from tests.fakes.container import TEST_API_KEY_1, TEST_API_KEY_2, FakeContainer

AUTH_1 = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
AUTH_2 = {"Authorization": f"Bearer {TEST_API_KEY_2}"}


@pytest.fixture
def client_and_fake():
    app = create_app()
    fake = FakeContainer()
    fake.history_store = ChatHistoryStore(path=None)
    app.state.container = fake
    client = TestClient(app, raise_server_exceptions=False)
    client.app.state.container = fake
    return client, fake


def _create_session(client, headers=AUTH_1, **overrides):
    payload = {
        "session_id": "session-1",
        "title": "First conversation",
        "model": "auto",
        "messages": [
            {"id": "m1", "role": "user", "content": "Hello history"},
            {
                "id": "m2",
                "role": "assistant",
                "content": "Stored reply",
                "model": "auto",
                "tools_used": ["memory_search"],
            },
        ],
    }
    payload.update(overrides)
    return client.post("/api/history/sessions", headers=headers, json=payload)


def test_history_routes_require_authentication(client_and_fake):
    client, _fake = client_and_fake

    assert client.get("/api/history/sessions").status_code == 401
    assert client.post("/api/history/sessions", json={}).status_code == 401


def test_history_create_list_get_and_search(client_and_fake):
    client, _fake = client_and_fake

    created = _create_session(client)
    assert created.status_code == 201
    session = created.json()["session"]
    assert session["id"] == "session-1"
    assert session["title"] == "First conversation"
    assert [message["id"] for message in session["messages"]] == ["m1", "m2"]

    listed = client.get("/api/history/sessions", headers=AUTH_1)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    summary = listed.json()["sessions"][0]
    assert summary["id"] == "session-1"
    assert summary["message_count"] == 2
    assert summary["preview"] == "Stored reply"
    assert "messages" not in summary

    found = client.get("/api/history/sessions", headers=AUTH_1, params={"q": "stored"})
    assert found.status_code == 200
    assert [item["id"] for item in found.json()["sessions"]] == ["session-1"]

    fetched = client.get("/api/history/sessions/session-1", headers=AUTH_1)
    assert fetched.status_code == 200
    assert fetched.json()["session"]["messages"][1]["tools_used"] == ["memory_search"]


def test_history_append_is_idempotent_and_updates_model(client_and_fake):
    client, _fake = client_and_fake
    assert _create_session(client).status_code == 201

    response = client.post(
        "/api/history/sessions/session-1/messages",
        headers=AUTH_1,
        json={
            "model": "meta/llama-3.3-70b-instruct",
            "messages": [
                {"id": "m2", "role": "assistant", "content": "Duplicate must be ignored"},
                {"id": "m3", "role": "user", "content": "Follow up"},
            ],
        },
    )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["model"] == "meta/llama-3.3-70b-instruct"
    assert [message["id"] for message in session["messages"]] == ["m1", "m2", "m3"]
    assert session["messages"][1]["content"] == "Stored reply"


def test_history_append_auto_creates_first_turn(client_and_fake):
    client, _fake = client_and_fake

    response = client.post(
        "/api/history/sessions/fresh-from-ui/messages",
        headers=AUTH_1,
        json={
            "model": "auto",
            "messages": [{"id": "u1", "role": "user", "content": "A brand new question"}],
        },
    )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["id"] == "fresh-from-ui"
    assert session["title"] == "A brand new question"


def test_history_rename_delete_and_clear(client_and_fake):
    client, _fake = client_and_fake
    assert _create_session(client).status_code == 201
    assert _create_session(
        client,
        session_id="session-2",
        title="Second conversation",
        messages=[{"id": "x1", "role": "user", "content": "Another topic"}],
    ).status_code == 201

    renamed = client.patch(
        "/api/history/sessions/session-1",
        headers=AUTH_1,
        json={"title": "Renamed conversation"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["session"]["title"] == "Renamed conversation"

    deleted = client.delete("/api/history/sessions/session-2", headers=AUTH_1)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": "session-2"}
    assert client.get("/api/history/sessions/session-2", headers=AUTH_1).status_code == 404

    cleared = client.delete("/api/history/sessions", headers=AUTH_1)
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1
    assert client.get("/api/history/sessions", headers=AUTH_1).json()["count"] == 0


def test_history_is_owner_scoped(client_and_fake):
    client, _fake = client_and_fake
    assert _create_session(client).status_code == 201

    assert client.get("/api/history/sessions", headers=AUTH_2).json()["count"] == 0
    assert client.get("/api/history/sessions/session-1", headers=AUTH_2).status_code == 404
    assert client.patch(
        "/api/history/sessions/session-1",
        headers=AUTH_2,
        json={"title": "Hijacked"},
    ).status_code == 404
    assert client.delete("/api/history/sessions/session-1", headers=AUTH_2).status_code == 404
    assert client.post(
        "/api/history/sessions/session-1/messages",
        headers=AUTH_2,
        json={"messages": [{"id": "evil", "role": "user", "content": "Nope"}]},
    ).status_code == 404

    # A colliding client-supplied ID must not overwrite the original owner's
    # conversation; the second owner receives a distinct generated ID.
    collision = _create_session(client, headers=AUTH_2, title="Other owner copy")
    assert collision.status_code == 201
    assert collision.json()["session"]["id"] != "session-1"
    original = client.get("/api/history/sessions/session-1", headers=AUTH_1)
    assert original.json()["session"]["title"] == "First conversation"


def test_chat_history_store_persists_atomically_as_json(tmp_path):
    path = tmp_path / "chat_history.json"
    store = ChatHistoryStore(path=path)
    created = store.create_session(
        user_id="u1",
        tenant_id="t1",
        session_id="persisted",
        messages=[{"id": "m1", "role": "user", "content": "Remember me"}],
    )
    assert created["id"] == "persisted"
    assert path.exists()
    assert not (tmp_path / "chat_history.json.tmp").exists()

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["sessions"]["persisted"]["messages"][0]["content"] == "Remember me"

    reloaded = ChatHistoryStore(path=path)
    fetched = reloaded.get_session("persisted", "u1", "t1")
    assert fetched is not None
    assert fetched["title"] == "Remember me"
