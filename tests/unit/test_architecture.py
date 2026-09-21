"""
Architecture guard - mechanically enforce the dependency rule.

The README promises the dependency rule is "verified by tests". These tests
are that promise: they parse every module under src/nexus with the ast module
(no imports executed) and fail if a layer reaches past its boundary.

    domain       -> may not import nexus.application or nexus.infrastructure
    application  -> may not import nexus.infrastructure

Infrastructure is free to import both - it is the outside of the onion.
If you are reading this because it failed: do not add the import. Declare a
port in domain, implement it in infrastructure, and inject it from the
DI container (src/nexus/infrastructure/di/container.py).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NEXUS_ROOT = REPO_ROOT / "src" / "nexus"


def _collect_imports(package: Path) -> dict[Path, set[str]]:
    """Map every module in `package` to the absolute module names it imports.

    Relative imports (level > 0) stay inside the package by definition and
    are ignored. Imports guarded by `if TYPE_CHECKING:` are collected too -
    the dependency rule applies to type-only coupling as well.
    """
    imports: dict[Path, set[str]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
        imports[path] = names
    return imports


def _violations(package: Path, forbidden: tuple[str, ...]) -> list[str]:
    """Modules in `package` importing any of the forbidden module prefixes."""
    bad: list[str] = []
    for path, names in _collect_imports(package).items():
        for name in sorted(names):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                bad.append(f"{path.relative_to(REPO_ROOT)} -> {name}")
    return bad


def test_domain_never_imports_application_or_infrastructure() -> None:
    assert (
        _violations(
            NEXUS_ROOT / "domain",
            ("nexus.application", "nexus.infrastructure"),
        )
        == []
    )


def test_application_never_imports_infrastructure() -> None:
    assert _violations(NEXUS_ROOT / "application", ("nexus.infrastructure",)) == []
