"""Keep runtime imports and dependency manifests synchronized."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / "src" / "nexus" / "infrastructure" / "adapters" / "execution" / "registry_tool_executor.py"


def _runtime_package_names() -> set[str]:
    requirements = (ROOT / "requirements.in").read_text(encoding="utf-8")
    return {
        re.split(r"[<>=!~\[]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _runtime_project_package_names() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        re.split(r"[<>=!~\[]", dependency, maxsplit=1)[0].lower().replace("_", "-")
        for dependency in project["project"]["dependencies"]
    }


def _imported_external_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported - set(sys.stdlib_module_names) - {"nexus"}


def test_registry_tool_executor_imports_are_declared() -> None:
    declared = _runtime_package_names()
    undeclared = _imported_external_modules(EXECUTOR) - declared
    assert not undeclared, f"Undeclared runtime imports in {EXECUTOR.name}: {sorted(undeclared)}"


def test_aiohttp_is_a_runtime_dependency_in_both_sources() -> None:
    assert "aiohttp" in _runtime_package_names()
    assert "aiohttp" in _runtime_project_package_names()


def test_aiohttp_is_in_linux_py311_runtime_lock() -> None:
    lock = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert (
        "uv pip compile requirements.in -o requirements.txt --python-platform linux --python-version 3.11"
        in lock
    )
    assert re.search(r"(?m)^aiohttp==[\d.]+", lock)


def test_dev_lock_uses_updated_runtime_lock_constraints() -> None:
    lock = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert (
        "uv pip compile requirements-dev.in -o requirements-dev.txt --python-platform linux --python-version 3.11"
        in lock
    )
    assert "-c requirements.txt" in (ROOT / "requirements-dev.in").read_text(encoding="utf-8")
