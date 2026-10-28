"""Hermetic tests for the real-task RL training runner.

The LLM is faked; the subprocess verification is REAL (actual code written to
a temp workspace and executed), so objective scoring is exercised end-to-end.
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


@pytest.fixture(scope="module")
def tt():
    spec = importlib.util.spec_from_file_location(
        "nexus_task_training", REPO_ROOT / "backend" / "services" / "task_training.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nexus_task_training"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def isolated(be, tt, monkeypatch, tmp_path):
    """Fresh reward store + fresh exemplar file + reset blackboard."""
    monkeypatch.setattr(be.training_service, "RL_STATE", {"pairs": [], "daily": {}})
    examples = tmp_path / "coding_examples.json"
    monkeypatch.setattr(be.training_service, "EXAMPLES_PATH", examples)
    monkeypatch.setattr(be.tools_service, "TOOL_BLACKBOARD", {})
    return examples


class TestCorpus:
    def test_10_tasks_unique_with_verify(self, tt):
        ids = [t["id"] for t in tt.TASK_CORPUS]
        assert len(ids) == len(set(ids)) == 10
        for task in tt.TASK_CORPUS:
            assert task["filename"].endswith(".py")
            assert "print('VERIFY PASS')" in task["verify"]
            assert len(task["rubric"]) >= 3

    def test_categories(self, tt):
        cats = {t["category"] for t in tt.TASK_CORPUS}
        assert {"coding", "debugging"} <= cats


class TestCodeExtraction:
    def test_fenced_block(self, tt):
        assert tt._extract_code("```python\ndef f():\n    pass\n```") == "def f():\n    pass"

    def test_bare_code(self, tt):
        assert "def f()" in tt._extract_code("def f():\n    pass")

    def test_no_code_returns_empty(self, tt):
        assert tt._extract_code("Sorry, I cannot help with that.") == ""


class TestObjectiveVerification:
    def test_passing_code_scores_10(self, tt, tmp_path):
        (tmp_path / "dedupe.py").write_text(
            "def dedupe(items):\n    return list(dict.fromkeys(items))\n", encoding="utf-8"
        )
        passed, output = tt._run_verify(
            tmp_path,
            next(t["verify"] for t in tt.TASK_CORPUS if t["id"] == "code-dedupe"),
        )
        assert passed is True
        assert "VERIFY PASS" in output

    def test_broken_code_fails(self, tt, tmp_path):
        (tmp_path / "dedupe.py").write_text("def dedupe(items):\n    return items\n", encoding="utf-8")
        passed, output = tt._run_verify(
            tmp_path,
            next(t["verify"] for t in tt.TASK_CORPUS if t["id"] == "code-dedupe"),
        )
        assert passed is False
        assert "AssertionError" in output


class TestTaskRound:
    @pytest.mark.asyncio
    async def test_first_try_pass_full_reward(self, tt, be, monkeypatch, tmp_path, isolated):
        good = "def dedupe(items):\n    return list(dict.fromkeys(items))\n"

        async def fake_llm(system, messages):
            return "```python\n" + good + "\n```", ""

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)

        result = await tt.run_task_round(1)
        assert result["trained"] == 1
        r = result["results"][0]
        assert r["id"] == "code-dedupe" and r["passed"] is True and r["score"] == 10.0
        assert result["exemplars_stored"] == 1
        assert isolated.is_file() and "dict.fromkeys" in isolated.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_repair_round_after_failure(self, tt, be, monkeypatch, tmp_path, isolated):
        replies = [
            "```python\ndef dedupe(items):\n    return []\n```",
            "```python\ndef dedupe(items):\n    return list(dict.fromkeys(items))\n```",
        ]

        async def fake_llm(system, messages):
            r0 = replies.pop(0) if replies else ("```python\npass\n```", "")
            return (r0, "")

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)

        result = await tt.run_task_round(1, repair=True)
        r = result["results"][0]
        assert r["passed"] is True
        assert r["attempts"] == 2
        assert r["score"] == 7.5

    @pytest.mark.asyncio
    async def test_total_failure_scores_3(self, tt, be, monkeypatch, tmp_path, isolated):
        async def fake_llm(system, messages):
            return "```python\nraise SystemExit(1)\n```", ""

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)
        result = await tt.run_task_round(1, repair=False)
        r = result["results"][0]
        assert r["passed"] is False and r["score"] == 3.0

    @pytest.mark.asyncio
    async def test_scored_tasks_are_skipped(self, tt, be, monkeypatch, tmp_path, isolated):
        monkeypatch.setattr(
            be.training_service,
            "RL_STATE",
            {"pairs": [{"q": tt.TASK_CORPUS[0]["instruction"]}], "daily": {}},
        )
        calls = []

        async def fake_llm(system, messages):
            calls.append(1)
            return "```python\npass\n```", ""

        monkeypatch.setattr(be.llm_service, "_call_llm", fake_llm)
        result = await tt.run_task_round(1, repair=False)
        assert result["trained"] == 1, "only the 2nd task should run; the scored one is skipped"
        assert len(calls) == 1
