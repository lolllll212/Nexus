"""Clean Architecture and Hexagonal Boundary Verification.

Enforces that `src/nexus/domain/` has zero dependencies on:
1. `nexus.application` (use cases, application services)
2. `nexus.infrastructure` (adapters, API endpoints, DI container)
3. `nexus.training` (training CLI, dataset loaders)
4. Heavy infrastructure / network / database libraries (e.g. redis, neo4j, qdrant, openai, fastapi)

This test parses the AST of every Python file in the domain layer to guarantee
that domain independence is strictly maintained and fails locally before CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "nexus.application",
    "nexus.infrastructure",
    "nexus.training",
)

FORBIDDEN_THIRD_PARTY = {
    "redis",
    "neo4j",
    "qdrant_client",
    "openai",
    "fastapi",
    "starlette",
    "docker",
    "httpx",
    "requests",
    "sqlalchemy",
    "aiohttp",
}


def _get_domain_python_files() -> list[Path]:
    domain_root = Path(__file__).resolve().parents[2] / "src" / "nexus" / "domain"
    assert domain_root.exists() and domain_root.is_dir(), f"Domain path {domain_root} not found"
    return list(domain_root.rglob("*.py"))


def test_domain_files_exist():
    files = _get_domain_python_files()
    assert len(files) >= 20, f"Expected at least 20 domain files, found {len(files)}"


def test_domain_has_zero_imports_from_application_or_infrastructure():
    domain_files = _get_domain_python_files()
    violations: list[str] = []

    for file_path in domain_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        rel_path = file_path.relative_to(file_path.parents[3])

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_PREFIXES:
                        if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                            violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
                    top_module = alias.name.split(".")[0]
                    if top_module in FORBIDDEN_THIRD_PARTY:
                        violations.append(
                            f"{rel_path}:{node.lineno} imports forbidden infra library '{top_module}'"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in FORBIDDEN_PREFIXES:
                        if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                            violations.append(f"{rel_path}:{node.lineno} imports from '{node.module}'")
                    top_module = node.module.split(".")[0]
                    if top_module in FORBIDDEN_THIRD_PARTY:
                        violations.append(
                            f"{rel_path}:{node.lineno} imports forbidden infra library '{top_module}'"
                        )

                # Check relative imports don't escape domain
                if node.level > 0:
                    # e.g., in domain/entities/foo.py, level 1 = entities, level 2 = domain, level 3 escapes domain
                    # Let's verify by computing the parts
                    rel_parts = file_path.relative_to(
                        file_path.parents[2]
                    ).parts  # ('domain', 'entities', 'foo.py')
                    # Depth from inside domain: len(rel_parts) - 1. If level >= len(rel_parts), it escapes domain.
                    if node.level >= len(rel_parts):
                        violations.append(
                            f"{rel_path}:{node.lineno} relative import level {node.level} escapes nexus.domain"
                        )

    assert not violations, "Hexagonal architecture violation(s) in domain layer:\n" + "\n".join(violations)
