"""Cockpit API tests — the full-stack contract behind ``frontend/workspace.html``.

Covers Screen 1 (bootstrap payload: identity, usage meters, feature matrix, route
catalog) and Screen 2 (runs, SSE frames that drive the THINKING/STREAMING aura,
procedural artifacts, cancel, replay and the plan catalog).

All runs are forced onto the offline engine so the suite never needs an LLM, and
streaming pace is zeroed for speed. Every assertion is on observable HTTP/SSE
behaviour — no reaching into private state beyond resetting the bounded stores.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["NEXUS_WORKSPACE_PACE"] = "0"
os.environ["NEXUS_WORKSPACE_ENGINE"] = "local"

from backend.main import app  # noqa: E402
from backend.routers import workspace as cockpit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client():
    cockpit.RUNS.clear()
    cockpit._AUDIO_CACHE.clear()
    cockpit._USAGE.update({"day": "", "runs": 0, "credits_spent": 0, "plan": "studio"})
    with TestClient(app) as test_client:
        yield test_client


def run_stream(client, run_id):
    """Drain an SSE endpoint into [(event, payload)]."""
    frames: list[tuple[str, dict]] = []
    with client.stream("GET", f"/api/workspace/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        event = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                frames.append((event, json.loads(line.split(":", 1)[1].strip())))
    return frames


def start_run(client, prompt="Explain quantum computing in simple terms", route="deep_research"):
    response = client.post("/api/workspace/runs", json={"prompt": prompt, "route": route})
    assert response.status_code == 201, response.text
    return response.json()


# ── Screen 1 ────────────────────────────────────────────────────────────────


class TestBootstrap:
    def test_payload_shape(self, client):
        payload = client.get("/api/workspace/bootstrap").json()
        assert payload["user"]["name"] == "Nixtio"
        assert payload["user"]["plan_label"] == "Studio"
        assert payload["greeting"]["bubble"] == "Hey there! Need a boost?"
        assert payload["greeting"]["title"].startswith("Hi ")
        assert len(payload["greeting"]["suggestions"]) >= 3
        assert payload["spaces"] == {
            "total": 10,
            "landed": 10,
            "pending": 0,
            "endpoint": "/api/workspace/spaces",
        }

    def test_feature_matrix_matches_the_three_cards(self, client):
        features = client.get("/api/workspace/bootstrap").json()["features"]
        assert [feature["id"] for feature in features] == ["fast_start", "collaborate", "planning"]
        for feature in features:
            assert feature["title"] and feature["caption"] and feature["metric"]
            assert 0 < feature["progress"] <= 1
            assert feature["items"]

    def test_route_catalog_is_the_four_chips(self, client):
        routes = client.get("/api/workspace/bootstrap").json()["routes"]
        assert [route["id"] for route in routes] == ["deep_research", "image", "search", "music"]
        assert [route["label"] for route in routes] == [
            "Deep Research",
            "Make an Image",
            "Search",
            "Create music",
        ]
        for route in routes:
            assert len(route["steps"]) >= 3
            assert route["hint"] and route["cost"] > 0

    def test_knowledge_index_reads_the_repository(self, client):
        knowledge = client.get("/api/workspace/bootstrap").json()["knowledge"]
        assert knowledge["passages"] > 100
        assert knowledge["documents"] >= 5

    def test_usage_envelope(self, client):
        usage = client.get("/api/workspace/bootstrap").json()["usage"]
        assert usage["credits_total"] == 1200
        assert usage["credits_left"] == 1200
        assert usage["plan"] == "studio"
        assert usage["window"]


class TestPlatformSpaces:
    def test_shared_catalog_is_served(self, client):
        payload = client.get("/api/workspace/spaces").json()
        assert payload["ok"] is True
        assert payload["summary"] == {"total": 10, "landed": 10, "pending": 0}
        assert payload["filtered_count"] == 10
        assert [space["id"] for space in payload["spaces"]] == list(range(1, 11))
        assert payload["source"] == "nexus.domain.value_objects.upgrade_spaces"
        for space in payload["spaces"]:
            assert space["status"] == "landed"
            assert space["summary"] and space["runtime_note"]
            assert space["evidence"]

    def test_search_matches_name_summary_and_evidence(self, client):
        by_name = client.get("/api/workspace/spaces", params={"q": "telemetry"}).json()
        assert by_name["filtered_count"] >= 1
        assert any("telemetry" in space["name"].lower() for space in by_name["spaces"])

        by_evidence = client.get("/api/workspace/spaces", params={"q": "agent_telemetry.py"}).json()
        assert by_evidence["filtered_count"] >= 1
        assert all(
            "agent_telemetry.py" in " ".join(space["evidence"]) for space in by_evidence["spaces"]
        )

    def test_priority_filter_and_validation(self, client):
        payload = client.get("/api/workspace/spaces", params={"priority": "p0"}).json()
        assert payload["priority"] == "P0"
        assert payload["spaces"]
        assert all(space["priority"] == "P0" for space in payload["spaces"])

        response = client.get("/api/workspace/spaces", params={"priority": "P9"})
        assert response.status_code == 400
        assert response.json()["priorities"]


# ── run validation ──────────────────────────────────────────────────────────


class TestRunValidation:
    def test_empty_prompt_is_rejected(self, client):
        response = client.post("/api/workspace/runs", json={"prompt": "   ", "route": "search"})
        assert response.status_code == 400
        assert "prompt" in response.json()["error"]

    def test_unknown_route_lists_the_valid_ones(self, client):
        response = client.post("/api/workspace/runs", json={"prompt": "hi", "route": "telepathy"})
        assert response.status_code == 400
        assert set(response.json()["routes"]) == {"deep_research", "image", "search", "music"}

    def test_oversized_prompt_is_rejected(self, client):
        response = client.post("/api/workspace/runs", json={"prompt": "x" * 4001, "route": "search"})
        assert response.status_code == 400

    def test_created_run_returns_a_stream_url_and_a_plan(self, client):
        body = start_run(client)
        assert body["ok"] is True
        assert body["stream"] == f"/api/workspace/runs/{body['run']['id']}/stream"
        assert body["run"]["status"] == "queued"
        assert len(body["plan"]) == 4

    def test_unknown_run_is_404(self, client):
        assert client.get("/api/workspace/runs/deadbeef").status_code == 404
        assert client.get("/api/workspace/runs/deadbeef/stream").status_code == 404
        assert client.post("/api/workspace/runs/deadbeef/cancel").status_code == 404
        assert client.get("/api/workspace/art/deadbeef.svg").status_code == 404
        assert client.get("/api/workspace/audio/deadbeef.wav").status_code == 404


# ── SSE lifecycle ───────────────────────────────────────────────────────────


class TestStreamLifecycle:
    @pytest.mark.parametrize("route", ["deep_research", "image", "search", "music"])
    def test_every_route_emits_the_full_frame_sequence(self, client, route):
        run_id = start_run(client, prompt="sandbox backend defaults", route=route)["run"]["id"]
        frames = run_stream(client, run_id)
        events = [event for event, _ in frames]

        # the aura contract: thinking first, streaming later, done last
        assert events[0] == "state"
        assert frames[0][1]["status"] == "thinking"
        assert frames[0][1]["label"] == "THINKING"
        assert "plan" in events
        assert frames[events.index("plan")][1]["steps"][0]["id"]

        streaming = [
            payload for event, payload in frames if event == "state" and payload["status"] == "streaming"
        ]
        assert streaming and streaming[0]["label"] == "STREAMING"
        assert events.index("state") < events.index("delta")
        assert events[-1] == "done"

        # step frames cover every plan step, each ending in "done"
        steps_done = {p["id"] for e, p in frames if e == "step" and p["status"] == "done"}
        plan_steps = {step["id"] for _, p in frames if _ == "plan" for step in p["steps"]}
        assert plan_steps == steps_done

        assert events.count("usage") == 1
        assert frames[-1][1]["run"]["status"] == "done"

    def test_deltas_reassemble_the_answer(self, client):
        run_id = start_run(client)["run"]["id"]
        frames = run_stream(client, run_id)
        streamed = "".join(p["text"] for event, p in frames if event == "delta")
        final = frames[-1][1]["run"]
        assert "Short answer" in streamed
        assert final["answer"].strip() == streamed.strip()

    def test_meta_reports_engine_and_latency(self, client):
        run_id = start_run(client)["run"]["id"]
        frames = run_stream(client, run_id)
        meta = next(p for event, p in frames if event == "meta")
        assert meta["engine"] in {"local-primer", "local-grounding", "llm"}
        assert meta["latency_ms"] >= 0
        assert meta["note"]

    def test_usage_meter_advances_with_runs(self, client):
        before = client.get("/api/workspace/bootstrap").json()["usage"]
        frames = run_stream(client, start_run(client, route="search")["run"]["id"])
        usage = next(p for event, p in frames if event == "usage")
        assert usage["runs_today"] == before["runs_today"] + 1
        assert usage["credits_left"] == before["credits_left"] - cockpit.ROUTES["search"]["cost"]

    def test_replay_is_idempotent(self, client):
        run_id = start_run(client)["run"]["id"]
        first = run_stream(client, run_id)
        second = run_stream(client, run_id)
        assert [event for event, _ in first] == [event for event, _ in second]
        assert first[-1][1]["run"]["id"] == second[-1][1]["run"]["id"]

    def test_cancel_stops_the_stream(self, client):
        run_id = start_run(client)["run"]["id"]
        assert client.post(f"/api/workspace/runs/{run_id}/cancel").json()["ok"] is True
        frames = run_stream(client, run_id)
        statuses = [p["status"] for event, p in frames if event == "state"]
        assert "cancelled" in statuses
        assert frames[-1][0] == "done"
        assert frames[-1][1]["run"]["status"] == "cancelled"
        # cancelling again is a no-op, not an error
        assert client.post(f"/api/workspace/runs/{run_id}/cancel").json()["ok"] is True


# ── deep research grounding ────────────────────────────────────────────────


class TestDeepResearch:
    def test_offline_answers_are_labelled_not_faked(self, client):
        frames = run_stream(client, start_run(client)["run"]["id"])
        meta = next(p for event, p in frames if event == "meta")
        artifacts = [p["artifact"] for event, p in frames if event == "artifact"]
        assert meta["engine"].startswith("local-")
        assert meta["model"] is None
        assert any(artifact["kind"] == "note" for artifact in artifacts)

    def test_grounded_answer_cites_source_paths(self, client):
        run_id = start_run(client, prompt="sandbox backend defaults")["run"]["id"]
        frames = run_stream(client, run_id)
        answer = frames[-1][1]["run"]["answer"]
        assert "**What holds up.**" in answer
        assert "docs/" in answer or "README.md" in answer
        evidence = [
            p["artifact"] for event, p in frames if event == "artifact" and p["artifact"]["kind"] == "source"
        ]
        assert evidence
        assert all(artifact["match"] >= 60 for artifact in evidence)

    def test_uncovered_question_does_not_invent_citations(self, client):
        run_id = start_run(client, prompt="zzzqqq flibbertigibbet nonsense")["run"]["id"]
        frames = run_stream(client, run_id)
        answer = frames[-1][1]["run"]["answer"]
        assert "outside the written record" in answer or "no passage" in answer.lower()

    def test_primer_cards_are_used_for_known_offline_topics(self, client):
        run_id = start_run(client)["run"]["id"]
        frames = run_stream(client, run_id)
        answer = frames[-1][1]["run"]["answer"]
        assert cockpit.PRIMERS["quantum"]["answer"] in answer
        assert "**What it isn't.**" in answer


# ── procedural artifacts ────────────────────────────────────────────────────


class TestArtifacts:
    def test_image_run_produces_a_downloadable_svg(self, client):
        run_id = start_run(client, prompt="a moody launch poster", route="image")["run"]["id"]
        frames = run_stream(client, run_id)
        artifacts = [p["artifact"] for event, p in frames if event == "artifact"]
        image = next(a for a in artifacts if a["kind"] == "image")
        assert image["url"] == f"/api/workspace/art/{run_id}.svg"

        response = client.get(image["url"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        body = response.text
        assert body.lstrip().startswith("<svg")
        assert 'width="1200"' in body and 'height="860"' in body
        assert "nexus-poster" in image["download"]

    def test_svg_is_deterministic_per_prompt(self, client):
        first = start_run(client, prompt="same prompt", route="image")["run"]["id"]
        second = start_run(client, prompt="same prompt", route="image")["run"]["id"]
        assert (
            client.get(f"/api/workspace/art/{first}.svg").text
            == client.get(f"/api/workspace/art/{second}.svg").text
        )

    def test_music_run_renders_a_real_wav(self, client):
        run_id = start_run(client, prompt="a calm ambient focus loop", route="music")["run"]["id"]
        frames = run_stream(client, run_id)
        audio = next(
            p["artifact"] for event, p in frames if event == "artifact" and p["artifact"]["kind"] == "audio"
        )
        assert audio["blueprint"]["mood"] == "weightless"

        response = client.get(audio["url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        header = response.content[:12]
        riff, _, wave = struct.unpack("<4sI4s", header)
        assert riff == b"RIFF" and wave == b"WAVE"
        assert 300_000 < len(response.content) < 400_000  # ~8s mono 22.05kHz 16-bit
        assert 'filename="nexus-stem-' in response.headers["content-disposition"]

    def test_search_returns_ranked_repository_sources(self, client):
        run_id = start_run(client, prompt="sandbox backend defaults", route="search")["run"]["id"]
        frames = run_stream(client, run_id)
        sources = [
            p["artifact"] for event, p in frames if event == "artifact" and p["artifact"]["kind"] == "source"
        ]
        assert sources
        assert all(source["subtitle"].endswith(".md") for source in sources)
        assert [source["match"] for source in sources] == sorted(
            (source["match"] for source in sources), reverse=True
        )

    def test_search_answer_counts_matches(self, client):
        run_id = start_run(client, prompt="sandbox backend defaults", route="search")["run"]["id"]
        answer = run_stream(client, run_id)[-1][1]["run"]["answer"]
        assert "passages" in answer and "matched" in answer


# ── misc surfaces ──────────────────────────────────────────────────────────


class TestSupportingSurfaces:
    def test_plans_and_upgrade_catalog(self, client):
        plans = client.get("/api/workspace/plans").json()
        assert [plan["id"] for plan in plans["plans"]] == ["free", "studio", "atlas"]
        assert plans["current"] == "studio"

        response = client.post("/api/workspace/upgrade", json={"plan": "atlas"})
        body = response.json()
        assert response.status_code == 200
        assert body["checkout"] == "not_configured"
        assert body["requested"] == "atlas"

        assert client.post("/api/workspace/upgrade", json={"plan": "platinum"}).status_code == 400

    def test_preview_state_describes_the_aura(self, client):
        thinking = client.get("/api/workspace/preview-state?state=thinking").json()
        assert thinking["aura"] is True
        assert thinking["label"] == "THINKING"
        assert thinking["layers"] == ["cyan", "violet"]
        assert client.get("/api/workspace/preview-state?state=idle").json()["aura"] is False
        assert client.get("/api/workspace/preview-state?state=chaos").status_code == 400

    def test_workspace_page_is_served(self, client):
        page = client.get("/workspace")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        html = page.text
        for landmark in (
            "Hi ",
            "Ready to Achieve Great Things?",
            "Hey there! Need a boost?",
            "Fast Start",
            "Collaborate with Team",
            "Planning",
            "Deep Research",
            "Make an Image",
            "Create music",
            "Platform Spaces",
            "Search the ten Nexus capability spaces",
            'id="spaces-search"',
            'id="spaces-priority"',
            "Jump to latest",
            "Example: 'Explain quantum computing in simple terms'",
        ):
            assert landmark in html, landmark
        # The dark Upgrade pill was intentionally removed from the product.
        assert "Upgrade" not in html, "Upgrade sign must not appear on the workspace page"

    def test_static_assets_are_served(self, client):
        for path in (
            "/workspace/workspace.css",
            "/workspace/app.js",
            "/workspace/robot.js",
            "/workspace/fonts/plus-jakarta-sans-latin-700-normal.woff2",
            "/assets/workspace/quantum-bloom.jpg",
        ):
            assert client.get(path).status_code == 200, path

    def test_run_history_lists_newest_first(self, client):
        first = start_run(client, prompt="first", route="search")["run"]["id"]
        run_stream(client, first)
        second = start_run(client, prompt="second", route="search")["run"]["id"]
        run_stream(client, second)
        runs = client.get("/api/workspace/runs").json()["runs"]
        assert runs[0]["id"] == second
        assert runs[1]["id"] == first


class TestLegacySurfaceContracts:
    def test_workspace_controller_uses_abortable_runs_and_shared_spaces(self):
        script = (ROOT / "frontend/workspace/app.js").read_text(encoding="utf-8")
        assert "/api/workspace/spaces" in script
        assert "signal: state.controller.signal" in script
        assert "event.keyCode !== 229" in script
        assert "safeArtifactUrl" in script
        assert "Intl.NumberFormat('en-IN')" in script
        assert "nexus-legacy-workspace-draft" in script

    def test_shared_voice_defaults_to_indian_english(self):
        voice = (ROOT / "frontend/shared/voice.js").read_text(encoding="utf-8")
        assert 'var LANGUAGE = "en-IN"' in voice
        assert "recognitionLanguage" in voice
        assert 'lang === "en-in"' in voice

    @pytest.mark.parametrize("page", ["frontend/chat.html", "frontend/index.html", "frontend/holo.html"])
    def test_legacy_chat_surfaces_are_cancellable_ime_safe_and_en_in(self, page):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert "AbortController" in html
        assert "keyCode !== 229" in html
        assert "en-IN" in html
        assert "lang = 'en-US'" not in html
        assert "â" not in html
        assert "/workspace#spaces" in html

    def test_static_dashboard_keeps_key_session_only_and_renders_spaces(self):
        html = (ROOT / "src/nexus/infrastructure/api/static/dashboard.html").read_text(encoding="utf-8")
        assert "sessionStorage.getItem('nexus_api_key')" in html
        assert "localStorage.setItem('nexus_api_key'" not in html
        assert "/api/system/upgrade-spaces" in html
        assert "renderList" in html
        assert "list.innerHTML = tools.map" not in html
