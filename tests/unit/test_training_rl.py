"""Hermetic tests for the cosmos RL training loop (corpus, judge, rewards).

The backend module is loaded by file path; every LLM touchpoint is
monkeypatched so these tests never hit the network.
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


class TestCorpus:
    def test_unique_ids_and_shape(self, be):
        ids = [item["id"] for item in be.TRAINING_CORPUS]
        assert len(ids) == len(set(ids)), "corpus ids must be unique"
        for item in be.TRAINING_CORPUS:
            assert item["q"] and len(item["q"]) > 40
            assert len(item["rubric"]) >= 3, "every hard question needs a rubric"
            assert item["category"]

    def test_hard_gil_question_present(self, be):
        assert any(item["id"] == "gil-py313" for item in be.TRAINING_CORPUS)

    def test_bat_ball_rubric_covers_trap(self, be):
        item = next(i for i in be.TRAINING_CORPUS if i["id"] == "bat-ball")
        assert any("0.05" in r for r in item["rubric"])


class TestJudge:
    @pytest.mark.asyncio
    async def test_parses_llm_score(self, be, monkeypatch):
        async def fake_llm(system, messages):
            return "SCORE: 8.5\nCRITIQUE: covers the rubric well", ""

        monkeypatch.setattr(be, "_call_llm", fake_llm)
        verdict = await be._judge_answer("q", "a" * 80, ["point one", "point two"])
        assert verdict["score"] == 8.5
        assert verdict["judge"] == "llm"
        assert "rubric" in verdict["critique"]

    @pytest.mark.asyncio
    async def test_clamps_out_of_range_score(self, be, monkeypatch):
        async def fake_llm(system, messages):
            return "SCORE: 42\nCRITIQUE: overconfident", ""

        monkeypatch.setattr(be, "_call_llm", fake_llm)
        verdict = await be._judge_answer("q", "a", ["p"])
        assert verdict["score"] == 10.0

    @pytest.mark.asyncio
    async def test_heuristic_fallback_when_judge_down(self, be, monkeypatch):
        async def broken_llm(system, messages):
            raise RuntimeError("LLM offline")

        monkeypatch.setattr(be, "_call_llm", broken_llm)
        verdict = await be._judge_answer("q", "word " * 100, ["p"])
        assert verdict["judge"] == "heuristic"
        assert verdict["score"] > 3.0


class TestExemplars:
    def test_only_high_scores_with_overlap(self, be, monkeypatch):
        monkeypatch.setattr(
            be,
            "RL_STATE",
            {
                "pairs": [
                    {"q": "how does the gil change threading", "score": 9.5, "a": "x"},
                    {"q": "unrelated query about cooking pasta", "score": 9.8, "a": "y"},
                    {"q": "how does the gil change threading", "score": 6.0, "a": "z"},
                ],
                "daily": {},
            },
        )
        picks = be._pick_exemplars("explain the gil threading change in python")
        assert len(picks) == 1
        assert picks[0]["score"] == 9.5

    def test_empty_when_no_pairs(self, be, monkeypatch):
        monkeypatch.setattr(be, "RL_STATE", {"pairs": [], "daily": {}})
        assert be._pick_exemplars("anything") == []


class TestRewardStore:
    def test_record_pair_updates_daily_log(self, be, monkeypatch, tmp_path):
        path = tmp_path / "rl_state.json"
        monkeypatch.setattr(be, "RL_STATE_PATH", path)
        monkeypatch.setattr(be, "RL_STATE", {"pairs": [], "daily": {}})

        entry = be._record_training_pair("q?", "a" * 60, 7.5, "decent", "test", "m1")
        assert entry["score"] == 7.5
        assert path.is_file(), "state must persist"
        saved = path.read_text(encoding="utf-8")
        assert "rl" in saved or "score" in saved
        assert len(be.RL_STATE["pairs"]) == 1
        today = entry["ts"][:10]
        assert be.RL_STATE["daily"][today]["count"] == 1
