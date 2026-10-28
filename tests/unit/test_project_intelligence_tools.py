"""Project-intelligence tool coverage.

The release/security helpers are deliberately read-only: they should expose
enough evidence to make a ship/no-ship decision, draft release notes from real
Git history, and never print a full suspected secret.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.application.cortex.react_prompt import REACT_SYSTEM_PROMPT
from nexus.domain.value_objects.solution_brief import detect_read_only_tool_call
from nexus.infrastructure.adapters.execution.builtin_tools import default_builtin_tools
from nexus.infrastructure.adapters.execution.extended_tools import (
    EXTENDED_HANDLERS,
    TOOL_DEFS,
)
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider

PROJECT_INTELLIGENCE_TOOLS = {"secret_scan", "release_readiness", "changelog_draft"}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_git(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "nexus-test@example.com")
    _git(root, "config", "user.name", "Nexus Test")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "sample-project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "README.md").write_text("# Sample Project\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools>=68"]

[project]
name = "sample-project"
version = "0.1.0"
dependencies = []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "src" / "app.py").write_text(
        """from __future__ import annotations


class Calculator:
    def add(self, left: int, right: int) -> int:
        return left + right
""",
        encoding="utf-8",
    )
    (root / "tests" / "test_app.py").write_text(
        """from src.app import Calculator


def test_add() -> None:
    assert Calculator().add(2, 3) == 5
""",
        encoding="utf-8",
    )
    return root


def test_project_intelligence_tools_are_registered_and_prompted() -> None:
    defined = {definition["id"] for definition in TOOL_DEFS}
    registered = {tool.id for tool in default_builtin_tools()}

    assert PROJECT_INTELLIGENCE_TOOLS <= defined
    assert PROJECT_INTELLIGENCE_TOOLS <= registered
    assert PROJECT_INTELLIGENCE_TOOLS <= set(EXTENDED_HANDLERS)
    assert len(registered) == 48
    assert len(EXTENDED_HANDLERS) == 48
    for tool_id in PROJECT_INTELLIGENCE_TOOLS:
        assert f'"tool_id": "{tool_id}"' in REACT_SYSTEM_PROMPT
    assert "never print a full suspected secret" in REACT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_secret_scan_redacts_findings_and_skips_denylisted_files(project: Path) -> None:
    fake_secret = "sk-live-1234567890abcdef1234"
    env_secret = "env-secret-that-must-not-appear"
    (project / "src" / "config.py").write_text(
        f'API_KEY = "{fake_secret}"\n'
        'SAFE_TOKEN = "change-me-please"\n'
        'DATABASE_PASSWORD = "correct horse battery staple"\n',
        encoding="utf-8",
    )
    (project / ".env").write_text(f"API_KEY={env_secret}\n", encoding="utf-8")

    result = await EXTENDED_HANDLERS["secret_scan"]({"path": str(project)})

    assert result["clean"] is False
    assert result["risk_level"] == "high"
    assert result["files_with_findings"] == 1
    assert {item["file"] for item in result["findings"]} == {"src/config.py"}
    assert {item["line"] for item in result["findings"]} == {1, 3}
    rendered = json.dumps(result)
    assert fake_secret not in rendered
    assert env_secret not in rendered
    assert "change-me-please" not in rendered
    assert any("***" in item["redacted_preview"] for item in result["findings"])


@pytest.mark.asyncio
async def test_release_readiness_clean_project_and_secret_blocker(project: Path) -> None:
    _init_git(project)
    _git(project, "add", ".")
    _git(project, "commit", "-q", "-m", "feat: add calculator")

    clean = await EXTENDED_HANDLERS["release_readiness"](
        {"path": str(project), "include_checks": True, "checks": ["python_compile"]}
    )
    assert clean["ready"] is True
    assert clean["status"] == "ready"
    assert clean["score"] == 100
    assert clean["blockers"] == []
    assert clean["warnings"] == []
    assert clean["git"]["clean"] is True
    assert clean["secrets"]["clean"] is True
    assert clean["checks_passed"] is True

    (project / "src" / "config.py").write_text(
        'API_KEY = "sk-live-1234567890abcdef1234"\n', encoding="utf-8"
    )
    blocked = await EXTENDED_HANDLERS["release_readiness"]({"path": str(project)})
    blocker_codes = {item["code"] for item in blocked["blockers"]}

    assert blocked["ready"] is False
    assert blocked["status"] == "not_ready"
    assert {"likely_secrets", "uncommitted_changes"} <= blocker_codes
    assert any("secret" in action.lower() for action in blocked["recommended_next_actions"])
    assert "sk-live-1234567890abcdef1234" not in json.dumps(blocked)


@pytest.mark.asyncio
async def test_changelog_draft_groups_conventional_commits(project: Path) -> None:
    _init_git(project)
    _git(project, "add", ".")
    _git(project, "commit", "-q", "-m", "feat: add calculator")

    app_path = project / "src" / "app.py"
    app_path.write_text(
        app_path.read_text(encoding="utf-8") + "\n# Handles normal integer inputs.\n",
        encoding="utf-8",
    )
    _git(project, "add", "src/app.py")
    _git(project, "commit", "-q", "-m", "fix: handle normal integer inputs")

    limited = await EXTENDED_HANDLERS["changelog_draft"](
        {"repo_path": str(project), "from_ref": "HEAD~1", "max_commits": 10}
    )
    assert limited["commit_count"] == 1
    assert limited["categories"] == {"Fixed": 1}

    (project / "notes.txt").write_text("not committed yet\n", encoding="utf-8")
    draft = await EXTENDED_HANDLERS["changelog_draft"](
        {"repo_path": str(project), "max_commits": 10, "include_uncommitted": True}
    )

    assert draft["commit_count"] == 2
    assert draft["categories"] == {"Added": 1, "Fixed": 1}
    assert "src/app.py" in draft["files_changed"]
    assert draft["uncommitted_files"] == ["notes.txt"]
    assert "## Added" in draft["markdown"]
    assert "add calculator" in draft["markdown"]
    assert "## Fixed" in draft["markdown"]
    assert "Uncommitted work" in draft["markdown"]


def test_simulation_routes_and_formats_project_intelligence_tools() -> None:
    secret = detect_read_only_tool_call("Scan this project for leaked secrets")
    assert secret is not None
    assert secret.tool_id == "secret_scan"
    assert secret.params()["path"] == "."

    release = detect_read_only_tool_call("Is this project ready to release?")
    assert release is not None
    assert release.tool_id == "release_readiness"
    assert release.params()["include_checks"] is False

    changelog = detect_read_only_tool_call("Draft release notes since v1.2.0")
    assert changelog is not None
    assert changelog.tool_id == "changelog_draft"
    assert changelog.params()["from_ref"] == "v1.2.0"

    project_scan = detect_read_only_tool_call("Scan the project")
    assert project_scan is not None
    assert project_scan.tool_id == "project_scan"
    git_diff = detect_read_only_tool_call("What changed in git?")
    assert git_diff is not None
    assert git_diff.tool_id == "git_diff"

    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")
    response = provider._simulated_response(
        [
            {"role": "system", "content": "Use FINAL ANSWER when done."},
            {"role": "user", "content": "Is this project ready to ship?"},
        ]
    )
    assert response.startswith("TOOL_CALL:")
    payload = json.loads(response.removeprefix("TOOL_CALL:").strip())
    assert payload["tool_id"] == "release_readiness"

    secret_answer = provider._deterministic_tool_result_answer(
        "secret_scan",
        repr(
            {
                "clean": False,
                "risk_level": "high",
                "files_scanned": 3,
                "files_with_findings": 1,
                "findings": [
                    {
                        "file": "src/config.py",
                        "line": 1,
                        "kind": "credential_assignment",
                        "severity": "high",
                        "redacted_preview": "sk-***34 (28 chars)",
                    }
                ],
            }
        ),
        "Scan for secrets",
    )
    assert "redacted" in secret_answer
    assert "sk-***34" in secret_answer

    release_answer = provider._deterministic_tool_result_answer(
        "release_readiness",
        repr(
            {
                "ready": False,
                "status": "not_ready",
                "score": 54,
                "summary": "Release readiness: not_ready; score 54/100; 1 blocker(s), 0 warning(s).",
                "blockers": [
                    {
                        "code": "likely_secrets",
                        "message": "High-confidence likely secrets were found",
                        "count": 1,
                    }
                ],
                "warnings": [],
                "diagnostics": {"errors": 0, "files_scanned": 3},
                "secrets": {"risk_level": "high"},
                "git": {"is_git_repository": True, "branch": "main", "changed_count": 0},
                "dependencies": {"undeclared": []},
                "checks_run": False,
                "recommended_next_actions": ["Remove likely secrets from source."],
            }
        ),
        "Is this ready to release?",
    )
    assert "Blockers" in release_answer
    assert "project checks were not run" in release_answer

    changelog_answer = provider._deterministic_tool_result_answer(
        "changelog_draft",
        repr({"markdown": "# Changelog draft\n\n## Added\n\n- add calculator (`abc123`)\n"}),
        "Draft a changelog",
    )
    assert changelog_answer.startswith("# Changelog draft")

    reconstructed = provider._deterministic_tool_result_answer(
        "changelog_draft",
        repr(
            {
                "range": "HEAD",
                "commit_count": 1,
                "_partial_observation": True,
                "commits": [
                    {
                        "hash": "abc123",
                        "subject": "feat: add calculator",
                        "display": "add calculator",
                        "category": "Added",
                        "breaking": False,
                    }
                ],
            }
        ),
        "Draft a changelog",
    )
    assert "## Added" in reconstructed
    assert "add calculator (`abc123`)" in reconstructed
    assert "bounded tool observation" in reconstructed
