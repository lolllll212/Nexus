"""Launch the vendored REA MCP server over stdio.

NEXUS registers this module as the ``rea`` MCP server (alongside ``nexus``) in
``opencode.json``, ``.vscode/mcp.json`` and ``.agent/mcp_config.json``. REA is a
Node.js project, and ``node`` is frequently *not* on ``PATH`` on Windows (nvm /
standalone installs). This launcher locates a usable Node runtime, then hands the
process over to ``node vendor/rea/scripts/rea.mjs mcp`` with stdio inherited so
the JSON-RPC 2.0 stream passes through untouched.

It mirrors the existing ``python scripts/nexus_mcp.py`` convention, which keeps
MCP wiring portable instead of hard-coding an absolute ``node.exe`` path into the
agent configs.

Usage::

    python scripts/rea_mcp.py            # run the MCP server (stdio)
    python scripts/rea_mcp.py --doctor   # report node/entry/dist status
    python scripts/rea_mcp.py --print-command  # resolved argv as JSON
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REA_ROOT = REPO_ROOT / "vendor" / "rea"
REA_ENTRY = REA_ROOT / "scripts" / "rea.mjs"
REA_DIST = REA_ROOT / "dist" / "mcp" / "main.js"

# Explicit override, highest priority. Read via os.environ.get so the
# env-var docs guard picks it up (see tests/eval/test_docs_env_vars.py).
NODE_OVERRIDE_ENV = "NEXUS_REA_NODE"


def _candidate_nodes() -> list[Path]:
    """Best-effort Node locations when ``node`` is not on ``PATH``.

    Ordered most-specific first; ``find_node`` still prefers ``PATH`` before
    consulting these. Only well-known install layouts are probed - no disk walk.
    """
    candidates: list[Path] = []
    override = os.environ.get(NODE_OVERRIDE_ENV)
    if override:
        candidates.append(Path(override))

    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local)
        nvm = base / "nvm"
        if nvm.is_dir():
            # nvm-windows keeps one dir per version; try newest first.
            for version_dir in sorted((d for d in nvm.iterdir() if d.is_dir()), reverse=True):
                exe = version_dir / "node.exe"
                if exe.is_file():
                    candidates.append(exe)
        programs = base / "Programs"
        if programs.is_dir():
            for exe in sorted(programs.glob("nodejs*/**/node.exe")):
                candidates.append(exe)

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates.append(Path(program_files) / "nodejs" / "node.exe")
    candidates.append(Path(program_files_x86) / "nodejs" / "node.exe")
    return candidates


def find_node() -> str | None:
    """Return a path to an engine-compatible Node.js executable, or ``None``.

    REA declares ``engines: ^22.19.0 || ^24.11.0 || >=26.0.0`` and ships an
    ``engine-strict=true`` .npmrc, so 23.x/25.x break ``npm ci``. Compatible
    runtimes are therefore preferred; the first runtime found is only returned as
    a fallback so callers still get something actionable to report.
    """
    candidates: list[Path] = []
    for name in ("node", "node.exe"):
        which = shutil.which(name)
        if which:
            candidates.append(Path(which))
    candidates.extend(_candidate_nodes())

    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)

    fallback: str | None = None
    for candidate in ordered:
        if not candidate.is_file():
            continue
        if fallback is None:
            fallback = str(candidate)
        if _engine_compatible(_node_version(str(candidate))):
            return str(candidate)
    return fallback


def _engine_compatible(version: tuple[int, int, int] | None) -> bool:
    """True when ``version`` satisfies REA's engines range (23.x/25.x excluded)."""
    if version is None:
        return False
    major, minor, _patch = version
    return (major == 22 and minor >= 19) or (major == 24 and minor >= 11) or major >= 26


@lru_cache(maxsize=None)
def _node_version(exe: str) -> tuple[int, int, int] | None:
    """Probe ``node -v`` once per path; returns ``None`` when unreachable."""
    try:
        result = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", f"{result.stdout} {result.stderr}")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def resolve_command() -> list[str]:
    """The argv to run REA's MCP server, e.g. ``[node, rea.mjs, mcp]``.

    Raises ``RuntimeError`` with an actionable message when Node or the vendored
    entrypoint is missing, so ``--doctor`` and the MCP client both get a clear
    diagnosis instead of a bare traceback.
    """
    node = find_node()
    if not node:
        raise RuntimeError(
            "no Node.js runtime found. Install Node >=22.19 (https://nodejs.org) "
            f"or set {NODE_OVERRIDE_ENV} to a node.exe path."
        )
    if not REA_ENTRY.is_file():
        raise RuntimeError(f"vendored REA entrypoint missing: {REA_ENTRY}")
    return [node, str(REA_ENTRY), "mcp"]


def _doctor() -> int:
    """Print readiness and return a shell exit code (0 = ready)."""
    node = find_node()
    print(f"REA root:   {REA_ROOT}")
    print(f"entrypoint: {REA_ENTRY}  [{'ok' if REA_ENTRY.is_file() else 'MISSING'}]")
    print(f"built dist: {REA_DIST}  [{'ok' if REA_DIST.is_file() else 'MISSING'}]")
    print(f"node:       {node or 'NOT FOUND'}")
    if node:
        version = _node_version(node)
        shown = ".".join(str(part) for part in version) if version else "unknown"
        compat = "ok" if _engine_compatible(version) else "UNSUPPORTED (need ^22.19 || ^24.11 || >=26)"
        print(f"node ver:   {shown}  [{compat}]")

    ready = bool(node) and REA_ENTRY.is_file() and REA_DIST.is_file()
    if not ready and (not REA_DIST.is_file()):
        print('\nRun "python scripts/setup_rea.py" to install deps and build dist/.')
    return 0 if ready else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("--doctor", "doctor"):
        return _doctor()

    if args and args[0] == "--print-command":
        try:
            print(json.dumps(resolve_command()))
            return 0
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        command = resolve_command()
    except RuntimeError as exc:
        print(f"rea_mcp: {exc}", file=sys.stderr)
        return 2

    if not REA_DIST.is_file():
        print(
            f"rea_mcp: {REA_DIST} is not built yet - run 'python scripts/setup_rea.py'.",
            file=sys.stderr,
        )
        return 2

    # stdio is inherited (no pipes) so the MCP JSON-RPC stream is not disturbed.
    try:
        return subprocess.call(command, cwd=str(REA_ROOT))
    except OSError as exc:  # pragma: no cover - env specific
        print(f"rea_mcp: failed to start REA: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
