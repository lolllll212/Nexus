"""Claude-style chat workspace tool wiring tests.

Covers the safe file-operation tools (create/edit/delete/directory), the
local repository builder, their approval gate, the ReAct prompt contract, and
the authenticated tool API used by the web chat window's Tools/Code panel.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.application.cortex.react_prompt import REACT_SYSTEM_PROMPT
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.execution.builtin_tools import (
    BuiltinToolRegistry,
    default_builtin_tools,
)
from nexus.infrastructure.adapters.execution.extended_tools import (
    EXTENDED_HANDLERS,
    TOOL_DEFS,
    set_autonomy_policy,
)
from nexus.infrastructure.adapters.execution.registry_tool_executor import (
    RegistryBackedToolExecutor,
)
from nexus.infrastructure.adapters.security.in_memory_rate_limiter import InMemoryRateLimiter
from nexus.infrastructure.api.main import create_app
from tests.fakes import FakeSandbox
from tests.fakes.container import TEST_API_KEY_1, TEST_API_KEY_2, FakeContainer

ADMIN_AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
USER_AUTH = {"Authorization": f"Bearer {TEST_API_KEY_2}"}
FILE_TOOLS = {"write_file", "edit_file", "delete_file", "create_directory"}
WORKSPACE_TOOLS = FILE_TOOLS | {"create_repository"}
CODING_POWER_TOOLS = {
    "project_scan",
    "find_files",
    "directory_tree",
    "read_files",
    "file_outline",
    "find_symbol",
    "code_diagnostics",
    "git_diff",
    "project_checks",
    "secret_scan",
    "release_readiness",
    "changelog_draft",
    "write_files",
    "batch_edit_files",
    "move_path",
    "copy_path",
    "delete_directory",
}
APPROVAL_GATED_POWER_TOOLS = {
    "write_files",
    "batch_edit_files",
    "move_path",
    "copy_path",
    "delete_directory",
}


@pytest.fixture
def client_and_fake():
    app = create_app()
    fake = FakeContainer()
    fake.tool_registry.tools = {tool.id: tool for tool in default_builtin_tools()}
    app.state.container = fake
    client = TestClient(app, raise_server_exceptions=False)
    client.app.state.container = fake
    return client, fake


def test_file_tools_are_registered_with_handlers_and_prompt_examples():
    defined = {definition["id"] for definition in TOOL_DEFS}
    registered = {tool.id for tool in default_builtin_tools()}

    assert WORKSPACE_TOOLS <= defined
    assert WORKSPACE_TOOLS <= registered
    assert WORKSPACE_TOOLS <= set(EXTENDED_HANDLERS)
    for tool_id in WORKSPACE_TOOLS:
        assert f'"tool_id": "{tool_id}"' in REACT_SYSTEM_PROMPT
    assert "approval_required" in REACT_SYSTEM_PROMPT
    assert "never claim the change happened" in REACT_SYSTEM_PROMPT
    assert "never claim GitHub creation/push without proof" in REACT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_edit_create_directory_and_delete_file_happy_path(tmp_path):
    policy = DefaultAutonomyPolicy(rate_limiter=InMemoryRateLimiter(), allowlist=[])
    set_autonomy_policy(policy)
    target = tmp_path / "notes.txt"
    target.write_text("hello hello\n", encoding="utf-8")
    try:
        blocked = await EXTENDED_HANDLERS["edit_file"](
            {"path": str(target), "old_text": "hello hello", "new_text": "namaste"}
        )
        assert blocked["approval_required"] is True
        assert target.read_text(encoding="utf-8") == "hello hello\n"

        for tool_id in ("edit_file", "create_directory", "delete_file"):
            await policy.grant_approval(f"tool:{tool_id}", approver="admin", tenant_id="default")

        ambiguous = await EXTENDED_HANDLERS["edit_file"](
            {"path": str(target), "old_text": "hello", "new_text": "namaste"}
        )
        assert ambiguous["replacements"] == 0
        assert ambiguous["occurrences"] == 2

        edited = await EXTENDED_HANDLERS["edit_file"](
            {
                "path": str(target),
                "old_text": "hello",
                "new_text": "namaste",
                "replace_all": True,
            }
        )
        assert edited["replacements"] == 2
        assert target.read_text(encoding="utf-8") == "namaste namaste\n"

        created = await EXTENDED_HANDLERS["create_directory"](
            {"path": str(tmp_path / "drafts" / "2026")}
        )
        assert created["created"] is True
        assert (tmp_path / "drafts" / "2026").is_dir()

        unconfirmed = await EXTENDED_HANDLERS["delete_file"](
            {"path": str(target), "confirm": False}
        )
        assert unconfirmed["deleted"] is False
        assert target.exists()

        deleted = await EXTENDED_HANDLERS["delete_file"](
            {"path": str(target), "confirm": True}
        )
        assert deleted["deleted"] is True
        assert not target.exists()
    finally:
        set_autonomy_policy(None)


@pytest.mark.asyncio
async def test_create_repository_builds_git_ready_project_after_approval(tmp_path):
    policy = DefaultAutonomyPolicy(rate_limiter=InMemoryRateLimiter(), allowlist=[])
    set_autonomy_policy(policy)
    target = tmp_path / "rent-cli"
    params = {
        "name": "rent-cli",
        "path": str(target),
        "template": "python-cli",
        "description": "Track rent payments from the command line",
    }
    try:
        blocked = await EXTENDED_HANDLERS["create_repository"](params)
        assert blocked["approval_required"] is True
        assert not target.exists()

        await policy.grant_approval(
            "tool:create_repository", approver="admin", tenant_id="default"
        )
        created = await EXTENDED_HANDLERS["create_repository"](params)

        assert created["created"] is True
        assert created["name"] == "rent-cli"
        assert created["template"] == "python-cli"
        assert "src/rent_cli/cli.py" in created["files"]
        assert (target / "README.md").is_file()
        assert (target / "tests" / "test_cli.py").is_file()
        assert created["git"]["initialized"] is True
        assert created["git"]["branch"] == "main"
        assert created["git"]["committed"] is True
        assert created["github"] == {
            "created": False,
            "pushed": False,
            "remote_configured": False,
            "push_commands": created["github"]["push_commands"],
        }

        blocked_again = await EXTENDED_HANDLERS["create_repository"](params)
        assert blocked_again["created"] is False
        assert "not empty" in blocked_again["error"]

        unknown = target / "keep-me.txt"
        unknown.write_text("do not delete\n", encoding="utf-8")
        overwritten = await EXTENDED_HANDLERS["create_repository"](
            {**params, "template": "empty", "overwrite": True}
        )
        assert overwritten["created"] is True
        assert unknown.read_text(encoding="utf-8") == "do not delete\n"
        assert overwritten["preserved_unknown_files"] >= 1
    finally:
        set_autonomy_policy(None)


@pytest.mark.asyncio
async def test_registry_executor_gates_and_normalizes_repository_aliases(tmp_path):
    policy = DefaultAutonomyPolicy(rate_limiter=InMemoryRateLimiter(), allowlist=[])
    set_autonomy_policy(policy)
    target = tmp_path / "alias-api"
    executor = RegistryBackedToolExecutor(
        BuiltinToolRegistry(default_builtin_tools()),
        FakeSandbox(),
        dict(EXTENDED_HANDLERS),
        autonomy_policy=policy,
    )
    params = {
        "project_name": "alias-api",
        "destination": str(target),
        "stack": "node-api",
        "description": "Alias normalization test API",
    }
    try:
        blocked = await executor.execute("create_repository", params)
        assert blocked["approval_required"] is True
        assert not target.exists()

        await policy.grant_approval(
            "tool:create_repository", approver="admin", tenant_id="default"
        )
        created = await executor.execute("create_repository", params)
        assert created["created"] is True
        assert created["template"] == "node-api"
        assert (target / "src" / "index.js").is_file()
    finally:
        set_autonomy_policy(None)


@pytest.mark.asyncio
async def test_file_tools_reject_paths_outside_workspace_and_denylist(tmp_path):
    outside = await EXTENDED_HANDLERS["edit_file"](
        {"path": "/etc/passwd", "old_text": "root", "new_text": "x"}
    )
    assert outside["replacements"] == 0
    assert "escapes workspace" in outside["error"] or "Access denied" in outside["error"]

    denied = await EXTENDED_HANDLERS["delete_file"]({"path": ".env", "confirm": True})
    assert denied["deleted"] is False
    assert "Access denied" in denied["error"] or "forbidden" in denied["error"]

    directory = await EXTENDED_HANDLERS["delete_file"](
        {"path": str(tmp_path), "confirm": True}
    )
    assert directory["deleted"] is False
    assert "regular files" in directory["error"]


@pytest.mark.asyncio
async def test_registry_executor_gates_new_file_tools(tmp_path):
    policy = DefaultAutonomyPolicy(rate_limiter=InMemoryRateLimiter(), allowlist=[])
    set_autonomy_policy(policy)
    target = tmp_path / "code.py"
    target.write_text("value = 1\n", encoding="utf-8")
    executor = RegistryBackedToolExecutor(
        BuiltinToolRegistry(default_builtin_tools()),
        FakeSandbox(),
        dict(EXTENDED_HANDLERS),
        autonomy_policy=policy,
    )
    try:
        blocked = await executor.execute(
            "edit_file",
            {"path": str(target), "old_text": "value = 1", "new_text": "value = 2"},
        )
        assert blocked["approval_required"] is True
        assert target.read_text(encoding="utf-8") == "value = 1\n"

        await policy.grant_approval("tool:edit_file", approver="admin", tenant_id="default")
        # Common model aliases are normalized before schema validation.
        edited = await executor.execute(
            "edit_file",
            {"filename": str(target), "search": "value = 1", "replacement": "value = 2"},
        )
        assert edited["replacements"] == 1
        assert target.read_text(encoding="utf-8") == "value = 2\n"
    finally:
        set_autonomy_policy(None)


def test_tools_api_exposes_schemas_approvals_and_admin_execution(client_and_fake):
    client, fake = client_and_fake

    assert client.get("/v1/tools").status_code == 401
    listed = client.get("/v1/tools", headers=USER_AUTH)
    assert listed.status_code == 200
    tools = {tool["id"]: tool for tool in listed.json()}
    assert WORKSPACE_TOOLS <= set(tools)
    assert tools["edit_file"]["category"] == "files"
    assert tools["edit_file"]["requires_approval"] is True
    assert tools["edit_file"]["input_schema"]["required"] == ["path", "old_text", "new_text"]
    assert tools["delete_file"]["input_schema"]["properties"]["confirm"]["type"] == "boolean"
    assert tools["create_repository"]["category"] == "projects"
    assert tools["create_repository"]["requires_approval"] is True
    assert tools["create_repository"]["input_schema"]["required"] == ["name"]
    assert "react-vite" in tools["create_repository"]["input_schema"]["properties"]["template"]["enum"]
    assert CODING_POWER_TOOLS <= set(tools)
    assert len(tools) == 48
    assert tools["project_scan"]["category"] == "projects"
    assert tools["find_files"]["category"] == "files"
    assert tools["file_outline"]["category"] == "code"
    assert tools["project_checks"]["category"] == "code"
    assert tools["secret_scan"]["category"] == "code"
    assert tools["secret_scan"]["requires_approval"] is False
    assert tools["release_readiness"]["category"] == "projects"
    assert tools["release_readiness"]["requires_approval"] is False
    assert tools["changelog_draft"]["category"] == "projects"
    assert tools["changelog_draft"]["requires_approval"] is False
    for tool_id in APPROVAL_GATED_POWER_TOOLS:
        assert tools[tool_id]["category"] == "files"
        assert tools[tool_id]["requires_approval"] is True
    for tool_id in CODING_POWER_TOOLS - APPROVAL_GATED_POWER_TOOLS:
        assert tools[tool_id]["requires_approval"] is False

    approvals = client.get("/v1/tools/approvals", headers=ADMIN_AUTH)
    assert approvals.status_code == 200
    approval_map = {item["tool_id"]: item["approved"] for item in approvals.json()}
    assert approval_map["edit_file"] is False
    assert approval_map["create_repository"] is False
    for tool_id in APPROVAL_GATED_POWER_TOOLS:
        assert approval_map[tool_id] is False

    forbidden_grant = client.post(
        "/v1/tools/approvals/grant", headers=USER_AUTH, json={"tool_ids": ["edit_file"]}
    )
    assert forbidden_grant.status_code == 403

    granted = client.post(
        "/v1/tools/approvals/grant",
        headers=ADMIN_AUTH,
        json={
            "tool_ids": [
                "write_file",
                "edit_file",
                "delete_file",
                "create_directory",
                "create_repository",
            ]
        },
    )
    assert granted.status_code == 200
    assert {item["tool_id"] for item in granted.json()} == WORKSPACE_TOOLS
    approvals = client.get("/v1/tools/approvals", headers=ADMIN_AUTH)
    approval_map = {item["tool_id"]: item["approved"] for item in approvals.json()}
    assert approval_map["delete_file"] is True
    assert approval_map["create_repository"] is True

    bad_grant = client.post(
        "/v1/tools/approvals/grant", headers=ADMIN_AUTH, json={"tool_ids": ["read_file"]}
    )
    assert bad_grant.status_code == 400

    forbidden_execute = client.post(
        "/v1/tools/execute",
        headers=USER_AUTH,
        json={"tool_id": "calculator", "params": {"expression": "2+2"}},
    )
    assert forbidden_execute.status_code == 403

    executed = client.post(
        "/v1/tools/execute",
        headers=ADMIN_AUTH,
        json={"tool_id": "calculator", "params": {"expression": "2+2"}},
    )
    assert executed.status_code == 200
    assert executed.json() == {
        "tool_id": "calculator",
        "result": {"ok": True, "result": "tool-executed"},
    }
    assert fake.executor.executed == ["calculator"]
