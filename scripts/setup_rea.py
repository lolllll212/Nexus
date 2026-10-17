"""Install dependencies and build the vendored REA MCP server.

REA (``vendor/rea``) is a Node.js project and its MCP entrypoint
(``scripts/rea.mjs``) loads compiled code from ``dist/`` - so it must be built
once before ``scripts/rea_mcp.py`` can serve it. This helper locates a Node
runtime and npm (both may be off ``PATH``), installs from the lockfile, and
compiles.

Usage::

    python scripts/setup_rea.py                 # npm ci + npm run compile
    python scripts/setup_rea.py --doctor        # report readiness, build nothing
    python scripts/setup_rea.py --skip-install  # build only
    python scripts/setup_rea.py --skip-build    # install only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rea_mcp import (  # noqa: E402  (sibling launcher module, resolved above)
    REA_DIST,
    REA_ENTRY,
    REA_ROOT,
    _engine_compatible,
    _node_version,
    find_node,
)

NODE_OVERRIDE_ENV = "NEXUS_REA_NODE"


def find_npm(node: str) -> list[str] | None:
    """Return an argv prefix that runs npm, preferring npm-cli.js beside node."""
    node_dir = Path(node).resolve().parent
    cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if cli.is_file():
        return [node, str(cli)]
    for name in ("npm.cmd", "npm"):
        candidate = node_dir / name
        if candidate.is_file():
            return [str(candidate)]
    for name in ("npm.cmd", "npm"):
        which = shutil.which(name)
        if which:
            return [which]
    return None


def _run(argv: list[str], cwd: Path, node_dir: Path | None = None) -> int:
    print("+ " + " ".join(argv), flush=True)
    # HUSKY=0 stops the vendored project's git-hook installer from running while
    # we only want a build; npm ci otherwise triggers REA's `prepare` script.
    env = {**os.environ, "HUSKY": "0"}
    if node_dir is not None:
        # Dependency lifecycle scripts (esbuild's install.js, native addons)
        # shell out to bare `node`. When Node is off PATH it must be prepended
        # here or those postinstall steps fail with "'node' is not recognized".
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    return subprocess.call(argv, cwd=str(cwd), env=env)


def doctor() -> int:
    """Print readiness and return an exit code (0 = ready to build/run)."""
    node = find_node()
    print(f"node:    {node or 'NOT FOUND'}")
    if node:
        version = _node_version(node)
        shown = ".".join(str(part) for part in version) if version else "unknown"
        compat = "ok" if _engine_compatible(version) else "UNSUPPORTED (need ^22.19 || ^24.11 || >=26)"
        print(f"version: {shown}  [{compat}]")
    npm = find_npm(node) if node else None
    print(f"npm:     {' '.join(npm) if npm else 'NOT FOUND'}")
    print(f"entry:   {REA_ENTRY}  [{'ok' if REA_ENTRY.is_file() else 'MISSING'}]")
    print(f"dist:    {REA_DIST}  [{'ok' if REA_DIST.is_file() else 'MISSING'}]")
    return 0 if (node and npm and REA_ENTRY.is_file()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the vendored REA MCP server.")
    parser.add_argument("--doctor", action="store_true", help="report readiness and exit")
    parser.add_argument("--skip-install", action="store_true", help="do not run npm ci")
    parser.add_argument("--skip-build", action="store_true", help="do not run npm run compile")
    args = parser.parse_args(argv)

    if args.doctor:
        return doctor()

    node = find_node()
    if not node:
        print(
            f"setup_rea: no Node.js runtime found. Install Node >=22.19 (https://nodejs.org) "
            f"or set {NODE_OVERRIDE_ENV} to a node.exe path.",
            file=sys.stderr,
        )
        return 2

    version = _node_version(node)
    if not _engine_compatible(version):
        shown = ".".join(str(part) for part in version) if version else "unknown"
        print(
            f"setup_rea: Node {shown} is not supported by REA (needs ^22.19 || ^24.11 || >=26; "
            f"vendor/rea/.npmrc sets engine-strict). Set {NODE_OVERRIDE_ENV} to a compatible runtime.",
            file=sys.stderr,
        )
        return 2

    if not REA_ENTRY.is_file():
        print(f"setup_rea: vendored entrypoint missing: {REA_ENTRY}", file=sys.stderr)
        return 2

    npm = find_npm(node)
    if not npm:
        print("setup_rea: npm not found next to node or on PATH.", file=sys.stderr)
        return 2

    if not args.skip_install:
        if _run(npm + ["ci"], REA_ROOT, node_dir=Path(node).parent) != 0:
            print("setup_rea: 'npm ci' failed.", file=sys.stderr)
            return 1

    if not args.skip_build:
        if _run(npm + ["run", "compile"], REA_ROOT, node_dir=Path(node).parent) != 0:
            print("setup_rea: 'npm run compile' failed.", file=sys.stderr)
            return 1

    if REA_DIST.is_file():
        print(f"setup_rea: built {REA_DIST}")
        return 0
    print("setup_rea: build finished but dist/mcp/main.js is missing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
