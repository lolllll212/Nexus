"""REA agent-tooling tests: the health checks a NEXUS agent should run before
and after doing work with the vendored REA MCP server.

Covers the exact surface agents use - stdio MCP handshake, the advertised tool
catalog, one real end-to-end analysis with evidence - plus the blueprint recipe
format they must save into memory when the work completes. Node-level tests
skip with an actionable message when REA is not built yet
(``python scripts/setup_rea.py``), so they stay hermetic on fresh clones.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import nexus_mcp  # noqa: E402
import rea_mcp  # noqa: E402

REA_ENTRY = rea_mcp.REA_ENTRY
REA_DIST = rea_mcp.REA_ROOT / "dist" / "mcp" / "main.js"
PE_TARGET = rea_mcp.REA_ROOT / "node_modules" / "@lydell" / "node-pty-win32-x64" / "conpty_console_list.node"

_SETUP_HINT = "REA not built - run: python scripts/setup_rea.py"


@pytest.fixture(scope="module")
def rea_server():
    """One live REA MCP server process for the module, skipped cleanly when
    REA is unbuilt or no engine-compatible Node runtime exists."""
    if not (REA_ENTRY.is_file() and REA_DIST.is_file()):
        pytest.skip(_SETUP_HINT)
    if rea_mcp.find_node() is None:
        pytest.skip("No engine-compatible Node runtime found (see docs/rea.md)")
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "rea_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        yield proc
    finally:
        proc.kill()


def _rpc(proc: subprocess.Popen, payload: dict) -> dict:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line, "REA MCP server closed stdout unexpectedly"
    return json.loads(line.strip())


def _initialize(proc: subprocess.Popen) -> dict:
    resp = _rpc(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nexus-agent", "version": "1.0.0"},
            },
        },
    )
    return resp.get("result", {})


class TestReaHealth:
    """Run these first: they prove the agent can talk to REA at all."""

    def test_handshake(self, rea_server):
        result = _initialize(rea_server)
        assert result.get("protocolVersion") == "2024-11-05"
        info = result.get("serverInfo", {})
        assert info.get("name") == "rea"
        assert info.get("version")
        assert "Evidence" in result.get("instructions", "")

    def test_tool_surface(self, rea_server):
        _initialize(rea_server)
        resp = _rpc(rea_server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp.get("result", {}).get("tools", [])
        assert len(tools) >= 150, "REA tool catalog unexpectedly small"
        names = {t["name"] for t in tools}
        # The core loop an agent needs for an investigation.
        for required in (
            "open_binary",
            "inspect_pe_resources",
            "analyze_javascript_application",
            "get_evidence_bundle",
            "close_binary",
        ):
            assert required in names


class TestReaAnalysis:
    """A real (read-only) analysis proving tools return evidence inline."""

    def test_pe_resources_end_to_end(self, rea_server):
        if not PE_TARGET.is_file():
            pytest.skip("node_modules not installed - run: python scripts/setup_rea.py")
        _initialize(rea_server)
        resp = _rpc(
            rea_server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "inspect_pe_resources",
                    "arguments": {"path": str(PE_TARGET)},
                },
            },
        )
        assert resp.get("id") == 3
        assert resp.get("error") is None
        content = resp.get("result", {}).get("content", [])
        assert content and content[0].get("type") == "text"
        text = content[0]["text"]
        assert "pe32-plus" in text
        assert "ev_" in text, "analysis must carry a stable evidence id"


class TestBlueprintRecipes:
    """Work done with REA must land in memory as a reusable blueprint."""

    def test_recipe_sections(self):
        text = nexus_mcp._compose_blueprint_text(  # noqa: SLF001
            title="Inspect a native DLL",
            goal="Explain exported behaviour with evidence",
            steps=["open binary", "read resources", "export evidence"],
            files=["docs/rea.md"],
            verify=["pytest tests/unit/test_rea_agent_tools.py -q"],
            tools=["rea:open_binary", "rea:inspect_pe_resources"],
        )
        for section in ("BLUEPRINT:", "GOAL:", "STEPS:", "FILES:", "VERIFY:", "TOOLS:"):
            assert section in text

    def test_rea_blueprint_roundtrip(self, monkeypatch, tmp_path):
        from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore

        store = AgentMemoryStore(tmp_path / "agent_memory.json")
        monkeypatch.setattr(nexus_mcp, "_agent_memory_store", lambda: store)

        saved = nexus_mcp.handle_tool_call(
            "blueprint_save",
            {
                "agent_id": "xenom",
                "title": "Inspect a native DLL",
                "goal": "Explain exported behaviour with evidence",
                "steps": ["open binary", "read resources", "export evidence"],
                "files": ["docs/rea.md"],
                "verify": ["pytest tests/unit/test_rea_agent_tools.py -q"],
                "tools": ["rea:inspect_pe_resources"],
                "tags": "rea,native,pe",
            },
        )
        assert "Blueprint saved" in saved

        found = nexus_mcp.handle_tool_call("blueprint_query", {"query": "rea native pe inspect", "k": 3})
        assert "Inspect a native DLL" in found
        assert "rea:inspect_pe_resources" in found
