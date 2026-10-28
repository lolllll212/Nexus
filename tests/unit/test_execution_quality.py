"""Elite execution profile and deterministic response-quality tests."""

from __future__ import annotations

import json

from nexus.domain.entities.tool import Tool
from nexus.domain.value_objects.execution_quality import (
    assess_response_quality,
    build_execution_contract,
    build_execution_profile,
    build_quality_repair_prompt,
    normalize_effort,
)
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider
from tests.fakes.container import FakeContainer


def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_effort_normalization_and_simple_profile_are_fast_and_bounded():
    assert normalize_effort("Quick") == "fast"
    assert normalize_effort("thorough") == "deep"
    assert normalize_effort("nonsense") == "auto"

    profile = build_execution_profile("Hello")
    assert profile.effective_effort == "fast"
    assert profile.max_tokens == 1400
    assert profile.repair_attempts == 1
    assert profile.needs_tools is False
    assert "request_text" not in profile.as_dict()


def test_compound_workspace_profile_escalates_and_requires_evidence():
    profile = build_execution_profile("Fix src/app.py, run the tests, and summarize the result")
    assert profile.effective_effort in {"deep", "max"}
    assert profile.temperature <= 0.25
    assert profile.needs_workspace_evidence is True
    assert profile.needs_verification is True
    assert "src/app.py" in profile.brief.referenced_paths

    contract = build_execution_contract(profile)
    assert "ELITE EXECUTION CONTRACT" in contract
    assert "Never say done/tested/sent" in contract
    assert len(contract) <= 1400


def test_deep_research_and_explicit_max_have_distinct_budgets():
    research = build_execution_profile(
        "Compare the latest electric cars available in India",
        deep_research=True,
    )
    assert research.effective_effort == "deep"
    assert research.needs_current_sources is True

    maximum = build_execution_profile("Explain recursion", requested_effort="max")
    assert maximum.effective_effort == "max"
    assert maximum.max_tokens == 8192
    assert maximum.repair_attempts == 3
    assert maximum.min_quality_score == 90


def test_creative_tasks_keep_more_sampling_freedom_than_code():
    story = build_execution_profile("Write a creative short story about a lighthouse")
    code = build_execution_profile("Fix the Python parser bug in src/parser.py and test it")
    assert story.temperature > code.temperature


def test_calculation_gate_checks_the_actual_number():
    profile = build_execution_profile("What is 15% of 2400?")

    wrong = assess_response_quality(profile, "The result is 300.", tools_used=["calculator"])
    assert wrong.passed is False
    assert "incorrect_calculation" in _codes(wrong)

    correct = assess_response_quality(
        profile,
        "15% of 2400 is 360.",
        tools_used=["calculator"],
    )
    assert correct.passed is True
    assert correct.status == "verified"


def test_calculation_gate_accepts_an_english_number_word_result():
    profile = build_execution_profile("what is 2+2?")

    report = assess_response_quality(profile, "four", tools_used=["calculator"])

    assert report.passed is True
    assert "calculation_result" in report.checks


def test_nim_simulation_calculator_honors_an_explicit_json_result():
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    rendered = provider._deterministic_tool_result_answer(
        "calculator",
        "{'expression': '(2400 * 15 / 100)', 'result': 360.0}",
        'What is 15% of 2400? Return only JSON with a "result" field.',
    )

    assert json.loads(rendered) == {"result": 360}


def test_relevance_gate_ignores_opaque_identifier_fragments():
    profile = build_execution_profile(
        "task\n\nWorker reports:\n"
        "e8c7484d-49f1-4b4f-b099-3a4c194bb597: ok\n"
        "006a411a-2161-4d64-b7ee-57d1891601b9: ok"
    )

    report = assess_response_quality(profile, "ok")

    assert report.passed is True
    assert "off_task_answer" not in _codes(report)


def test_relevance_gate_still_catches_a_genuinely_unrelated_answer():
    profile = build_execution_profile(
        "Explain how photosynthesis in plants converts sunlight, carbon dioxide, "
        "and water into oxygen and glucose."
    )

    report = assess_response_quality(
        profile,
        "The stock index rose after investors welcomed stronger bank earnings.",
    )

    assert report.passed is False
    assert "off_task_answer" in _codes(report)


def test_current_claims_require_live_linked_dated_evidence():
    profile = build_execution_profile("Research the latest NVIDIA GPU prices today and compare them")

    unsupported = assess_response_quality(
        profile,
        "NVIDIA GPU prices are lower now, so the mid-range card is the best comparison choice.",
    )
    assert unsupported.passed is False
    assert "missing_current_evidence" in _codes(unsupported)

    grounded = assess_response_quality(
        profile,
        (
            "I checked the current NVIDIA GPU prices today. The comparison is based on "
            "the listings at https://example.com/gpu-prices, with current prices and "
            "availability separated from estimates before making the recommendation."
        ),
        tools_used=["web_search", "web_fetch"],
    )
    assert grounded.passed is True


def test_workspace_success_requires_mutation_and_verification_evidence():
    profile = build_execution_profile("Fix src/app.py, run the tests, and summarize the result")

    invented = assess_response_quality(
        profile,
        "Done — I fixed src/app.py and all tests passed.",
    )
    assert invented.passed is False
    assert "unsupported_action_claim" in _codes(invented)
    assert "unsupported_verification_claim" in _codes(invented)

    evidence_backed = assess_response_quality(
        profile,
        """## Result
- I inspected and fixed `src/app.py`, keeping the change limited to the faulty branch.
- The summary is based on the file contents observed before editing and the diff afterward.

## Verification
- `pytest_runner` ran the targeted tests for `src/app.py`, and the tests passed.
- No other files were changed, and there are no remaining blockers for this result.
""",
        tools_used=["read_file", "edit_file", "pytest_runner"],
        observations=[{"ok": True, "result": "targeted tests passed"}],
    )
    assert evidence_backed.passed is True
    assert evidence_backed.score >= profile.min_quality_score


def test_tool_failure_or_approval_cannot_be_reported_as_success():
    profile = build_execution_profile("Update src/config.py and verify it")
    report = assess_response_quality(
        profile,
        "Completed: src/config.py was updated and verified successfully with a complete summary of the change.",
        tools_used=["read_file", "edit_file", "project_checks"],
        observations=[{"approval_required": True, "message": "requires approval"}],
    )
    assert report.passed is False
    assert "contradicted_by_tool_evidence" in _codes(report)


def test_explicit_table_json_and_code_formats_are_enforced():
    table_profile = build_execution_profile(
        "Plan a 3-day Patna trip under ₹20,000 in a table"
    )
    table = assess_response_quality(
        table_profile,
        """| Day | Patna plan | Cost |
|---|---|---:|
| 1 | Arrive and explore Patna | ₹6,000 |
| 2 | Museums and food | ₹6,000 |
| 3 | Market and departure | ₹5,000 |

This 3-day Patna plan totals ₹17,000, safely under ₹20,000.""",
    )
    assert table.passed is True

    json_profile = build_execution_profile("Return the user summary as JSON")
    invalid_json = assess_response_quality(json_profile, "Here is the summary: Ada, admin")
    assert "format_json" in _codes(invalid_json)
    valid_json = assess_response_quality(json_profile, '{"name": "Ada", "role": "admin"}')
    assert valid_json.passed is True

    code_profile = build_execution_profile("Write Python code to reverse a string")
    code = assess_response_quality(
        code_profile,
        "```python\ndef reverse_string(value: str) -> str:\n    return value[::-1]\n```",
    )
    assert code.passed is True


def test_only_json_with_a_named_field_is_detected_and_satisfiable():
    profile = build_execution_profile(
        'What is 15% of 2400? Return only JSON with a "result" field.',
        requested_effort="fast",
    )
    assert profile.required_formats == ("json",)

    valid = assess_response_quality(
        profile,
        '{"result": 360}',
        tools_used=["calculator"],
    )
    assert valid.passed is True
    assert "format_json" in valid.checks
    assert "calculation_result" in valid.checks

    wrong_field = assess_response_quality(
        profile,
        '{"answer": 360}',
        tools_used=["calculator"],
    )
    assert wrong_field.passed is False
    assert "missing_constraints" in _codes(wrong_field)

    markdown = assess_response_quality(
        profile,
        "`(2400 * 15 / 100)` = **360.0**",
        tools_used=["calculator"],
    )
    assert markdown.passed is False
    assert "format_json" in _codes(markdown)


def test_missing_constraints_and_memory_citations_are_repairable():
    trip = build_execution_profile("Plan a 3-day Patna trip under ₹20,000 in a table")
    missing_budget = assess_response_quality(
        trip,
        """| Day | Plan |
|---|---|
| 1 | Explore Patna |
| 2 | Visit museums in Patna |
| 3 | Depart from Patna |""",
    )
    assert "missing_constraints" in _codes(missing_budget)

    memory = build_execution_profile("What did we decide earlier about Redis?")
    uncited = assess_response_quality(
        memory,
        "We decided to use Redis for sessions.",
        context_sources=[{"label": "M1", "source_type": "semantic"}],
    )
    assert "unsupported_memory_claim" in _codes(uncited)

    cited = assess_response_quality(
        memory,
        "We decided to use Redis for sessions [M1].",
        context_sources=[{"label": "M1", "source_type": "semantic"}],
    )
    assert cited.passed is True


def test_external_action_claim_and_repair_prompt_are_grounded():
    profile = build_execution_profile("Draft a polite email to my manager about leave")
    report = assess_response_quality(
        profile,
        "I sent the polite leave email to your manager.",
    )
    assert "unsupported_external_action" in _codes(report)

    prompt = build_quality_repair_prompt(profile, report, attempt=1)
    assert "Do not mention this gate" in prompt
    assert "Never fabricate" in prompt
    assert "unsupported_external_action" in prompt
    assert report.as_dict()["passed"] is False


class _ScriptedTextLLM:
    def __init__(self, turns: list[str]) -> None:
        self.turns = list(turns)
        self.calls: list[dict] = []

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
            }
        )
        return self.turns.pop(0) if self.turns else "FINAL ANSWER: No scripted turn remains."

    async def extract_structured(self, content, schema, instructions=""):
        return {}


class _NativeLLM:
    supports_native_tool_calls = True

    def __init__(self, *, fail_native: bool = False) -> None:
        self.fail_native = fail_native
        self.native_calls = []
        self.text_calls = []

    async def complete_with_tools(self, messages, tools, temperature=0.7, max_tokens=4096):
        self.native_calls.append({"messages": messages, "tools": tools, "temperature": temperature})
        if self.fail_native:
            raise RuntimeError("native tools unsupported by this endpoint")
        if len(self.native_calls) == 1:
            return {
                "type": "tool_call",
                "id": "call-1",
                "name": "calculator",
                "arguments": {"expression": "(2400 * 15 / 100)"},
            }
        return {"type": "text", "content": "15% of 2400 is 360."}

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.text_calls.append(messages)
        return "FINAL ANSWER: Native fallback text answer."

    async def extract_structured(self, content, schema, instructions=""):
        return {}


async def _register_tool(fake: FakeContainer, tool_id: str, properties: dict, required: list[str]):
    await fake.tool_registry.register(
        Tool(
            id=tool_id,
            name=tool_id,
            description=f"Test {tool_id}",
            input_schema=JSONSchema(properties=properties, required=required),
            output_schema=JSONSchema(),
        )
    )


async def test_cortex_uses_native_tool_calling_and_adaptive_sampling():
    fake = FakeContainer()
    await _register_tool(fake, "calculator", {"expression": {"type": "string"}}, ["expression"])
    llm = _NativeLLM()

    result = await fake.process_message.execute(
        user_id="u-native",
        message="What is 15% of 2400?",
        session_id="native-tools",
        tenant_id="default",
        llm=llm,
    )

    assert result.response == "15% of 2400 is 360."
    assert result.tools_used == ["calculator"]
    assert len(llm.native_calls) == 2
    assert llm.text_calls == []
    assert llm.native_calls[0]["tools"][0]["function"]["name"] == "calculator"
    assert llm.native_calls[0]["temperature"] <= 0.35
    assert result.quality is not None and result.quality["status"] == "verified"
    assert result.execution is not None and result.execution["effective_effort"] == "fast"


async def test_cortex_falls_back_to_text_when_native_tool_calling_fails():
    fake = FakeContainer()
    await _register_tool(fake, "calculator", {"expression": {"type": "string"}}, ["expression"])
    llm = _NativeLLM(fail_native=True)

    result = await fake.process_message.execute(
        user_id="u-native-fallback",
        message="Please explain why native tool calling needs a text fallback.",
        session_id="native-fallback",
        tenant_id="default",
        llm=llm,
    )

    assert result.response == "Native fallback text answer."
    assert len(llm.native_calls) == 1
    assert len(llm.text_calls) == 1


async def test_quality_gate_repairs_unsupported_current_answer_with_a_tool():
    fake = FakeContainer()
    await _register_tool(fake, "web_search", {"query": {"type": "string"}}, ["query"])
    llm = _ScriptedTextLLM(
        [
            "FINAL ANSWER: NVIDIA GPU prices are lower now and the mid-range option wins.",
            'TOOL_CALL: {"tool_id": "web_search", "params": {"query": "current NVIDIA GPU prices"}}',
            (
                "FINAL ANSWER: I checked the current NVIDIA GPU prices today at "
                "https://example.com/gpu-prices. The comparison separates confirmed current "
                "listings from estimates, then recommends the mid-range GPU because its price "
                "and performance are balanced for the stated comparison."
            ),
        ]
    )

    result = await fake.process_message.execute(
        user_id="u-repair",
        message="Research the latest NVIDIA GPU prices today and compare them",
        session_id="quality-repair",
        tenant_id="default",
        llm=llm,
    )

    assert result.tools_used == ["web_search"]
    assert "https://example.com/gpu-prices" in result.response
    assert result.quality is not None
    assert result.quality["repair_attempts_used"] == 1
    assert result.quality["status"] == "verified"
    second_context = "\n".join(
        str(message.get("content", "")) for message in llm.calls[1]["messages"]
    )
    assert "QUALITY REPAIR 1" in second_context
    assert "missing_current_evidence" in second_context


def test_execution_configuration_is_environment_backed(monkeypatch):
    from nexus.infrastructure.di.container import Config

    monkeypatch.setenv("NEXUS_AI_QUALITY_GATE_ENABLED", "false")
    monkeypatch.setenv("NEXUS_AI_NATIVE_TOOL_CALLING_ENABLED", "off")
    monkeypatch.setenv("NEXUS_AI_QUALITY_MAX_REPAIRS", "2")
    monkeypatch.setenv("NEXUS_AI_DEFAULT_EFFORT", "deep")

    config = Config()
    assert config.ai_quality_gate_enabled is False
    assert config.ai_native_tool_calling_enabled is False
    assert config.ai_quality_max_repairs == 2
    assert config.ai_default_effort == "deep"

    fake = FakeContainer()
    assert fake.ai_execution_config["default_effort"] == "auto"
    assert fake.process_message._quality_gate_enabled is True
    assert fake.process_message._native_tool_calling_enabled is True
