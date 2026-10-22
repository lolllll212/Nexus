#!/usr/bin/env python3
"""Single source of truth for MCP registrations.

Canonical definitions live in ``opencode.json`` (``mcp`` object). This script
generates the two mirrored registration files so they can never drift:

* ``.vscode/mcp.json``      -> ``servers.<name>``
* ``.agent/mcp_config.json`` -> ``mcpServers.<name>``

Usage::

    python scripts/sync_agent_config.py          # write both files
    python scripts/sync_agent_config.py --check  # exit 1 if files are stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "opencode.json"
VSCODE = REPO_ROOT / ".vscode" / "mcp.json"
AGENT = REPO_ROOT / ".agent" / "mcp_config.json"


def load_canonical() -> dict:
    """Enabled MCP servers from opencode.json, keyed by name."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    servers = {}
    for name, cfg in (data.get("mcp") or {}).items():
        if cfg.get("enabled", True) and cfg.get("command"):
            servers[name] = cfg
    return servers


def build_vscode(canonical: dict) -> dict:
    return {
        "servers": {
            name: {
                "type": "stdio",
                "command": cfg["command"][0],
                "args": list(cfg["command"][1:]),
                "env": dict(cfg.get("environment") or {}),
            }
            for name, cfg in canonical.items()
        }
    }


def build_agent(canonical: dict) -> dict:
    return {
        "mcpServers": {
            name: {
                "command": cfg["command"][0],
                "args": list(cfg["command"][1:]),
            }
            for name, cfg in canonical.items()
        }
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if files are stale")
    args = parser.parse_args()

    canonical = load_canonical()
    targets = {VSCODE: build_vscode(canonical), AGENT: build_agent(canonical)}

    stale = []
    for path, payload in targets.items():
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        if current != payload:
            stale.append(str(path.relative_to(REPO_ROOT)))
            if not args.check:
                _write(path, payload)

    if args.check:
        if stale:
            print("STALE: " + ", ".join(stale))
            print("Run: python scripts/sync_agent_config.py")
            return 1
        print("in sync")
        return 0

    print("synced:", ", ".join(str(p.relative_to(REPO_ROOT)) for p in targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
