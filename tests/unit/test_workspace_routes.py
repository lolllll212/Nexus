"""
Workspace API route tests — prove the light-mode NEXUS OS workspace surface
is a thin, fully-wired adapter:

  * GET  /api/workspace/bootstrap — live greeting, hero, cards & telemetry.
  * POST /api/workspace/search    — unified multi-modal retrieval.
  * POST /api/workspace/image     — deterministic procedural art synthesis.
  * POST /api/workspace/music     — deterministic WAV synthesis.

Runs with zero external infra via the FakeContainer composition root.
"""

import base64
import sys
import wave
import io
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.infrastructure.api.main import create_app
from tests.fakes.container import TEST_API_KEY_1, FakeContainer

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}


def make_memory(content: str, memory_type: str = "semantic") -> Memory:
    return Memory(content=content, memory_type=MemoryType(memory_type))


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def fake(client, app):
    fake = FakeContainer()
    app.state.container = fake
    client.app.state.container = fake
    return fake


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/workspace/bootstrap
# ─────────────────────────────────────────────────────────────────────────────


def test_bootstrap_returns_greeting_hero_and_cards(client, fake):
    resp = client.get("/api/workspace/bootstrap", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    # Greeting is personalised from the authenticated identity.
    assert data["greeting"]["headline"].startswith("Hi ")
    assert "Ready to Achieve Great Things?" in data["greeting"]["headline"]
    # Hero companion + onboarding message.
    assert data["hero"]["message"] == "Hey there! Need a boost?"
    assert data["hero"]["companion"]
    assert len(data["hero"]["suggestions"]) >= 2
    # Feature matrix: the three dashboard cards.
    titles = [c["title"] for c in data["cards"]]
    assert titles == ["Fast Start", "Collaborate with Team", "Planning"]
    accents = [c["accent"] for c in data["cards"]]
    assert accents == ["orange", "multicolor", "blue"]


def test_bootstrap_reports_builtin_roster_when_swarm_empty(client, fake):
    resp = client.get("/api/workspace/bootstrap", headers=AUTH)
    data = resp.json()
    assert data["telemetry"]["agents_online"] == 10
    names = [a["name"] for a in data["telemetry"]["agents"]]
    assert "Researcher" in names and "Fact Checker" in names


def test_bootstrap_requires_auth(client, fake):
    resp = client.get("/api/workspace/bootstrap")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/workspace/search
# ─────────────────────────────────────────────────────────────────────────────


def test_search_merges_memory_hits(client, fake):
    import asyncio

    mem = make_memory("Quantum computing uses qubits that superpose zero and one", memory_type="semantic")
    # Store through the repo so the fake's tenant index is populated (tenant t1
    # belongs to TEST_API_KEY_1).
    asyncio.run(fake.memory_repo.store(mem, tenant_id="t1"))

    resp = client.post("/api/workspace/search", headers=AUTH, json={"query": "quantum computing", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["scanned_sources"] >= 1
    memory_hits = [r for r in data["results"] if r["source"] == "memory"]
    assert memory_hits, "expected at least one memory hit"
    assert memory_hits[0]["score"] > 0


def test_search_rejects_empty_query(client, fake):
    resp = client.post("/api/workspace/search", headers=AUTH, json={"query": "   "})
    assert resp.status_code == 400


def test_search_respects_limit(client, fake):
    import asyncio

    for i in range(6):
        asyncio.run(fake.memory_repo.store(make_memory(f"quantum note number {i}"), tenant_id="t1"))
    resp = client.post("/api/workspace/search", headers=AUTH, json={"query": "quantum", "limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/workspace/image
# ─────────────────────────────────────────────────────────────────────────────


def test_image_returns_valid_deterministic_svg(client, fake):
    payload = {"prompt": "Aurora over a neural skyline", "style": "aurora"}
    resp = client.post("/api/workspace/image", headers=AUTH, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["style"] == "aurora"
    assert len(data["palette"]) == 4
    assert data["svg_data_uri"].startswith("data:image/svg+xml;base64,")

    svg = base64.b64decode(data["svg_data_uri"].split(",", 1)[1]).decode("utf-8")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg

    # Determinism: same prompt + style ⇒ same seed & same artwork.
    resp2 = client.post("/api/workspace/image", headers=AUTH, json=payload)
    assert resp2.json()["seed"] == data["seed"]
    assert resp2.json()["svg_data_uri"] == data["svg_data_uri"]


def test_image_palette_follows_prompt_keywords(client, fake):
    resp = client.post("/api/workspace/image", headers=AUTH, json={"prompt": "sunset over the desert dunes"})
    palette = resp.json()["palette"]
    assert "#FF7A59" in palette  # sunset palette


def test_image_rejects_empty_prompt(client, fake):
    resp = client.post("/api/workspace/image", headers=AUTH, json={"prompt": ""})
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/workspace/music
# ─────────────────────────────────────────────────────────────────────────────


def test_music_returns_playable_wav(client, fake):
    resp = client.post(
        "/api/workspace/music", headers=AUTH, json={"prompt": "dreamy focus track", "duration_seconds": 6, "tempo": 100}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["tempo"] == 100
    assert data["key"] in {"C", "D", "E", "F", "G", "A", "B"}
    assert data["scale"]
    assert data["notes_rendered"] > 0
    assert data["audio_data_uri"].startswith("data:audio/wav;base64,")

    wav_bytes = base64.b64decode(data["audio_data_uri"].split(",", 1)[1])
    assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 22050
        # Honours the requested duration (±0.5s).
        assert abs(wav_file.getnframes() / 22050 - 6.0) < 0.5


def test_music_is_deterministic_for_same_prompt(client, fake):
    payload = {"prompt": "epic cinematic battle theme", "duration_seconds": 5, "tempo": 120}
    r1 = client.post("/api/workspace/music", headers=AUTH, json=payload).json()
    r2 = client.post("/api/workspace/music", headers=AUTH, json=payload).json()
    assert r1["seed"] == r2["seed"]
    assert r1["audio_data_uri"] == r2["audio_data_uri"]


def test_music_rejects_empty_prompt(client, fake):
    resp = client.post("/api/workspace/music", headers=AUTH, json={"prompt": "  "})
    assert resp.status_code == 400
