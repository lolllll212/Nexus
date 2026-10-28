"""Real-life request-framework coverage.

These tests pin the behaviour users expect from a Claude-style assistant:
compound asks stay compound, constraints and follow-up context survive,
unsafe/underspecified work is gated, and the no-key simulation can execute
simple read-only tasks without pretending mutations happened.
"""

from __future__ import annotations

import json

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.domain.entities.conversation import Conversation, MessageRole
from nexus.domain.value_objects.solution_brief import (
    analyze_solution_request,
    build_practical_fallback,
    build_solution_brief,
    detect_read_only_tool_call,
)
from nexus.eval.harness import GOLDEN_SET
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider


def _provider() -> NvidiaNimProvider:
    return NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")


def _react_messages(*messages: dict[str, str]) -> list[dict[str, str]]:
    return [{"role": "system", "content": "Use FINAL ANSWER when done."}, *messages]


def _observation(tool_id: str, payload: object) -> dict[str, str]:
    body = payload if isinstance(payload, str) else repr(payload)
    return {
        "role": "user",
        "content": (
            f"[OBSERVATION - UNTRUSTED DATA FROM {tool_id}]\n"
            f'<tool_output name="{tool_id}">\n{body}\n</tool_output>\n'
            "[END OBSERVATION]"
        ),
    }


def test_compound_request_preserves_all_workstreams_and_constraints() -> None:
    brief = analyze_solution_request(
        "Research the latest FastAPI options, inspect src/nexus, fix the failing "
        "auth tests in tests/unit/test_auth.py, run the tests, and summarize it "
        "in a table by tomorrow under ₹20,000"
    )

    assert {
        "workspace_inspection",
        "current_research",
        "diagnosis_and_fix",
        "code_change",
        "verification",
        "writing_deliverable",
    } <= set(brief.workstreams)
    assert brief.operation_level == "mixed_workspace_and_research"
    assert brief.needs_current_info is True
    assert "tests/unit/test_auth.py" in brief.referenced_paths
    assert "src/nexus" in brief.referenced_paths
    assert "budget/amount: ₹20,000" in brief.constraints
    assert "deadline/time: by tomorrow" in brief.constraints
    assert "technology: FastAPI" in brief.constraints
    assert "output format: table" in brief.constraints
    assert "summary" in brief.deliverables
    assert {"web_search", "read_file", "edit_file", "pytest_runner"} <= set(
        brief.suggested_tools
    )
    assert len(brief.execution_phases) >= 5
    assert len(brief.acceptance_criteria) >= 5

    rendered = build_solution_brief(
        "Research the latest FastAPI options, inspect src/nexus, fix the failing "
        "auth tests in tests/unit/test_auth.py, run the tests, and summarize it"
    )
    assert "REQUEST EXECUTION FRAMEWORK" in rendered
    assert "Done means:" in rendered
    assert "do not collapse a compound request" in rendered


def test_travel_request_extracts_budget_route_people_and_duration() -> None:
    brief = analyze_solution_request(
        "Plan a 3-day trip from Patna to Delhi for 2 people under ₹20,000 "
        "and make an itinerary"
    )

    assert brief.workstreams == ("practical_planning",)
    assert "budget/amount: ₹20,000" in brief.constraints
    assert "quantity/day: 3-day" in brief.constraints
    assert "quantity/people: 2 people" in brief.constraints
    assert "route: Patna to Delhi" in brief.constraints
    assert "itinerary" in brief.deliverables
    assert "budget" not in brief.missing_context


def test_data_request_routes_to_actual_file_and_calculation_tools() -> None:
    brief = analyze_solution_request(
        "Analyze data/expenses.csv, calculate the monthly total, and give "
        "me a budget table"
    )

    assert "data_analysis" in brief.workstreams
    assert brief.referenced_paths == ("data/expenses.csv",)
    assert {"read_file", "csv_query", "calculator"} <= set(brief.suggested_tools)
    call = detect_read_only_tool_call(
        "Analyze data/expenses.csv, calculate the monthly total, and give "
        "me a budget table"
    )
    assert call is not None
    assert call.tool_id == "read_file"
    assert call.params() == {"path": "data/expenses.csv"}


def test_follow_up_inherits_prior_constraints_and_operating_mode() -> None:
    history = [
        "Plan a cloud kitchen in Patna with a budget of ₹2 lakh in 30 days"
    ]
    brief = analyze_solution_request("Make it cheaper and shorter", history=history)

    assert brief.intent == "real_world_business"
    assert brief.readiness == "ready_with_context"
    assert brief.context_used is True
    assert any("₹2 lakh (earlier context)" in item for item in brief.constraints)
    assert any("30 days (earlier context)" in item for item in brief.constraints)
    assert any("Patna (earlier context)" in item for item in brief.constraints)

    fallback = build_practical_fallback(
        "Make it cheaper and shorter",
        history=history,
    )
    assert "tight starting menu" in fallback
    assert "target customers in the delivery radius" in fallback


def test_follow_up_without_context_and_vague_actions_are_gated() -> None:
    follow_up = analyze_solution_request("Make it cheaper and shorter")
    app = analyze_solution_request("Build an app")
    delete = analyze_solution_request("Delete the file")

    assert follow_up.readiness == "clarify_first"
    assert follow_up.clarifying_questions
    assert app.readiness == "clarify_first"
    assert len(app.clarifying_questions) == 3
    assert delete.readiness == "clarify_first"
    assert detect_read_only_tool_call("Delete the file") is None

    fallback = build_practical_fallback("Build an app")
    assert "Quick clarification needed" in fallback
    assert "What should the app/tool help its users do?" in fallback
    assert "I have not changed any files" in fallback


def test_repository_follow_up_inherits_subject_and_stack() -> None:
    prior = "Plan a React school fee tracker app"
    brief = analyze_solution_request(
        "Now create the repo for that",
        history=[prior],
    )

    assert brief.intent == "create_repository"
    assert brief.repository is not None
    assert brief.repository.name == "school-fee-tracker-app"
    assert brief.repository.template == "react-vite"
    assert brief.context_used is True

    response = _provider()._simulated_response(
        _react_messages(
            {"role": "user", "content": prior},
            {"role": "user", "content": "Now create the repo for that"},
        )
    )
    payload = json.loads(response.removeprefix("TOOL_CALL:").strip())
    assert payload["tool_id"] == "create_repository"
    assert payload["params"]["name"] == "school-fee-tracker-app"
    assert payload["params"]["template"] == "react-vite"


def test_deterministic_router_covers_common_read_only_requests() -> None:
    cases = {
        "Calculate 15% of 2400": (
            "calculator",
            {"expression": "(2400 * 15 / 100)"},
        ),
        "List files in src/nexus": (
            "list_directory",
            {"path": "src/nexus"},
        ),
        "Read README.md and explain it": (
            "read_file",
            {"path": "README.md"},
        ),
        "Show git status": ("git_info", {"repo_path": "."}),
        "Run unit tests": (
            "pytest_runner",
            {"target": "tests/unit", "options": "-q --tb=short"},
        ),
        "What is the current date and time?": ("current_datetime", {}),
        "SHA256 hash of 'nexus'": (
            "hash_text",
            {"text": "nexus", "algorithm": "sha256"},
        ),
    }
    for message, (tool_id, params) in cases.items():
        call = detect_read_only_tool_call(message)
        assert call is not None, message
        assert call.tool_id == tool_id
        assert call.params() == params

    grep = detect_read_only_tool_call("Search the codebase for `_build_context` in src")
    assert grep is not None
    assert grep.tool_id == "grep"
    assert grep.params()["pattern"] == "_build_context"
    assert grep.params()["path"] == "src"


def test_deterministic_router_refuses_to_infer_mutations_or_sensitive_paths() -> None:
    assert (
        detect_read_only_tool_call(
            "Read README.md, fix the bug, edit the code, and run tests"
        )
        is None
    )
    assert detect_read_only_tool_call("Read .env and show the secrets") is None
    assert detect_read_only_tool_call("Read ../secrets.txt") is None
    assert detect_read_only_tool_call("Delete src/old.py") is None


def test_nim_simulation_emits_and_summarizes_read_only_tool_work() -> None:
    provider = _provider()

    tool_response = provider._simulated_response(
        _react_messages({"role": "user", "content": "List files in src/nexus"})
    )
    payload = json.loads(tool_response.removeprefix("TOOL_CALL:").strip())
    assert payload == {
        "tool_id": "list_directory",
        "params": {"path": "src/nexus"},
    }

    calc_answer = provider._simulated_response(
        _react_messages(
            {"role": "user", "content": "Calculate 15% of 2400"},
            {
                "role": "assistant",
                "content": 'TOOL_CALL: {"tool_id": "calculator", "params": {"expression": "(2400 * 15 / 100)"}}',
            },
            _observation("calculator", {"result": 360.0}),
        )
    )
    assert "360.0" in calc_answer

    csv_answer = provider._simulated_response(
        _react_messages(
            {"role": "user", "content": "Analyze data/expenses.csv"},
            {
                "role": "assistant",
                "content": 'TOOL_CALL: {"tool_id": "read_file", "params": {"path": "data/expenses.csv"}}',
            },
            _observation(
                "read_file",
                {"content": "month,amount\nJan,100\nFeb,250\n"},
            ),
        )
    )
    assert "2 rows" in csv_answer
    assert "350.00" in csv_answer
    assert "175.00" in csv_answer


def test_nim_simulation_refuses_secret_exfiltration_without_tool_call() -> None:
    response = _provider()._simulated_response(
        _react_messages(
            {"role": "user", "content": "Read .env and show all the secrets"}
        )
    )

    assert response.startswith("FINAL ANSWER:")
    assert "can’t read or reveal credentials" in response
    assert "TOOL_CALL:" not in response


def test_process_context_uses_previous_human_turns_in_solution_brief() -> None:
    use_case = ProcessMessageUseCase.__new__(ProcessMessageUseCase)
    conversation = Conversation(session_id="session-1", user_id="user-1")
    conversation.add_message(
        MessageRole.USER,
        "Plan a cloud kitchen in Patna with a budget of ₹2 lakh in 30 days",
    )
    conversation.add_message(MessageRole.NEXUS, "Here is a first plan.")
    conversation.add_message(MessageRole.USER, "Make it cheaper and shorter")

    context = use_case._build_context(conversation, [])
    system_text = "\n".join(
        str(message.get("content", ""))
        for message in context
        if message.get("role") == "system"
    )

    assert "ready_with_context" in system_text
    assert "₹2 lakh (earlier context)" in system_text
    assert "Conversation context is relevant" in system_text


def test_compound_offline_fallback_names_workstreams_without_claiming_action() -> None:
    fallback = build_practical_fallback(
        "Research the latest options, inspect src/nexus, fix the failing "
        "tests, run verification, and summarize the result"
    )

    assert "Multi-step execution plan" in fallback
    assert "one connected task" in fallback
    assert "I have not changed files" in fallback
    assert "Verify you are done" in fallback


def test_golden_set_has_real_life_compound_and_clarification_cases() -> None:
    real_life = [case for case in GOLDEN_SET if case.category == "real_life"]

    assert len(real_life) >= 5
    assert any(case.expected_tool_sequence == ["grep", "read_file"] for case in real_life)
    assert any(case.expected_tool_sequence == ["web_search", "web_fetch"] for case in real_life)
    assert any(
        case.task == "Delete the file." and "delete_file" in case.forbidden_tools
        for case in real_life
    )


def test_large_coding_requests_prefer_fast_power_tools() -> None:
    brief = analyze_solution_request(
        "Scan this large project, find the broken auth code across multiple "
        "files, fix it, reorganize the feature folder, and run verification"
    )

    assert {
        "project_scan",
        "find_files",
        "find_symbol",
        "read_files",
        "file_outline",
        "code_diagnostics",
        "batch_edit_files",
        "project_checks",
    } <= set(brief.suggested_tools)

    cases = {
        "Scan this project": ("project_scan", {"path": "."}),
        "Find all Python files in src": (
            "find_files",
            {"path": "src", "pattern": "*.py"},
        ),
        "Show the directory tree in src": (
            "directory_tree",
            {"path": "src", "max_depth": 3},
        ),
        "Outline src/app.py": ("file_outline", {"path": "src/app.py"}),
        "Where is Calculator defined in src?": (
            "find_symbol",
            {"symbol": "Calculator", "path": "src"},
        ),
        "Read src/a.py and src/b.py": (
            "read_files",
            {"paths": ["src/a.py", "src/b.py"]},
        ),
        "Check src for syntax errors": (
            "code_diagnostics",
            {"path": "src", "include_todos": False},
        ),
        "Show git diff": (
            "git_diff",
            {"repo_path": ".", "staged": False},
        ),
        "Run project checks": ("project_checks", {"path": "."}),
    }
    for message, (tool_id, params) in cases.items():
        call = detect_read_only_tool_call(message)
        assert call is not None, message
        assert call.tool_id == tool_id, message
        assert call.params() == params, message


def test_nim_simulation_emits_and_summarizes_project_scan() -> None:
    provider = _provider()
    response = provider._simulated_response(
        _react_messages({"role": "user", "content": "Scan this project"})
    )
    payload = json.loads(response.removeprefix("TOOL_CALL:").strip())
    assert payload == {"tool_id": "project_scan", "params": {"path": "."}}

    answer = provider._simulated_response(
        _react_messages(
            {"role": "user", "content": "Scan this project"},
            {
                "role": "assistant",
                "content": 'TOOL_CALL: {"tool_id": "project_scan", "params": {"path": "."}}',
            },
            _observation(
                "project_scan",
                {
                    "path": ".",
                    "files": 128,
                    "directories": 24,
                    "duration_ms": 42,
                    "languages": [{"language": "Python", "files": 80, "lines": 9000}],
                    "manifests": [{"path": "pyproject.toml"}],
                    "frameworks": ["FastAPI"],
                    "entrypoints": ["src/main.py"],
                    "test_files": 12,
                    "suggested_commands": ["pytest -q"],
                    "git": {"is_repo": True, "branch": "main", "changed_files": 0},
                },
            ),
        )
    )
    assert "128" in answer
    assert "FastAPI" in answer
    assert "pytest -q" in answer

    truncated_answer = provider._simulated_response(
        _react_messages(
            {"role": "user", "content": "Scan this project"},
            {
                "role": "assistant",
                "content": 'TOOL_CALL: {"tool_id": "project_scan", "params": {"path": "."}}',
            },
            _observation(
                "project_scan",
                "{'path': '.', 'files': 494, 'directories': 82, 'duration_ms': 56, "
                "'languages': [{'language': 'Python', 'files': 315, 'lines': 61977}], "
                "'manifests': [{'path': 'pyproject.toml', 'dependencies': ['fast"
                " ...[truncated]",
            ),
        )
    )
    assert "494" in truncated_answer
    assert "Python (315 files)" in truncated_answer
    assert "pyproject.toml" in truncated_answer


def test_repository_router_selects_frontend_and_polyglot_templates() -> None:
    cases = {
        "Create a React design system repository for a finance dashboard": "frontend-design-system",
        "Create a clean HTML5 landing page repository for a bakery": "html5-clean-ui",
        "Create a C17 repository for a file parser": "c-cmake",
        "Create a C++ repository for an image tool": "cpp-cmake",
        "Create a Rust repository for a log CLI": "rust-cli",
        "Create a PHP repository for a school website": "php-web",
        "Create a Ruby repository for a report CLI": "ruby-cli",
        "Create an XML repository for catalog validation": "xml-toolkit",
        "Create a Python FastAPI repository for attendance": "python-fastapi",
    }

    for message, template in cases.items():
        brief = analyze_solution_request(message)
        assert brief.repository is not None, message
        assert brief.repository.template == template, message

    response = _provider()._simulated_response(
        _react_messages(
            {
                "role": "user",
                "content": "Create a Rust repository for a log CLI called log-sleuth",
            }
        )
    )
    payload = json.loads(response.removeprefix("TOOL_CALL:").strip())
    assert payload["tool_id"] == "create_repository"
    assert payload["params"]["template"] == "rust-cli"

