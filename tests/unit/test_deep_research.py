"""Hermetic tests for the research-and-train pipeline (Upgrade batch).

deep_research, extract_examples, and the new endpoints are covered without
network or LLM access: every external touchpoint is monkeypatched.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def be():
    spec = importlib.util.spec_from_file_location("nexus_cosmos_backend", REPO_ROOT / "backend" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nexus_cosmos_backend"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestDeepResearch:
    @pytest.mark.asyncio
    async def test_roundtrip_writes_note_and_reports(self, be, monkeypatch, tmp_path):
        """Sub-queries are parsed, sources fetched, note saved, index fired."""
        monkeypatch.setattr(be.tools_service, "ROOT_DIR", tmp_path)
        calls = {"llm": 0, "fetch": 0, "index": 0}

        async def fake_llm(system, messages):
            calls["llm"] += 1
            if "research planner" in system:
                return '["sub-question one?", "sub-question two?"]', ""
            return "# Synthesized Research\n\nKey findings:\n- answer", ""

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)
        monkeypatch.setattr(
            be.tools_service,
            "_fetch_reader_text",
            lambda url, timeout=25.0: ("excerpt about " + url) or calls.__setitem__("fetch", 1),
        )
        monkeypatch.setattr(
            be.tools_service, "_trigger_indexer", lambda: calls.__setitem__("index", 1) or True
        )

        result = await be.tools_service.deep_research(
            "How does uvicorn graceful shutdown work? https://example.com/shutdown"
        )
        assert result["ok"] is True
        assert result["sub_queries"] == ["sub-question one?", "sub-question two?"]
        assert result["sources"] == ["https://example.com/shutdown"]
        assert result["indexed"] is True
        note = tmp_path / result["note_path"]
        assert note.is_file()
        assert "Synthesized Research" in note.read_text(encoding="utf-8")
        assert calls["index"] == 1

    @pytest.mark.asyncio
    async def test_synthesis_failure_is_reported(self, be, monkeypatch, tmp_path):
        monkeypatch.setattr(be.tools_service, "ROOT_DIR", tmp_path)

        async def broken_llm(system, messages):
            raise RuntimeError("LLM offline")

        monkeypatch.setattr(be.llm_service, "_call_llm", broken_llm)
        result = await be.tools_service.deep_research("anything at all")
        assert result["ok"] is False
        assert "synthesis failed" in result["error"]


class TestExtractExamples:
    @pytest.mark.asyncio
    async def test_extracts_and_dedups(self, be, monkeypatch, tmp_path):
        examples_path = tmp_path / "coding_examples.json"
        monkeypatch.setattr(be.training_service, "EXAMPLES_PATH", examples_path)

        notes_dir = tmp_path / "docs" / "notes"
        notes_dir.mkdir(parents=True)
        (notes_dir / "research-test.md").write_text(
            "# Research: pytest patterns\n\nUse fixtures.", encoding="utf-8"
        )
        monkeypatch.setattr(be.training_service, "ROOT_DIR", tmp_path)

        payload = (
            '[{"instruction": "Write a fixture", "input": "tmp_path", '
            '"output": "def test_x(tmp_path): pass"}]'
        )

        async def fake_llm(system, messages):
            return payload, ""

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)

        first = await be.training_service.extract_examples()
        assert first["ok"] is True and first["added"] == 1
        assert examples_path.is_file()

        second = await be.training_service.extract_examples()
        assert second["added"] == 0, "identical instruction must be deduplicated"

    @pytest.mark.asyncio
    async def test_no_notes_reported_cleanly(self, be, monkeypatch, tmp_path):
        monkeypatch.setattr(be.training_service, "ROOT_DIR", tmp_path)
        result = await be.training_service.extract_examples()
        assert result["ok"] is False and "no research notes" in result["error"]


class TestNewEndpoints:
    def test_holo_props_lists_glb(self, be):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        client = TestClient(be.app)
        resp = client.get("/api/holo/props")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert all(p["url"].startswith("/props/") for p in data["props"])

    @pytest.mark.asyncio
    async def test_research_endpoint_routes_through_service(self, be, monkeypatch):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        async def fake_research(query, max_depth=3):
            return {"ok": True, "note_path": "docs/notes/fake.md", "summary": "done"}

        monkeypatch.setattr(be.tools_service, "deep_research", fake_research)
        client = TestClient(be.app)
        resp = client.post("/api/research", json={"query": "test anything"})
        assert resp.status_code == 200
        assert resp.json()["note_path"] == "docs/notes/fake.md"
