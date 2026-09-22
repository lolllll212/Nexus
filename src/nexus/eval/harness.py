"""Shared eval harness - golden set, grading, and JSON reporting.

Kept out of tests/ so the same cases (and rubric) can run both as pytest
(against fakes) and as a nightly GitHub Actions job against a real LLM.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from nexus.domain.ports.llm_provider import LLMProvider


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
    """Runs eval cases against an injected container/cortex and grades them.

    `container_factory` returns anything exposing a `.process_message` use
    case with an `execute(user_id, message, tenant_id)` method and a `.llm`
    attribute (for the fake-provider path). Defaults to the test fake so the
    same harness is unit-testable and live-runnable.
    """

    def __init__(self, container_factory: Callable[[], "object"]) -> None:
        self._container_factory = container_factory
        self.results: List[EvalResult] = []

    async def run_case(self, case: EvalCase, llm: Optional[LLMProvider] = None) -> EvalResult:
        """Run a single eval case against the (overridable) container."""
        container = self._container_factory()
        if llm is not None:
            container.llm = llm
            container.process_message._llm = llm

        started = time.monotonic()
        try:
            result = await container.process_message.execute(
                user_id="eval",
                message=case.task,
                tenant_id="eval",
            )
            return self._grade(case, result, started)
        except Exception as exc:
            return EvalResult(
                case=case,
                tools_called=[],
                answer="",
                passed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                details=str(exc),
            )

    def _grade(self, case: EvalCase, result, started: float) -> EvalResult:
        duration_ms = int((time.monotonic() - started) * 1000)
        tools_called = list(result.tools_used or [])
        answer = result.response or ""

        tools_ok = all(t in tools_called for t in case.expected_tools)
        answer_upper = answer.upper()
        keywords_ok = all(k.upper() in answer_upper for k in case.expected_keywords)
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

    async def run_all(self, llm: Optional[LLMProvider] = None) -> List[EvalResult]:
        self.results = [await self.run_case(case, llm=llm) for case in GOLDEN_SET]
        return self.results

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    def report(self) -> str:
        """Generate a human-readable eval report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        avg_ms = sum(r.duration_ms for r in self.results) // max(total, 1)

        lines = [
            f"Eval Report: {passed}/{total} passed ({failed} failed)",
            f"Pass rate: {self.pass_rate:.1%}",
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

    def to_json(self) -> dict:
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "pass_rate": self.pass_rate,
            "average_duration_ms": (
                sum(r.duration_ms for r in self.results) // max(len(self.results), 1)
            ),
            "results": [
                {
                    "task": r.case.task,
                    "expected_tools": r.case.expected_tools,
                    "expected_keywords": r.case.expected_keywords,
                    "tools_called": r.tools_called,
                    "answer": r.answer,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


def write_report_html(results: List[EvalResult], out_path: Path) -> None:
    """Write the eval report as a self-contained HTML artifact."""
    rows = []
    for r in results:
        cls = "pass" if r.passed else "fail"
        rows.append(
            f"<tr class='{cls}'>"
            f"<td>{'PASS' if r.passed else 'FAIL'}</td>"
            f"<td>{r.case.task}</td>"
            f"<td>{', '.join(r.tools_called) or '&mdash;'}</td>"
            f"<td>{r.duration_ms}ms</td><td>{r.details}</td></tr>"
        )
    passed = sum(1 for r in results if r.passed)
    total = max(len(results), 1)
    rate = passed / total
    html = (
        f"<html><head><style>"
        f"body{{font-family:monospace;margin:2rem}}"
        f".pass{{background:#e8f5e9}}.fail{{background:#ffebee}}"
        f"td{{padding:.4rem .8rem;border:1px solid #ddd}}"
        f"</style></head><body>"
        f"<h1>NEXUS Nightly Eval</h1>"
        f"<h2>{passed}/{len(results)} passed ({rate:.1%})</h2>"
        f"<table>{''.join(rows)}</table></body></html>"
    )
    out_path.write_text(html)


__all__ = [
    "EvalCase",
    "EvalResult",
    "GOLDEN_SET",
    "EvalRunner",
    "write_report_html",
]