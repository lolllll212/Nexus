"""Hermetic tests for the cosmos repo/file inspection tool.

Path clamping is the security surface: anything outside the repo root, secret
files, and binaries must be refused. ROOT_DIR is monkeypatched to tmp_path so
these tests never touch the real repository.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def be():
    spec = importlib.util.spec_from_file_location("nexus_cosmos_backend", REPO_ROOT / "backend" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nexus_cosmos_backend"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def repo_root(be, monkeypatch, tmp_path):
    """A fake repo root with a known file, subdir, and secret."""
    (tmp_path / "README.md").write_text("# Fake Repo\n" + "content " * 40, encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "binary.dll").write_bytes(b"MZ\x00\x00")
    monkeypatch.setattr(be, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(be.tools_service, "ROOT_DIR", tmp_path)
    return tmp_path


class TestPathClamping:
    def test_outside_root_refused(self, be, repo_root):
        outside = str(repo_root.parent / "elsewhere.txt")
        result = be.tool_read_repo(f"read {outside}")
        assert result["kind"] == "refused"

    def test_env_secret_refused(self, be, repo_root):
        result = be.tool_read_repo(f"read {repo_root / '.env'}")
        assert result["kind"] == "refused"

    def test_binary_refused(self, be, repo_root):
        result = be.tool_read_repo(f"read {repo_root / 'binary.dll'}")
        assert result["kind"] == "refused"

    def test_traversal_refused(self, be, repo_root):
        result = be.tool_read_repo("read ../../../../Windows/win.ini")
        assert result["kind"] in ("refused", "error")

    def test_missing_file_refused(self, be, repo_root):
        result = be.tool_read_repo(f"read {repo_root / 'nope' / 'ghost.py'}")
        assert result["kind"] == "refused"


class TestReads:
    def test_directory_listing(self, be, repo_root):
        result = be.tool_read_repo(f"see {repo_root}")
        assert result["kind"] == "directory"
        names = {e["name"] for e in result["entries"]}
        assert {"README.md", "src"} <= names

    def test_file_excerpt(self, be, repo_root):
        result = be.tool_read_repo(f"read {repo_root / 'README.md'}")
        assert result["kind"] == "file"
        assert result["excerpt"].startswith("# Fake Repo")
        assert result["bytes"] > 0

    def test_repo_overview_for_project_questions(self, be, repo_root):
        result = be.tool_read_repo("what do you think about the project file at all?")
        assert result["kind"] == "overview"
        assert any(e["name"] == "README.md" for e in result["entries"])

    def test_relative_path_resolves_inside_root(self, be, repo_root):
        result = be.tool_read_repo("read src/app.py and tell me about it")
        assert result["kind"] == "file"
        assert "print" in result["excerpt"]


class TestRouterIntent:
    @pytest.mark.asyncio
    async def test_chat_uses_repo_tool_for_see_path(self, be, repo_root, monkeypatch):
        """The /chat intent router must dispatch path reads to the repo tool."""

        async def fake_llm(system, messages):
            return "SCORE: 1.0\nCRITIQUE: n/a", ""  # unused here

        # Drive the real endpoint logic via a lightweight ASGI-less call:
        from fastapi.testclient import TestClient  # noqa: PLC0415

        monkeypatch.setattr(be, "_check_llm_alive", _async_false)
        client = TestClient(be.app)
        resp = client.post("/chat", json={"message": f"see {repo_root}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "repo_read" in data["tools_used"]


async def _async_false():
    return False


class TestSiblingDiscovery:
    def test_discovers_sibling_repo_by_name(self, be, monkeypatch, tmp_path):
        home = tmp_path / "home"
        (home / "Astra-X-main").mkdir(parents=True)
        (home / "Astra-X-main" / "main.py").write_text("print(1)", encoding="utf-8")
        monkeypatch.setattr(be.tools_service, "_HOME", home)
        result = be.tool_read_repo("use tools to look into the repo astra-x-main in the local disk")
        assert result["kind"] == "directory"
        assert result["external"] is True
        assert "Astra-X-main" in result["path"]

    def test_discovery_is_case_insensitive(self, be, monkeypatch, tmp_path):
        home = tmp_path / "home"
        (home / "My-Project").mkdir(parents=True)
        monkeypatch.setattr(be.tools_service, "_HOME", home)
        result = be.tool_read_repo("look into the repo my-project please")
        assert result["kind"] == "directory"

    def test_unknown_name_reports_not_found(self, be, monkeypatch, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True)
        monkeypatch.setattr(be.tools_service, "_HOME", home)
        result = be.tool_read_repo("look into the repo does-not-exist-xyz")
        assert result["kind"] == "not-found"
        assert "does-not-exist-xyz" in result["searched"]

    def test_discovery_scan_capped(self, be, monkeypatch, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True)
        for i in range(50):
            (home / f"dir{i}").mkdir()
            for j in range(5):
                (home / f"dir{i}" / f"sub{j}").mkdir()
        monkeypatch.setattr(be.tools_service, "_HOME", home)
        monkeypatch.setattr(be.tools_service, "_DISCOVERY_SCAN_CAP", 30)
        result = be.tool_read_repo("look into the repo dir49")
        assert result["kind"] in ("not-found", "directory")  # cap respected, no hang
