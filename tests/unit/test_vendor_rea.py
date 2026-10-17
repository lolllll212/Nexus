"""Hermetic tests for the vendored REA MCP server wiring.

Covers the engine-aware Node locator, the stdio launcher command shape, and that
REA is registered as an MCP server next to ``nexus`` in every agent config. No
Node process is spawned - version probing is monkeypatched - so this stays fast
and offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import rea_mcp  # noqa: E402
import setup_rea  # noqa: E402


class TestEngineCompatibility:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ((22, 19, 0), True),
            ((22, 18, 0), False),
            ((23, 5, 0), False),
            ((24, 11, 0), True),
            ((24, 10, 0), False),
            ((25, 8, 1), False),
            ((26, 0, 0), True),
            ((27, 1, 0), True),
            (None, False),
        ],
    )
    def test_engine_range(self, version, expected):
        assert rea_mcp._engine_compatible(version) is expected


class TestFindNode:
    def test_prefers_engine_compatible(self, monkeypatch, tmp_path):
        incompatible = tmp_path / "old" / "node.exe"
        incompatible.parent.mkdir()
        incompatible.write_text("")
        compatible = tmp_path / "new" / "node.exe"
        compatible.parent.mkdir()
        compatible.write_text("")
        versions = {str(incompatible): (25, 8, 1), str(compatible): (24, 21, 0)}

        monkeypatch.setattr(rea_mcp.shutil, "which", lambda name: None)
        monkeypatch.setattr(rea_mcp, "_candidate_nodes", lambda: [incompatible, compatible])
        monkeypatch.setattr(rea_mcp, "_node_version", lambda exe: versions.get(exe))

        assert rea_mcp.find_node() == str(compatible)

    def test_falls_back_when_none_compatible(self, monkeypatch, tmp_path):
        only = tmp_path / "node.exe"
        only.write_text("")
        monkeypatch.setattr(rea_mcp.shutil, "which", lambda name: None)
        monkeypatch.setattr(rea_mcp, "_candidate_nodes", lambda: [only])
        monkeypatch.setattr(rea_mcp, "_node_version", lambda exe: (25, 8, 1))

        assert rea_mcp.find_node() == str(only)

    def test_none_when_nothing_found(self, monkeypatch):
        monkeypatch.setattr(rea_mcp.shutil, "which", lambda name: None)
        monkeypatch.setattr(rea_mcp, "_candidate_nodes", list)
        assert rea_mcp.find_node() is None

    def test_path_node_wins_and_is_validated(self, monkeypatch, tmp_path):
        node = tmp_path / "node.exe"
        node.write_text("")
        monkeypatch.setattr(
            rea_mcp.shutil, "which", lambda name: str(node) if name in ("node", "node.exe") else None
        )
        monkeypatch.setattr(rea_mcp, "_candidate_nodes", list)
        monkeypatch.setattr(rea_mcp, "_node_version", lambda exe: (24, 21, 0))

        assert rea_mcp.find_node() == str(node)

    def test_override_env_is_honoured(self, monkeypatch, tmp_path):
        custom = tmp_path / "custom-node.exe"
        custom.write_text("")
        monkeypatch.setenv(rea_mcp.NODE_OVERRIDE_ENV, str(custom))
        monkeypatch.setattr(rea_mcp.shutil, "which", lambda name: None)
        monkeypatch.setattr(rea_mcp, "_node_version", lambda exe: (24, 21, 0))

        assert rea_mcp.find_node() == str(custom)


class TestResolveCommand:
    def test_command_shape(self, monkeypatch):
        monkeypatch.setattr(rea_mcp, "find_node", lambda: r"C:\node\node.exe")
        command = rea_mcp.resolve_command()
        assert command == [r"C:\node\node.exe", str(rea_mcp.REA_ENTRY), "mcp"]

    def test_missing_node_raises_actionable_error(self, monkeypatch):
        monkeypatch.setattr(rea_mcp, "find_node", lambda: None)
        with pytest.raises(RuntimeError, match="Node"):
            rea_mcp.resolve_command()


class TestVendoredTree:
    def test_entrypoint_present(self):
        assert rea_mcp.REA_ENTRY.is_file()

    def test_package_and_license_present(self):
        assert (rea_mcp.REA_ROOT / "package.json").is_file()
        assert (rea_mcp.REA_ROOT / "LICENSE").is_file()

    def test_provenance_readme_present(self):
        assert (rea_mcp.REA_ROOT / "README.vendor.md").is_file()


class TestMcpRegistration:
    def test_opencode_registers_rea_next_to_nexus(self):
        data = json.loads((REPO_ROOT / "opencode.json").read_text(encoding="utf-8"))
        assert data["mcp"]["rea"]["command"] == ["python", "scripts/rea_mcp.py"]
        assert data["mcp"]["nexus"]["command"] == ["python", "scripts/nexus_mcp.py"]

    def test_vscode_registers_rea(self):
        data = json.loads((REPO_ROOT / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
        assert data["servers"]["rea"]["args"] == ["scripts/rea_mcp.py"]

    def test_antigravity_registers_rea(self):
        data = json.loads((REPO_ROOT / ".agent" / "mcp_config.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["rea"]["args"] == ["scripts/rea_mcp.py"]


class TestFindNpm:
    def test_prefers_npm_cli_beside_node(self, tmp_path):
        node_dir = tmp_path / "nodejs"
        cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
        cli.parent.mkdir(parents=True)
        cli.write_text("")
        node = node_dir / "node.exe"
        node.write_text("")

        assert setup_rea.find_npm(str(node)) == [str(node), str(cli)]
