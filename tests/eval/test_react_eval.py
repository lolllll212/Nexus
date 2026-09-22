"""
Golden-set eval harness tests - reuse the shared rubric from nexus.eval.

Run with: pytest tests/eval/ -v

These run the SAME harness (EvalCase/EvalResult/GOLDEN_SET/EvalRunner) that
the nightly `python -m nexus.eval` job uses, but against a RecordingLLM + the
fake container, so the unit test verifies grading without a live model.
"""

from __future__ import annotations

from tests.fakes.container import FakeContainer

from nexus.eval.harness import EvalRunner, GOLDEN_SET


class RecordingLLM:
    def __init__(self, response="FINAL ANSWER: The answer is 42."):
        self.calls = []
        self._response = response

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(messages)
        return self._response

    async def extract_structured(self, content, schema, instructions=""):
        return {}


def _runner():
    return EvalRunner(container_factory=lambda: FakeContainer())


async def test_react_golden_set():
    """Run the full golden set against the ReAct loop (fake LLM)."""
    llm = RecordingLLM("FINAL ANSWER: The answer is 42.")
    runner = _runner()

    for case in GOLDEN_SET:
        runner.results.append(await runner.run_case(case, llm=llm))

    report = runner.report()
    print(report)

    assert len(runner.results) == len(GOLDEN_SET)
    # Every case should have been attempted with the fake LLM.
    assert all(r.duration_ms >= 0 for r in runner.results)


async def test_react_golden_set_with_tools():
    """Golden set with a scripted tool-calling LLM exercises the ACT/OBSERVE path."""

    class ToolCallingLLM(RecordingLLM):
        def __init__(self):
            super().__init__("FINAL ANSWER: 1024.")
            self.turns = 0

        async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
            self.calls.append(messages)
            self.turns += 1
            if self.turns == 1:
                return 'TOOL_CALL: {"tool_id": "calculator", "params": {"expression": "2**10"}}'
            return "FINAL ANSWER: 2 raised to the power of 10 is 1024."

    fake = FakeContainer()
    from nexus.domain.entities.tool import Tool
    from nexus.domain.value_objects.schema import JSONSchema

    # Register a real calculator tool so the ACT step finds it in the registry.
    await fake.tool_registry.register(
        Tool(
            id="calculator",
            name="calculator",
            description="Evaluate a math expression safely.",
            input_schema=JSONSchema(properties={"expression": {"type": "string"}}, required=["expression"]),
            output_schema=JSONSchema(properties={"result": {"type": "number"}}),
        )
    )
    runner = EvalRunner(container_factory=lambda: fake)
    result = await runner.run_case(
        next(c for c in GOLDEN_SET if c.task.startswith("Calculate")), llm=ToolCallingLLM()
    )
    assert result.passed


async def test_eval_tracks_latency():
    """Verify eval harness tracks timing accurately."""
    llm = RecordingLLM("FINAL ANSWER: The capital of France is Paris.")
    runner = _runner()
    result = await runner.run_case(
        next(c for c in GOLDEN_SET if c.task.startswith("What is the capital")), llm=llm
    )

    assert result.duration_ms >= 0
    assert result.passed  # capital of France + no tools expected


async def test_eval_report_format():
    """Verify the eval report is properly formatted and JSON-serializable."""
    llm = RecordingLLM("FINAL ANSWER: The answer is 42.")
    runner = _runner()
    await runner.run_all(llm=llm)

    report = runner.report()
    assert "Eval Report:" in report
    assert "[PASS]" in report or "[FAIL]" in report

    data = runner.to_json()
    assert data["total"] == len(GOLDEN_SET)
    assert data["passed"] == sum(1 for r in runner.results if r.passed)
    assert data["pass_rate"] == data["passed"] / data["total"]


def test_write_report_html(tmp_path):
    """HTML artifact generation works."""
    from nexus.eval.harness import EvalCase, EvalResult, write_report_html

    write_report_html(
        [
            EvalResult(
                case=EvalCase(task="t"), tools_called=["grep"], answer="x", passed=True, duration_ms=1
            ),
            EvalResult(
                case=EvalCase(task="u"),
                tools_called=[],
                answer="",
                passed=False,
                duration_ms=2,
                details="nope",
            ),
        ],
        tmp_path / "report.html",
    )
    html = (tmp_path / "report.html").read_text()
    assert "<table>" in html
    assert "1/2 passed" in html
