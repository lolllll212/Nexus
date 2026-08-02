"""
Multi-modal tests (Phase 3, Priority 3).

Covers vision + audio I/O against fakes:
  - image_urls -> OpenAI vision content blocks reach the LLM
  - audio (base64 data URI) -> transcribed and used as the user message
  - voice -> response synthesized to an audio data URI
  - data URI helpers, _attach_images, and auth gating on /v1/chat
"""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.api.routes.chat import _parse_data_uri, _to_data_uri

from tests.fakes.container import FakeContainer, TEST_API_KEY_1

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}


class RecordingLLM:
    """Captures every complete() call so tests can assert message shape."""

    def __init__(self, response: str = "FINAL ANSWER: ok"):
        self.calls = []
        self._response = response

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(messages)
        return self._response

    async def extract_structured(self, content, schema, instructions=""):
        return {}


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _inject(client, app, llm=None):
    fake = FakeContainer()
    if llm is not None:
        fake.llm = llm
        fake.process_message._llm = llm
    app.state.container = fake
    client.app.state.container = fake
    return fake


def _user_contents(calls):
    return [
        m["content"]
        for msgs in calls
        for m in msgs
        if m.get("role") == "user"
    ]


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #


def test_data_uri_roundtrip():
    payload = b"\x00\x01\x02audio"
    uri = _to_data_uri(payload, "audio/mpeg")
    assert uri.startswith("data:audio/mpeg;base64,")
    mime, decoded = _parse_data_uri(uri)
    assert mime == "audio/mpeg"
    assert decoded == payload


def test_parse_data_uri_default_mime():
    uri = "data:;base64," + base64.b64encode(b"x").decode()
    mime, _ = _parse_data_uri(uri)
    assert mime == "audio/mpeg"


def test_attach_images_converts_last_user_message():
    use_case = _make_process_message()
    ctx = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "what is this?"},
    ]
    out = use_case._attach_images(ctx, ["https://x.test/a.png", "https://x.test/b.png"])
    user = out[1]
    assert isinstance(user["content"], list)
    assert user["content"][0] == {"type": "text", "text": "what is this?"}
    assert user["content"][1] == {"type": "image_url", "image_url": {"url": "https://x.test/a.png"}}
    assert user["content"][2] == {"type": "image_url", "image_url": {"url": "https://x.test/b.png"}}


def _make_process_message() -> ProcessMessageUseCase:
    fake = FakeContainer()
    return fake.process_message


# --------------------------------------------------------------------------- #
#  Vision
# --------------------------------------------------------------------------- #


def test_chat_passes_images_as_content_blocks(app, client):
    llm = RecordingLLM()
    _inject(client, app, llm=llm)
    r = client.post(
        "/v1/chat",
        json={
            "message": "describe this screenshot",
            "session_id": "s1",
            "image_urls": ["https://x.test/shot.png"],
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert any(
        isinstance(content, list)
        and any(p.get("type") == "image_url" and p["image_url"]["url"] == "https://x.test/shot.png" for p in content)
        for content in _user_contents(llm.calls)
    )


# --------------------------------------------------------------------------- #
#  Audio input (STT)
# --------------------------------------------------------------------------- #


def test_chat_transcribes_audio_when_no_text(app, client):
    llm = RecordingLLM(response="FINAL ANSWER: got it")
    fake = _inject(client, app, llm=llm)
    uri = _to_data_uri(b"encoded-wave", "audio/mpeg")
    r = client.post("/v1/chat", json={"message": "", "session_id": "s1", "audio": uri}, headers=AUTH)
    assert r.status_code == 200
    assert fake.speech_to_text.calls[0]["mime"] == "audio/mpeg"
    assert fake.speech_to_text.calls[0]["bytes"] == b"encoded-wave"
    assert any("transcribed audio text" in str(content) for content in _user_contents(llm.calls))


def test_chat_audio_prepended_to_text(app, client):
    llm = RecordingLLM(response="FINAL ANSWER: ok")
    _inject(client, app, llm=llm)
    uri = _to_data_uri(b"encoded-wave", "audio/wav")
    r = client.post(
        "/v1/chat",
        json={"message": "and now analyze", "session_id": "s1", "audio": uri},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert any("transcribed audio text" in str(content) and "and now analyze" in str(content) for content in _user_contents(llm.calls))


def test_audio_requires_valid_data_uri(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/chat",
        json={"message": "", "session_id": "s1", "audio": "data:audio/mpeg;base64,!!!"},
        headers=AUTH,
    )
    assert r.status_code == 400


def test_empty_chat_rejected(app, client):
    _inject(client, app)
    r = client.post("/v1/chat", json={"message": "", "session_id": "s1"}, headers=AUTH)
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
#  Audio output (TTS)
# --------------------------------------------------------------------------- #


def test_chat_synthesizes_response_audio(app, client):
    fake = _inject(client, app, llm=RecordingLLM(response="FINAL ANSWER: hello there"))
    r = client.post(
        "/v1/chat",
        json={"message": "say hi", "session_id": "s1", "voice": "nova"},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["audio"].startswith("data:audio/mpeg;base64,")
    assert fake.text_to_speech.calls[0]["voice"] == "nova"
    assert fake.text_to_speech.calls[0]["text"] == "hello there"


def test_chat_without_voice_has_no_audio(app, client):
    _inject(client, app)
    r = client.post("/v1/chat", json={"message": "hi", "session_id": "s1"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["audio"] is None


# --------------------------------------------------------------------------- #
#  Auth + gating
# --------------------------------------------------------------------------- #


def test_multimodal_chat_requires_auth(app, client):
    _inject(client, app)
    r = client.post(
        "/v1/chat",
        json={"message": "hi", "audio": _to_data_uri(b"x", "audio/mpeg")},
    )
    assert r.status_code == 401
