"""Fast coding/workspace power-tool coverage.

These tests exercise the tools Nexus uses for work larger than scaffolding a
repository: mapping an existing project, finding code and problems, editing
or reorganizing many files safely, and verifying the result.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.application.cortex.react_prompt import REACT_SYSTEM_PROMPT
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.execution.builtin_tools import (
    BuiltinToolRegistry,
    default_builtin_tools,
)
from nexus.infrastructure.adapters.execution.extended_tools import (
    _REPOSITORY_RUN_COMMANDS,
    _REPOSITORY_TEMPLATE_DETAILS,
    _REPOSITORY_TEMPLATES,
    EXTENDED_HANDLERS,
    TOOL_DEFS,
    _repository_files,
    set_autonomy_policy,
)
from nexus.infrastructure.adapters.execution.registry_tool_executor import (
    RegistryBackedToolExecutor,
)
from nexus.infrastructure.adapters.security.in_memory_rate_limiter import InMemoryRateLimiter
from tests.fakes import FakeSandbox

READ_TOOLS = {
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
}
MUTATION_TOOLS = {
    "write_files",
    "batch_edit_files",
    "move_path",
    "copy_path",
    "delete_directory",
}
POWER_TOOLS = READ_TOOLS | MUTATION_TOOLS


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "sample-project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules" / "ignored").mkdir(parents=True)
    (root / "package.json").write_text(
        """{
  "name": "sample-project",
  "private": true,
  "scripts": {"dev": "vite", "lint": "tsc --noEmit", "build": "vite build"},
  "dependencies": {"react": "^19.0.0"},
  "devDependencies": {"vite": "^6.0.0"}
}
""",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools>=68"]

[project]
name = "sample-project"
version = "0.1.0"
dependencies = ["fastapi>=0.110"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "src" / "app.py").write_text(
        """from __future__ import annotations


class Calculator:
    def add(self, left: int, right: int) -> int:
        return left + right


def build_calculator() -> Calculator:
    return Calculator()
""",
        encoding="utf-8",
    )
    (root / "src" / "util.py").write_text(
        """from app import Calculator


def total() -> int:
    return Calculator().add(2, 3)
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
    (root / "README.md").write_text("# Sample Project\n", encoding="utf-8")
    (root / "node_modules" / "ignored" / "broken.py").write_text("def ignored(:\n", encoding="utf-8")
    return root


@pytest.fixture
def policy():
    instance = DefaultAutonomyPolicy(rate_limiter=InMemoryRateLimiter(), allowlist=[])
    set_autonomy_policy(instance)
    try:
        yield instance
    finally:
        set_autonomy_policy(None)


def _executor(policy: DefaultAutonomyPolicy) -> RegistryBackedToolExecutor:
    return RegistryBackedToolExecutor(
        BuiltinToolRegistry(default_builtin_tools()),
        FakeSandbox(),
        dict(EXTENDED_HANDLERS),
        autonomy_policy=policy,
    )


def test_coding_power_tools_are_registered_and_prompted() -> None:
    defined = {definition["id"] for definition in TOOL_DEFS}
    registered = {tool.id for tool in default_builtin_tools()}

    assert POWER_TOOLS <= defined
    assert POWER_TOOLS <= registered
    assert POWER_TOOLS <= set(EXTENDED_HANDLERS)
    assert len(registered) == 48
    for tool_id in POWER_TOOLS:
        assert f'"tool_id": "{tool_id}"' in REACT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_fast_project_intelligence_tools(project: Path) -> None:
    scan = await EXTENDED_HANDLERS["project_scan"]({"path": str(project)})
    assert scan["files"] >= 5
    assert scan["test_files"] == 1
    assert {"React", "Vite", "FastAPI"} <= set(scan["frameworks"])
    assert any(item["path"] == "package.json" for item in scan["manifests"])
    assert any("npm run lint" in command for command in scan["suggested_commands"])
    assert all("node_modules" not in item["path"] for item in scan["largest_files"])

    found = await EXTENDED_HANDLERS["find_files"]({"path": str(project), "pattern": "*.py", "sort": "path"})
    found_paths = {item["path"] for item in found["files"]}
    assert {"src/app.py", "src/util.py", "tests/test_app.py"} <= found_paths
    assert all("node_modules" not in path for path in found_paths)

    tree = await EXTENDED_HANDLERS["directory_tree"](
        {"path": str(project), "max_depth": 3, "max_entries": 100}
    )
    assert "src/" in tree["tree"]
    assert "app.py" in tree["tree"]
    assert "node_modules" not in tree["tree"]

    reads = await EXTENDED_HANDLERS["read_files"](
        {
            "paths": [str(project / "src" / "app.py"), str(project / "src" / "util.py")],
            "start_line": 1,
            "end_line": 5,
        }
    )
    assert reads["failed"] == 0
    assert reads["read"] == 2
    assert "class Calculator" in reads["files"][0]["content"]

    outline = await EXTENDED_HANDLERS["file_outline"]({"path": str(project / "src" / "app.py")})
    symbols = {(item["name"], item["kind"]) for item in outline["symbols"]}
    assert ("Calculator", "class") in symbols
    assert ("add", "function") in symbols
    assert ("build_calculator", "function") in symbols

    symbol = await EXTENDED_HANDLERS["find_symbol"]({"symbol": "Calculator", "path": str(project)})
    assert any(item["file"].endswith("src/app.py") for item in symbol["definitions"])
    assert any(item["file"].endswith("src/util.py") for item in symbol["references"])

    grep = await EXTENDED_HANDLERS["grep"](
        {"pattern": "Calculator", "path": str(project), "include": "*.py", "max_results": 20}
    )
    assert grep["files_scanned"] >= 3
    assert grep["matches"]
    assert all("node_modules" not in item["file"] for item in grep["matches"])


@pytest.mark.asyncio
async def test_diagnostics_checks_and_git_diff(project: Path) -> None:
    clean = await EXTENDED_HANDLERS["code_diagnostics"]({"path": str(project)})
    assert clean["clean"] is True
    assert clean["errors"] == 0

    (project / "src" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (project / "src" / "bad.json").write_text("{not json}\n", encoding="utf-8")
    diagnostics = await EXTENDED_HANDLERS["code_diagnostics"]({"path": str(project / "src")})
    assert diagnostics["clean"] is False
    assert diagnostics["errors"] == 2
    assert {item["source"] for item in diagnostics["diagnostics"]} == {"python", "json"}
    (project / "src" / "broken.py").unlink()
    (project / "src" / "bad.json").unlink()

    checks = await EXTENDED_HANDLERS["project_checks"]({"path": str(project), "checks": ["python_compile"]})
    assert checks["passed"] is True
    assert checks["checks"][0]["files_checked"] >= 3

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Nexus Test"], cwd=project, check=True)
    subprocess.run(
        ["git", "add", "src/app.py", "src/util.py", "tests/test_app.py"],
        cwd=project,
        check=True,
    )
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=project, check=True)
    app_path = project / "src" / "app.py"
    app_path.write_text(
        app_path.read_text(encoding="utf-8").replace("left + right", "left + right + 0"),
        encoding="utf-8",
    )

    diff = await EXTENDED_HANDLERS["git_diff"]({"repo_path": str(project)})
    assert diff["clean"] is False
    assert diff["branch"] == "main"
    assert any(item["path"] == "src/app.py" for item in diff["changed_files"])
    assert "left + right + 0" in diff["diff"]


@pytest.mark.asyncio
async def test_batch_and_folder_mutations_are_approval_gated_and_atomic(
    project: Path, policy: DefaultAutonomyPolicy
) -> None:
    feature = project / "feature" / "new.py"
    write_params = {
        "files": [
            {"path": str(feature), "content": "VALUE = 1\n"},
            {"path": str(project / "feature" / "README.md"), "content": "# Feature\n"},
        ]
    }

    preview = await EXTENDED_HANDLERS["write_files"]({**write_params, "dry_run": True})
    assert preview["dry_run"] is True
    assert preview["files_written"] == 0
    assert not feature.exists()

    blocked = await EXTENDED_HANDLERS["write_files"](write_params)
    assert blocked["approval_required"] is True
    assert not feature.exists()

    # Existing one-file workspace grants intentionally authorize the batch
    # equivalent so the current chat's workspace toggle remains useful.
    await policy.grant_approval("tool:write_file", approver="admin", tenant_id="default")
    written = await EXTENDED_HANDLERS["write_files"](write_params)
    assert written["files_written"] == 2
    assert feature.read_text(encoding="utf-8") == "VALUE = 1\n"

    app_path = project / "src" / "app.py"
    util_path = project / "src" / "util.py"
    original_app = app_path.read_text(encoding="utf-8")
    original_util = util_path.read_text(encoding="utf-8")
    invalid_batch = {
        "edits": [
            {"path": str(app_path), "old_text": "left + right", "new_text": "left - right"},
            {"path": str(util_path), "old_text": "missing text", "new_text": "x"},
        ]
    }
    failed = await EXTENDED_HANDLERS["batch_edit_files"](invalid_batch)
    assert "not found" in failed["error"]
    assert app_path.read_text(encoding="utf-8") == original_app
    assert util_path.read_text(encoding="utf-8") == original_util

    edit_preview = await EXTENDED_HANDLERS["batch_edit_files"](
        {
            "dry_run": True,
            "edits": [
                {"path": str(feature), "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                {"path": str(util_path), "old_text": "add(2, 3)", "new_text": "add(4, 5)"},
            ],
        }
    )
    assert edit_preview["dry_run"] is True
    assert edit_preview["replacements"] == 2
    assert feature.read_text(encoding="utf-8") == "VALUE = 1\n"

    blocked_edit = await EXTENDED_HANDLERS["batch_edit_files"](
        {
            "edits": [
                {"path": str(feature), "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                {"path": str(util_path), "old_text": "add(2, 3)", "new_text": "add(4, 5)"},
            ]
        }
    )
    assert blocked_edit["approval_required"] is True
    assert feature.read_text(encoding="utf-8") == "VALUE = 1\n"

    await policy.grant_approval("tool:edit_file", approver="admin", tenant_id="default")
    edited = await EXTENDED_HANDLERS["batch_edit_files"](
        {
            "edits": [
                {"path": str(feature), "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                {"path": str(util_path), "old_text": "add(2, 3)", "new_text": "add(4, 5)"},
            ]
        }
    )
    assert edited["replacements"] == 2
    assert feature.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert "add(4, 5)" in util_path.read_text(encoding="utf-8")

    copied = await EXTENDED_HANDLERS["copy_path"](
        {"source": str(project / "feature"), "destination": str(project / "feature-copy")}
    )
    assert copied["copied"] is True
    assert copied["files"] == 2
    assert (project / "feature-copy" / "new.py").exists()

    moved = await EXTENDED_HANDLERS["move_path"](
        {
            "source": str(project / "feature-copy"),
            "destination": str(project / "renamed-feature"),
        }
    )
    assert moved["moved"] is True
    assert not (project / "feature-copy").exists()
    assert (project / "renamed-feature" / "new.py").exists()

    blocked_delete = await EXTENDED_HANDLERS["delete_directory"](
        {"path": str(project / "renamed-feature"), "confirm": True, "recursive": True}
    )
    assert blocked_delete["approval_required"] is True
    assert (project / "renamed-feature").exists()

    await policy.grant_approval("tool:delete_file", approver="admin", tenant_id="default")
    deleted = await EXTENDED_HANDLERS["delete_directory"](
        {"path": str(project / "renamed-feature"), "confirm": True, "recursive": True}
    )
    assert deleted["deleted"] is True
    assert deleted["files_deleted"] == 2
    assert not (project / "renamed-feature").exists()


@pytest.mark.asyncio
async def test_executor_normalizes_power_tool_aliases_and_dry_runs(
    project: Path, policy: DefaultAutonomyPolicy
) -> None:
    executor = _executor(policy)
    feature = project / "src" / "feature.py"
    feature.write_text("answer = 41\n", encoding="utf-8")

    preview = await executor.execute(
        "batch_edit_files",
        {
            "changes": [
                {
                    "filename": str(feature),
                    "search": "answer = 41",
                    "replacement": "answer = 42",
                }
            ],
            "dry_run": True,
        },
    )
    assert preview["dry_run"] is True
    assert preview["replacements"] == 1
    assert feature.read_text(encoding="utf-8") == "answer = 41\n"

    target = project / "generated" / "one.py"
    blocked = await executor.execute(
        "write_files",
        {"path": str(target), "content": "print('ok')\n"},
    )
    assert blocked["approval_required"] is True
    assert not target.exists()

    await policy.grant_approval("tool:write_file", approver="admin", tenant_id="default")
    created = await executor.execute(
        "write_files",
        {"path": str(target), "content": "print('ok')\n"},
    )
    assert created["files_written"] == 1
    assert target.exists()

    moved = await executor.execute(
        "move_path",
        {"from": str(target), "to": str(project / "generated" / "moved.py")},
    )
    assert moved["moved"] is True
    assert (project / "generated" / "moved.py").exists()


@pytest.mark.asyncio
async def test_polyglot_diagnostics_cover_frontend_xml_and_native_code(tmp_path: Path) -> None:
    root = tmp_path / "polyglot"
    (root / "src").mkdir(parents=True)
    (root / "web").mkdir()
    (root / "src" / "main.c").write_text(
        '#include <stdio.h>\nint main(void) { puts("ok"); return 0; }\n',
        encoding="utf-8",
    )
    (root / "src" / "widget.cpp").write_text(
        "#include <memory>\nstruct Widget { int value() const { return 42; } };\n",
        encoding="utf-8",
    )
    (root / "src" / "main.rs").write_text("fn main() { println!(\"ok\"); }\n", encoding="utf-8")
    (root / "src" / "index.php").write_text("<?php declare(strict_types=1); echo 'ok';\n", encoding="utf-8")
    (root / "src" / "tool.rb").write_text("# frozen_string_literal: true\nputs 'ok'\n", encoding="utf-8")
    (root / "web" / "index.html").write_text(
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OK</title></head>
<body><main><h1>OK</h1><form><label for="email">Email</label><input id="email" type="email"></form></main></body></html>
""",
        encoding="utf-8",
    )
    (root / "web" / "styles.css").write_text(
        ":root { --space: 1rem; }\n:focus-visible { outline: 3px solid currentColor; }\n"
        "@media (max-width: 40rem) { main { padding: var(--space); } }\n",
        encoding="utf-8",
    )
    (root / "data.xml").write_text('<?xml version="1.0"?><catalog><book id="1"/></catalog>\n', encoding="utf-8")

    result = await EXTENDED_HANDLERS["code_diagnostics"]({"path": str(root)})

    assert result["clean"] is True, result["diagnostics"]
    assert result["errors"] == 0
    languages = {item["language"] for item in result["languages"]}
    assert {"C", "C++", "Rust", "PHP", "Ruby", "HTML5", "CSS", "XML"} <= languages
    assert {"C", "C++"} <= set(result["native_checks"])
    if not __import__("shutil").which("php"):
        assert any("PHP: php not installed" in item for item in result["native_checks_skipped"])
    if not __import__("shutil").which("ruby"):
        assert any("Ruby: ruby not installed" in item for item in result["native_checks_skipped"])

    (root / "data.xml").write_text("<catalog><book></catalog>\n", encoding="utf-8")
    (root / "web" / "index.html").write_text(
        '<html><body><img src="x.png"><input placeholder="Email"></body></html>\n',
        encoding="utf-8",
    )
    broken = await EXTENDED_HANDLERS["code_diagnostics"]({"path": str(root), "include_native": False})
    sources = {item["source"] for item in broken["diagnostics"]}
    assert broken["clean"] is False
    assert "xml" in sources
    assert "accessibility" in sources


@pytest.mark.asyncio
async def test_polyglot_project_checks_and_scan(tmp_path: Path) -> None:
    root = tmp_path / "native-project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "math.c").write_text("int add(int a, int b) { return a + b; }\n", encoding="utf-8")
    (root / "src" / "math.cpp").write_text("int add_cpp(int a, int b) { return a + b; }\n", encoding="utf-8")
    (root / "tests" / "test_math.c").write_text(
        '#include <assert.h>\nint add(int, int);\nint main(void) { assert(add(2, 3) == 5); return 0; }\n',
        encoding="utf-8",
    )
    (root / "Makefile").write_text(
        "CC = cc\nCFLAGS = -std=c17 -Wall -Wextra -Wpedantic\n\n"
        "test: build/test_math\n\t./build/test_math\n\n"
        "build/test_math: src/math.c tests/test_math.c\n"
        "\tmkdir -p build\n\t$(CC) $(CFLAGS) src/math.c tests/test_math.c -o build/test_math\n",
        encoding="utf-8",
    )
    (root / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\nserde = "1"\n',
        encoding="utf-8",
    )
    (root / "composer.json").write_text(
        '{"name":"demo/app","require":{"php":">=8.2"},"scripts":{"test":"php tests/run.php"}}\n',
        encoding="utf-8",
    )
    (root / "Gemfile").write_text('source "https://rubygems.org"\ngem "minitest"\n', encoding="utf-8")
    (root / "src" / "index.php").write_text("<?php declare(strict_types=1); echo 'ok';\n", encoding="utf-8")
    (root / "src" / "tool.rb").write_text("# frozen_string_literal: true\nputs 'ok'\n", encoding="utf-8")
    (root / "data.xml").write_text("<root><value>ok</value></root>\n", encoding="utf-8")

    scan = await EXTENDED_HANDLERS["project_scan"]({"path": str(root)})
    assert {"Cargo", "Composer", "Bundler"} <= set(scan["frameworks"])
    assert {"c_syntax", "cargo_test", "php_lint", "ruby_syntax", "xml_validate"} <= set(scan["recommended_checks"])
    cargo_manifest = next(item for item in scan["manifests"] if item["kind"] == "Cargo.toml")
    assert cargo_manifest["dependencies"] == ["serde"]

    checks = await EXTENDED_HANDLERS["project_checks"](
        {
            "path": str(root),
            "checks": ["c_syntax", "cpp_syntax", "make_test", "xml_validate"],
            "timeout": 30,
        }
    )
    by_name = {item["name"]: item for item in checks["checks"]}
    assert by_name["c_syntax"]["passed"] is True, by_name["c_syntax"]
    assert by_name["cpp_syntax"]["passed"] is True, by_name["cpp_syntax"]
    assert by_name["make_test"]["passed"] is True, by_name["make_test"]
    assert by_name["xml_validate"]["passed"] is True

    missing = await EXTENDED_HANDLERS["project_checks"](
        {"path": str(root), "checks": ["cargo_test", "php_lint", "ruby_syntax"]}
    )
    missing_by_name = {item["name"]: item for item in missing["checks"]}
    import shutil

    if not shutil.which("cargo"):
        assert missing_by_name["cargo_test"]["tool_available"] is False
    if not shutil.which("php"):
        assert missing_by_name["php_lint"]["tool_available"] is False
    if not shutil.which("ruby"):
        assert missing_by_name["ruby_syntax"]["tool_available"] is False


@pytest.mark.asyncio
async def test_polyglot_and_frontend_file_outlines(tmp_path: Path) -> None:
    root = tmp_path / "outlines"
    root.mkdir()
    files = {
        "main.cpp": '#include <string>\nclass Greeter { public: std::string label() const; };\nint add(int a, int b) { return a + b; }\n',
        "index.php": "<?php\ndeclare(strict_types=1);\nnamespace Demo;\nuse Demo\\Support\\Helper;\nfinal class Page\n{\n    public function render(): string\n    {\n        return 'ok';\n    }\n}\n",
        "tool.rb": "# frozen_string_literal: true\nrequire_relative 'helper'\nmodule Demo\n  class Tool\n    def run; end\n  end\nend\n",
        "lib.rs": "use std::fmt;\npub struct Item;\npub fn build_item() -> Item { Item }\n",
        "index.html": '<!doctype html><html lang="en"><head><title>Demo</title><link rel="stylesheet" href="styles.css"></head><body><main id="app"><h1>Demo</h1><label for="name">Name</label><input id="name"></main></body></html>\n',
        "data.xml": '<catalog><book><title>Demo</title></book></catalog>\n',
        "styles.css": ":root { --brand: #336699; }\n.card { padding: 1rem; }\n@media (max-width: 40rem) { .card { padding: .5rem; } }\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")

    expected = {
        "main.cpp": {"Greeter", "add"},
        "index.php": {"Page", "render"},
        "tool.rb": {"Demo", "Tool", "run"},
        "lib.rs": {"Item", "build_item"},
        "index.html": {"Demo", "main: app", "name"},
        "data.xml": {"catalog", "book", "title"},
        "styles.css": {":root", ".card", "--brand"},
    }
    for name, symbols_expected in expected.items():
        outline = await EXTENDED_HANDLERS["file_outline"]({"path": str(root / name)})
        names = {str(item["name"]) for item in outline["symbols"]}
        assert symbols_expected <= names, (name, outline)

    unsafe = root / "unsafe.xml"
    unsafe.write_text(
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><x>&xxe;</x>\n',
        encoding="utf-8",
    )
    outline = await EXTENDED_HANDLERS["file_outline"]({"path": str(unsafe)})
    assert "external identifier" in outline["error"]


@pytest.mark.asyncio
async def test_frontend_and_polyglot_repository_templates_are_clean(tmp_path: Path) -> None:
    create_tool = next(item for item in TOOL_DEFS if item["id"] == "create_repository")
    enum_templates = set(create_tool["input"]["template"]["enum"])
    assert enum_templates == set(_REPOSITORY_TEMPLATES)
    assert set(_REPOSITORY_TEMPLATE_DETAILS) == set(_REPOSITORY_TEMPLATES)
    assert set(_REPOSITORY_RUN_COMMANDS) == set(_REPOSITORY_TEMPLATES)

    expected_files = {
        "frontend-design-system": {
            "src/App.tsx",
            "src/components/Button.tsx",
            "src/components/TextField.tsx",
            "src/index.css",
        },
        "html5-clean-ui": {"index.html", "styles.css", "script.js", "tests/smoke.test.mjs"},
        "c-cmake": {"CMakeLists.txt", "Makefile", "src/main.c", "tests/test_math.c"},
        "cpp-cmake": {"CMakeLists.txt", "Makefile", "src/main.cpp", "tests/test_math.cpp"},
        "rust-cli": {"Cargo.toml", "src/lib.rs", "src/main.rs", "tests/cli.rs"},
        "php-web": {"composer.json", "public/index.php", "src/Greeting.php", "tests/run.php"},
        "ruby-cli": {"Gemfile", "Rakefile", "lib/demo_tool.rb", "test/test_demo_tool.rb"},
        "xml-toolkit": {"data/catalog.xml", "schema/catalog.xsd", "src/xml_toolkit.py", "tests/test_xml_toolkit.py"},
    }
    generated_roots: dict[str, Path] = {}
    for template, expected in expected_files.items():
        files = _repository_files(template, "demo-tool", "A polished demo project.", "MIT", True)
        assert expected <= set(files), template
        assert "Template highlights" in files["README.md"]
        assert files[".github/workflows/ci.yml"]
        root = tmp_path / template
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        generated_roots[template] = root
        diagnostics = await EXTENDED_HANDLERS["code_diagnostics"]({"path": str(root)})
        assert diagnostics["errors"] == 0, (template, diagnostics["diagnostics"])

    for template in ("c-cmake", "cpp-cmake"):
        checks = await EXTENDED_HANDLERS["project_checks"](
            {"path": str(generated_roots[template]), "checks": ["make_test"], "timeout": 60}
        )
        assert checks["passed"] is True, checks

    frontend_checks = await EXTENDED_HANDLERS["project_checks"](
        {
            "path": str(generated_roots["html5-clean-ui"]),
            "checks": ["frontend_quality", "npm_test"],
            "timeout": 60,
        }
    )
    assert frontend_checks["passed"] is True, frontend_checks

    design_checks = await EXTENDED_HANDLERS["project_checks"](
        {"path": str(generated_roots["frontend-design-system"]), "checks": ["frontend_quality"]}
    )
    assert design_checks["passed"] is True, design_checks

    xml_checks = await EXTENDED_HANDLERS["project_checks"](
        {
            "path": str(generated_roots["xml-toolkit"]),
            "checks": ["xml_validate", "python_compile", "pytest"],
            "timeout": 60,
        }
    )
    assert xml_checks["passed"] is True, xml_checks

    import shutil

    missing_cases = {
        "rust-cli": ("cargo_test", "cargo"),
        "php-web": ("php_lint", "php"),
        "ruby-cli": ("ruby_syntax", "ruby"),
    }
    for template, (check, binary) in missing_cases.items():
        result = await EXTENDED_HANDLERS["project_checks"](
            {"path": str(generated_roots[template]), "checks": [check], "timeout": 60}
        )
        item = result["checks"][0]
        if shutil.which(binary):
            assert item["passed"] is True, item
        else:
            assert item["tool_available"] is False
