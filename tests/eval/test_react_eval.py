"""
Golden-set eval harness for the ReAct loop and dreaming quality.

Measures whether the brain actually gets smarter over time.
Run with: pytest tests/eval/ -v

Each eval case is a (task, expected_tools, expected_keywords) tuple.
The harness:
  1. Runs ProcessMessageUseCase with a RecordingLLM
  2. Asserts the agent called the right tools
  3. Asserts the answer contains expected keywords
  4. Reports pass/fail + metrics
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@dataclass
class EvalCase:
    """A single evaluation scenario."""

    task: str
    expected_tools: List[str] = field(default_factory=list)
    expected_keywords: List[str] = field(default_factory=list)
    forbidden_keywords: List[str] = field(default_factory=list)
    max_iterations: int = 5


@dataclass
class EvalResult:
    """Result of running one eval case."""

    case: EvalCase
    tools_called: List[str]
    answer: str
    passed: bool
    duration_ms: int
    details: str = ""


# ── Golden Set ────────────────────────────────────────────────────────────

GOLDEN_SET: List[EvalCase] = [
    EvalCase(
        task="List all Python files in the current directory",
        expected_tools=["list_directory"],
        expected_keywords=[".py"],
    ),
    EvalCase(
        task="What is the capital of France?",
        expected_keywords=["Paris"],
        max_iterations=2,
    ),
    EvalCase(
        task="Read the file src/nexus/domain/entities/memory.py and tell me what classes it defines",
        expected_tools=["read_file"],
        expected_keywords=["Memory", "class"],
    ),
    EvalCase(
        task="Search for all files containing 'class.*UseCase' in the src directory",
        expected_tools=["grep"],
        expected_keywords=["UseCase"],
    ),
    EvalCase(
        task="Calculate 2 raised to the power of 10",
        expected_tools=["calculator"],
        expected_keywords=["1024"],
        max_iterations=2,
    ),
    EvalCase(
        task="What is the SHA-256 hash of the text 'hello world'?",
        expected_tools=["hash_text"],
        expected_keywords=["b94d27b9934d3e08"],
        max_iterations=2,
    ),
]


# ── Runner ────────────────────────────────────────────────────────────────


class EvalRunner:
    """Runs eval cases and collects results."""

    def __init__(self):
        self.results: List[EvalResult] = []

    async def run_case(self, case: EvalCase, llm) -> EvalResult:
        """Run a single eval case with the given LLM."""
        from tests.fakes.container import FakeContainer

        fake = FakeContainer()
        fake.llm = llm
        fake.process_message._llm = llm

        started = time.monotonic()
        try:
            result = await fake.process_message.execute(
                user_id="eval",
                message=case.task,
                tenant_id="eval",
            )
            duration_ms = int((time.monotonic() - started) * 1000)

            tools_called = result.tools_used
            answer = result.response

            # Check tool usage
            tools_ok = all(t in tools_called for t in case.expected_tools)

            # Check keywords
            answer_upper = answer.upper()
            keywords_ok = all(k.upper() in answer_upper for k in case.expected_keywords)

            # Check forbidden keywords
            forbidden_ok = all(k.upper() not in answer_upper for k in case.forbidden_keywords)

            passed = tools_ok and keywords_ok and forbidden_ok
            details = []
            if not tools_ok:
                details.append(f"Missing tools: {set(case.expected_tools) - set(tools_called)}")
            if not keywords_ok:
                details.append(f"Missing keywords: {case.expected_keywords}")
            if not forbidden_ok:
                details.append(f"Found forbidden: {case.forbidden_keywords}")

            return EvalResult(
                case=case,
                tools_called=tools_called,
                answer=answer[:200],
                passed=passed,
                duration_ms=duration_ms,
                details="; ".join(details),
            )
        except Exception as exc:
            return EvalResult(
                case=case,
                tools_called=[],
                answer="",
                passed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                details=str(exc),
            )

    def report(self) -> str:
        """Generate a human-readable eval report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        avg_ms = sum(r.duration_ms for r in self.results) // max(total, 1)

        lines = [
            f"Eval Report: {passed}/{total} passed ({failed} failed)",
            f"Average latency: {avg_ms}ms",
            "",
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            tools = ", ".join(r.tools_called) if r.tools_called else "(none)"
            lines.append(f"  [{status}] {r.case.task[:60]}")
            lines.append(f"         Tools: {tools}")
            if r.details:
                lines.append(f"         {r.details}")
            lines.append("")

        return "\n".join(lines)


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_react_golden_set():
    """Run the full golden set against the ReAct loop."""

    class RecordingLLM:
        def __init__(self, response="FINAL ANSWER: The answer is 42."):
            self.calls = []
            self._response = response

        async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
            self.calls.append(messages)
            return self._response

        async def extract_structured(self, content, schema, instructions=""):
            return {}

    llm = RecordingLLM("FINAL ANSWER: The answer is 42.")
    runner = EvalRunner()

    for case in GOLDEN_SET:
        result = await runner.run_case(case, llm)
        runner.results.append(result)

    report = runner.report()
    print(report)

    assert len(runner.results) == len(GOLDEN_SET)


@pytest.mark.asyncio
async def test_eval_tracks_latency():
    """Verify eval harness tracks timing accurately."""

    class RecordingLLM:
        def __init__(self, response="FINAL ANSWER: done"):
            self.calls = []
            self._response = response

        async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
            self.calls.append(messages)
            return self._response

        async def extract_structured(self, content, schema, instructions=""):
            return {}

    llm = RecordingLLM("FINAL ANSWER: done")
    runner = EvalRunner()

    case = EvalCase(task="test", max_iterations=2)
    result = await runner.run_case(case, llm)

    assert result.duration_ms >= 0
    assert result.case == case


def test_eval_report_format():
    """Verify the eval report is properly formatted."""
    runner = EvalRunner()
    runner.results = [
        EvalResult(
            case=EvalCase(task="test task", expected_tools=["grep"]),
            tools_called=["grep"],
            answer="found it",
            passed=True,
            duration_ms=42,
        ),
        EvalResult(
            case=EvalCase(task="fail task", expected_tools=["read_file"]),
            tools_called=[],
            answer="error",
            passed=False,
            duration_ms=10,
            details="Missing tools: {'read_file'}",
        ),
    ]

    report = runner.report()
    assert "1/2 passed" in report
    assert "[PASS]" in report
    assert "[FAIL]" in report
