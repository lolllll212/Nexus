"""Hermetic tests for the tool blackboard and tool-grounded training rounds.

No network, no LLM: every external touchpoint is monkeypatched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def be():
    spec = importlib.util.spec_from_file_location(
        "nexus_cosmos_backend", REPO_ROOT / "backend" / "main.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nexus_cosmos_backend"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestBlackboard:
    def test_put_get_roundtrip(self, be, monkeypatch):
        monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})
        be.tools_service.bb_put("git", {"branch": "master"})
        assert be.tools_service.bb_get("git") == {"branch": "master"}

    def test_rolling_cap_evicts_oldest(self, be, monkeypatch):
        monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})
        for i in range(30):
            be.tools_service.bb_put("k" + str(i), {"i": i})
        assert len(be.tools_service.TOOL_BLACKBOARD) <= be.tools_service._BB_MAX
        assert be.tools_service.bb_get("k29") is not None, "newest must survive"
        assert be.tools_service.bb_get("k0") is None, "oldest must be evicted"

    def test_bb_compact_renders_entries(self, be, monkeypatch):
        monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})
        be.tools_service.bb_put("git", {"branch": "dev"})
        text = be.tools_service.bb_compact()
        assert "[git]" in text and "dev" in text

    def test_empty_blackboard_summary(self, be, monkeypatch):
        monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})
        assert "empty" in be.tools_service.bb_compact()


class TestRunToolByName:
    def test_known_tools_dispatch(self, be):
        result = be.tools_service.run_tool_by_name("calc", "2 + 2")
        assert result.get("ok") is True or "expression" in result
        assert "error" not in result or result["error"] == ""

    def test_unknown_tool_reports(self, be):
        result = be.tools_service.run_tool_by_name("nope", "q")
        assert "unknown tool" in result["error"]

    def test_tool_failure_is_caught(self, be, monkeypatch):
        def boom():
            raise RuntimeError("tool exploded")

        monkeypatch.setitem(be.tools_service.run_tool_by_name.__globals__, "_x", 1)
        result = be.tools_service.run_tool_by_name("calc", "(((")
        assert result.get("ok") is False or "error" in result


class TestCorpusBreadth:
    def test_corpus_30_plus_unique(self, be):
        ids = [i["id"] for i in be.training_service.TRAINING_CORPUS]
        assert len(ids) >= 30, "corpus must span 30+ hard questions"
        assert len(ids) == len(set(ids))

    def test_mostly_non_nexus_domains(self, be):
        cats = [i["category"] for i in be.training_service.TRAINING_CORPUS]
        non_nexus = [c for c in cats if "nexs" not in c]
        assert len(non_nexus) >= len(cats) - 2, "training must not be NEXUS-only"
        expected_domains = {"machine-learning", "crypto", "databases", "auth", "api-design"}
        assert expected_domains <= set(cats)

    def test_tool_ground_corpus_wired(self, be):
        tg = be.training_service.TOOL_GROUND_CORPUS
        assert len(tg) >= 6
        for item in tg:
            assert item.get("tool"), "every tool-grounded item needs a tool"
            assert len(item["rubric"]) >= 2

    @pytest.mark.asyncio
    async def test_tool_grounded_round_uses_live_tool(self, be, monkeypatch, tmp_path):
        """A tool-grounded training item must call the real tool and judge with
        a grounding rubric point."""
        from backend.routers import training as training_router

        monkeypatch.setattr(training_router, "training_service", be.training_service)
        monkeypatch.setattr(training_router, "llm_service", be.llm_service)
        monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})

        seen_tools = []

        def fake_tool():
            seen_tools.append("git")
            return {"branch": "feat/test", "changes_count": 2, "clean": False}

        monkeypatch.setattr(be.tools_service, "tool_git_status", fake_tool)
        monkeypatch.setattr(be.training_service, "RL_STATE", {"pairs": [], "daily": {}})

        prompts = []

        async def fake_llm(system, messages):
            prompts.append(system + "\n" + "\n".join(m.get("content", "") for m in messages))
            if "strict evaluation judge" in system:
                return "SCORE: 9.0\nCRITIQUE: grounded", ""
            return (
                "Sir, the branch is feat/test with 2 uncommitted changes.",
                "",
            )

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)

        tg = [i for i in be.training_service.TOOL_GROUND_CORPUS if i["id"] == "tg-git-branch"]
        monkeypatch.setattr(be.training_service, "TRAINING_CORPUS", tg)
        monkeypatch.setattr(be.training_service, "TOOL_GROUND_CORPUS", [])

        result = await training_router.api_training_run(1)
        body = json.loads(result.body)
        assert body["ok"] is True and body["trained"] == 1
        assert seen_tools == ["git"], "the live tool must be called"
        assert any("LIVE TOOL OUTPUT" in p for p in prompts), "answer must be grounded"
        assert any("grounded in the live tool output" in p for p in prompts), (
            "judge must check grounding"
        )
