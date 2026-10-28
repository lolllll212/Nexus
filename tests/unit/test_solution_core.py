"""Real-world solution brief and simulation-fallback coverage."""

from __future__ import annotations

import json

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.domain.entities.conversation import Conversation, MessageRole
from nexus.domain.value_objects.solution_brief import (
    analyze_solution_request,
    build_practical_fallback,
    build_solution_brief,
    detect_repository_request,
)
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider


def test_classifier_routes_home_failure_to_troubleshooting() -> None:
    brief = analyze_solution_request("My fridge is not cooling. What should I check first?")

    assert brief.intent == "troubleshooting"
    assert brief.mode == "diagnose_then_fix"
    assert "Safest checks first" in brief.answer_sections


def test_classifier_routes_cloud_kitchen_to_business_plan() -> None:
    brief = analyze_solution_request(
        "How do I start a small cloud kitchen in Patna with a low budget?"
    )

    assert brief.intent == "real_world_business"
    assert "target customer" in brief.missing_context


def test_classifier_marks_volatile_decision_as_current_info() -> None:
    brief = analyze_solution_request("Which latest phone should I buy today under a tight budget?")

    assert brief.intent == "decision"
    assert brief.needs_current_info is True
    assert "web_search" in brief.suggested_tools


def test_classifier_puts_emergency_safety_first() -> None:
    brief = analyze_solution_request("There is a gas leak and a strong smell in my kitchen")

    assert brief.intent == "urgent_safety"
    assert brief.urgent is True
    fallback = build_practical_fallback("There is a gas leak and a strong smell in my kitchen")
    assert "Do this now" in fallback
    assert "local emergency number" in fallback


def test_repository_detection_extracts_name_and_template() -> None:
    request = detect_repository_request("Create a React repo for a school fee tracker")

    assert request is not None
    assert request.name == "school-fee-tracker"
    assert request.template == "react-vite"
    assert request.tool_params()["initial_commit"] is True


def test_repository_detection_does_not_trigger_on_explanation() -> None:
    assert detect_repository_request("Explain what a GitHub repository is") is None


def test_rendered_brief_includes_grounding_and_repository_rules() -> None:
    rendered = build_solution_brief("Create a Python repository for tracking rent payments")

    assert "REAL-WORLD SOLUTION BRIEF" in rendered
    assert "create_repository" in rendered
    assert "Never invent prices, laws, dates" in rendered
    assert "Never claim a GitHub repository was created" in rendered


def test_practical_fallback_is_structured_and_not_a_canned_acknowledgement() -> None:
    fallback = build_practical_fallback(
        "How do I start a small cloud kitchen in Patna with a low budget?",
        model_label="offline test model",
    )

    assert "Best first move" in fallback
    assert "Step-by-step" in fallback
    assert "target customers" in fallback
    assert "Verify you are done" in fallback
    assert "processed your inquiry" not in fallback


def test_fridge_fallback_is_appliance_specific() -> None:
    fallback = build_practical_fallback(
        "My fridge is not cooling. What should I check first before calling a technician?"
    )

    assert "Keep the doors closed" in fallback
    assert "3–4°C" in fallback
    assert "door seals fully" in fallback
    assert "refrigerator technician" in fallback
    assert "back up important data" not in fallback.lower()
    assert "known-good cable/file/account" not in fallback


def test_cloud_kitchen_fallback_includes_india_permissions_and_unit_costs() -> None:
    fallback = build_practical_fallback(
        "How do I start a small cloud kitchen in Patna with a low budget?"
    )

    assert "FSSAI" in fallback
    assert "aggregator commission" in fallback
    assert "6–10 standardized dishes" in fallback
    assert "profit per order" in fallback


def test_internet_fallback_uses_ordered_restart_and_isolation() -> None:
    fallback = build_practical_fallback("My home internet is not working on any device")

    assert "ONT/modem first" in fallback
    assert "mobile hotspot" in fallback
    assert "avoid factory reset" in fallback


def test_process_message_context_injects_solution_brief() -> None:
    use_case = ProcessMessageUseCase.__new__(ProcessMessageUseCase)
    conversation = Conversation(session_id="session-1", user_id="user-1")
    conversation.add_message(MessageRole.USER, "My washing machine stopped working")

    context = use_case._build_context(conversation, [])
    system_text = "\n".join(
        str(message.get("content", ""))
        for message in context
        if message.get("role") == "system"
    )

    assert "REAL-WORLD SOLUTION BRIEF" in system_text
    assert "diagnose_then_fix" in system_text


def test_nim_simulation_preserves_model_identity_for_greeting() -> None:
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    answer = provider._simulated_response([{"role": "user", "content": "hi"}])

    assert "meta/llama-3.3-70b-instruct" in answer
    assert "Llama 3.3 70B" in answer


def test_nim_simulation_emits_repository_tool_call_in_react() -> None:
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    response = provider._simulated_response(
        [
            {"role": "system", "content": "Use FINAL ANSWER when done."},
            {"role": "user", "content": "Create a React repo for a school fee tracker"},
        ]
    )

    assert response.startswith("TOOL_CALL:")
    payload = json.loads(response.removeprefix("TOOL_CALL:").strip())
    assert payload["tool_id"] == "create_repository"
    assert payload["params"]["name"] == "school-fee-tracker"
    assert payload["params"]["template"] == "react-vite"


def test_nim_simulation_reports_approval_without_claiming_creation() -> None:
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    response = provider._simulated_response(
        [
            {"role": "system", "content": "Use FINAL ANSWER when done."},
            {"role": "user", "content": "Create a repo for a rent tracker"},
            {"role": "assistant", "content": "TOOL_CALL: create_repository"},
            {
                "role": "user",
                "content": (
                    "<tool_output name=\"create_repository\">"
                    "{'error': 'Approval required', 'approval_required': True}"
                    "</tool_output>"
                ),
            },
        ]
    )

    assert response.startswith("FINAL ANSWER:")
    assert "not approved yet" in response
    assert "I have not created any files yet" in response


def test_nim_simulation_summarizes_repository_observation() -> None:
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    response = provider._simulated_response(
        [
            {"role": "system", "content": "Use FINAL ANSWER when done."},
            {"role": "user", "content": "Create a repo for a rent tracker"},
            {
                "role": "user",
                "content": (
                    "<tool_output name=\"create_repository\">"
                    "{'created': True, 'name': 'rent-tracker', "
                    "'path': 'projects/rent-tracker', 'template': 'python-fastapi', "
                    "'git': {'committed': True}}"
                    "</tool_output>"
                ),
            },
        ]
    )

    assert "Created **rent-tracker**" in response
    assert "projects/rent-tracker" in response
    assert "git push -u origin main" in response
