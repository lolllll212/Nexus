"""Keeps the ops env vars and the docs in agreement, in both directions.

`test_architecture_map.py` spot-checks a handful of env vars by hand, which is
how `NEXUS_QUOTA_*` and `NEXUS_GOALS_MAX_ACTIVE` shipped undocumented in the
first place: nobody wrote a test, so nobody noticed. This file makes the rule
generic instead of a checklist.

Two directions, deliberately asymmetric:

* A var the **code reads** must be **documented**. Reading it is an obligation
  to write it down - otherwise it is a knob only the author knows exists.
* A var the **docs mention** must be **known to the code**, checked as a string
  literal anywhere under `src/`. This direction is intentionally looser than
  the read patterns above, because a doc may legitimately mention a var that
  is consumed by something other than a plain `os.getenv` call (a secret-store
  indirection, a settings class). Being wrong here means a confusing failure;
  being wrong in the first direction means an undocumented knob ships.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
SCRIPTS = REPO_ROOT / "scripts"
DOCS = REPO_ROOT / "docs"

# HANDOFF.md is an append-only board quoting other agents' messages, so it is a
# record of what was once said rather than a statement about the system.
DOC_FILES = sorted(p for p in DOCS.glob("*.md") if p.name != "HANDOFF.md") + [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
]

# The only ways this codebase actually reads the environment. Tight on purpose:
# every hit becomes a documentation obligation, so a loose match here would
# demand docs for things that are not configuration.
ENV_READ = re.compile(
    r"(?:os\.getenv|os\.environ\.get|_parse_json_env)\(\s*[\"'](NEXUS_[A-Z0-9_]+)[\"']"
    r"|os\.environ\[\s*[\"'](NEXUS_[A-Z0-9_]+)[\"']"
)
# Any mention at all, used for the docs -> code direction.
ENV_LITERAL = re.compile(r"[\"'](NEXUS_[A-Z0-9_]+)[\"']")
# Bare mentions in prose, tables and shell examples. The trailing [A-Z0-9]\b is
# load-bearing: it stops `NEXUS_QUOTA_*` (a legitimate glob reference to a
# family) from being read as a var named `NEXUS_QUOTA_`.
ENV_MENTION = re.compile(r"\bNEXUS_[A-Z0-9_]*[A-Z0-9]\b")


def _src_files() -> list[Path]:
    """src/ plus the ops scripts - the daemon's knobs live in scripts/, and an
    env var read by an ops script is exactly as undocumented as one read by a
    module."""
    found = sorted(SRC.rglob("*.py")) + sorted(SCRIPTS.glob("*.py"))
    assert found, f"no python under {SRC} or {SCRIPTS} - the glob is wrong, not the codebase"
    return found


def _read_by_code() -> dict[str, set[str]]:
    """env var -> the files that read it."""
    found: dict[str, set[str]] = {}
    for path in _src_files():
        text = path.read_text(encoding="utf-8")
        for match in ENV_READ.finditer(text):
            name = match.group(1) or match.group(2)
            found.setdefault(name, set()).add(path.relative_to(REPO_ROOT).as_posix())
    return found


def _literal_in_code() -> set[str]:
    """Every NEXUS_* name that appears as a string literal anywhere under src/."""
    names: set[str] = set()
    for path in _src_files():
        names.update(ENV_LITERAL.findall(path.read_text(encoding="utf-8")))
    return names


def _mentioned_in_docs() -> dict[str, set[str]]:
    """env var -> the docs that mention it."""
    found: dict[str, set[str]] = {}
    for path in DOC_FILES:
        if not path.exists():
            continue
        for name in ENV_MENTION.findall(path.read_text(encoding="utf-8")):
            found.setdefault(name, set()).add(path.relative_to(REPO_ROOT).as_posix())
    return found


def test_the_scan_actually_finds_anything():
    """If the patterns rot, the two real tests below pass by finding nothing."""
    read = _read_by_code()
    assert len(read) >= 25, f"only found {len(read)} env reads; patterns are stale: {sorted(read)}"
    assert "NEXUS_API_KEYS" in read, "NEXUS_API_KEYS must be found - it is the auth contract"
    assert "NEXUS_INFRA_BACKEND" in read, "NEXUS_INFRA_BACKEND must be found - it selects adapters"


def test_env_vars_read_by_the_code_are_documented():
    """Reading a knob is an obligation to write it down."""
    documented = _mentioned_in_docs()
    undocumented = {
        name: sorted(readers) for name, readers in sorted(_read_by_code().items()) if name not in documented
    }
    assert not undocumented, (
        "env vars the code reads that no doc mentions - add them to the ops table in\n"
        "docs/architecture-map.md:\n"
        + "\n".join(f"  {name}  (read in {', '.join(where)})" for name, where in undocumented.items())
    )


def test_env_vars_mentioned_in_the_docs_exist_in_the_code():
    """A documented var that nothing reads is a promise the code does not keep."""
    known = _literal_in_code()
    ghosts = sorted(name for name in _mentioned_in_docs() if name not in known)
    assert (
        not ghosts
    ), "documented but never read anywhere in src/ - fix the doc or add the read:\n" + "\n".join(
        f"  {name}  (mentioned in {', '.join(sorted(_mentioned_in_docs()[name]))})" for name in ghosts
    )
