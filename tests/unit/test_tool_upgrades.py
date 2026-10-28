"""Regression coverage for the upgraded built-in tool families.

The older tools were individually useful but had uneven contracts: search
could invent findings, HTTP/file reads were unbounded, process output was
collected without a cap, and semantic/dependency scans reported optimistic
totals. These tests pin the safer, structured behaviour without requiring
external network access.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.infrastructure.adapters.execution import extended_tools
from nexus.infrastructure.adapters.execution.builtin_tools import core_builtin_tools
from nexus.infrastructure.adapters.execution.extended_tools import (
    _calculator,
    _code_search_semantic,
    _current_datetime,
    _dependency_audit,
    _git_info,
    _http_request,
    _json_query,
    _list_directory,
    _read_file,
    _run_confined_command,
    _web_fetch,
    _web_search,
    set_embedder,
)
from nexus.infrastructure.adapters.execution.registry_tool_executor import _normalize_params
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider
from nexus.infrastructure.adapters.security import ssrf


class _FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = io.BytesIO(body)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain; charset=utf-8"

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return "https://example.com/final"


def test_safe_http_fetch_detailed_bounds_success_and_http_error_bodies(monkeypatch) -> None:
    monkeypatch.setattr(
        ssrf,
        "resolve_and_validate_safe_url",
        lambda url, allow_local=False: (True, "", "203.0.113.10"),
    )

    class SuccessOpener:
        def open(self, _request: object, timeout: float = 0) -> _FakeHTTPResponse:
            assert timeout == 3
            return _FakeHTTPResponse(b"abcdefghijklmnopqrstuvwxyz")

    monkeypatch.setattr(ssrf, "build_safe_opener", lambda **_kwargs: SuccessOpener())
    result = ssrf.safe_http_fetch_detailed(
        "https://example.com/start",
        timeout=3,
        max_bytes=5,
    )
    assert result["status"] == 200
    assert result["body"] == "abcde"
    assert result["truncated"] is True
    assert result["bytes_read"] == 5
    assert result["final_url"].endswith("/final")

    class ErrorOpener:
        def open(self, _request: object, timeout: float = 0) -> _FakeHTTPResponse:
            headers = Message()
            headers["Content-Type"] = "text/plain; charset=utf-8"
            raise urllib.error.HTTPError(
                "https://example.com/final",
                503,
                "down",
                headers,
                io.BytesIO(b"service unavailable right now"),
            )

    monkeypatch.setattr(ssrf, "build_safe_opener", lambda **_kwargs: ErrorOpener())
    error = ssrf.safe_http_fetch_detailed("https://example.com/start", max_bytes=7)
    assert error["status"] == 503
    assert error["body"] == "service"
    assert error["truncated"] is True


def test_web_search_schema_accepts_the_react_prompt_max_results() -> None:
    tool = next(tool for tool in core_builtin_tools() if tool.id == "web_search")

    assert "max_results" in tool.input_schema.properties
    assert tool.input_schema.validate({"query": "nexus", "max_results": 3}) == []


@pytest.mark.asyncio
async def test_web_search_returns_structured_results_and_never_invents_them(monkeypatch) -> None:
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example <b>Docs</b></a>
      <a class="result__snippet">Useful &amp; grounded snippet.</a>
    </div>
    """

    def fake_fetch(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "status": 200,
            "body": html,
            "headers": {"Content-Type": "text/html"},
            "final_url": "https://html.duckduckgo.com/html/",
            "truncated": False,
            "bytes_read": len(html),
        }

    monkeypatch.setattr(extended_tools, "safe_http_fetch_detailed", fake_fetch)
    result = await _web_search({"query": "example docs", "max_results": 5})
    assert result["results"] == [
        {
            "title": "Example Docs",
            "url": "https://example.com/docs",
            "snippet": "Useful & grounded snippet.",
        }
    ]

    def broken_fetch(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(extended_tools, "safe_http_fetch_detailed", broken_fetch)
    failed = await _web_search({"query": "example docs"})
    assert failed["results"] == []
    assert "network unavailable" in failed["error"]


@pytest.mark.asyncio
async def test_web_fetch_extracts_title_links_and_http_request_sends_json(monkeypatch) -> None:
    page = """
    <html><head><title>Nexus Guide</title><script>alert('x')</script></head>
    <body><h1>Hello</h1><p>Readable body.</p><a href="/next">Next step</a></body></html>
    """
    captured: dict[str, Any] = {}

    def fetch_page(*args: object, **kwargs: object) -> dict[str, Any]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "status": 200,
            "body": page,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "final_url": "https://example.com/guide",
            "truncated": False,
            "bytes_read": len(page),
        }

    monkeypatch.setattr(extended_tools, "safe_http_fetch_detailed", fetch_page)
    fetched = await _web_fetch({"url": "https://example.com/guide", "max_chars": 100})
    assert fetched["title"] == "Nexus Guide"
    assert "Readable body" in fetched["content"]
    assert "alert" not in fetched["content"]
    assert fetched["links"] == [{"title": "Next step", "url": "https://example.com/next"}]

    def fetch_json(*args: object, **kwargs: object) -> dict[str, Any]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "status": 201,
            "body": '{"ok": true}',
            "headers": {"Content-Type": "application/json", "Set-Cookie": "secret=1"},
            "final_url": "https://example.com/api",
            "truncated": False,
            "bytes_read": 12,
        }

    monkeypatch.setattr(extended_tools, "safe_http_fetch_detailed", fetch_json)
    response = await _http_request(
        {
            "url": "https://example.com/api",
            "method": "post",
            "headers": {"Authorization": "Bearer secret", "X-Trace": "123"},
            "json_body": {"name": "Nexus"},
        }
    )
    assert response["status"] == 201
    assert response["json"] == {"ok": True}
    assert "Set-Cookie" not in response["headers"]
    assert captured["kwargs"]["headers"] == {"X-Trace": "123", "Content-Type": "application/json"}
    assert json.loads(captured["kwargs"]["body"]) == {"name": "Nexus"}

    assert (await _http_request({"url": "https://example.com", "method": "TRACE"}))["status"] == 0


@pytest.mark.asyncio
async def test_read_file_ranges_binary_guard_and_directory_caps(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    binary_file = tmp_path / "blob.bin"
    binary_file.write_bytes(b"abc\x00def")

    ranged = await _read_file(
        {"path": str(text_file), "start_line": 2, "end_line": 3, "max_chars": 100}
    )
    assert ranged["content"] == "two\nthree"
    assert ranged["line_range"] == [2, 3]
    assert ranged["total_lines"] == 4

    binary = await _read_file({"path": str(binary_file)})
    assert "binary" in binary["error"]

    (tmp_path / ".hidden").write_text("secret-free", encoding="utf-8")
    (tmp_path / "child").mkdir()
    listed = await _list_directory(
        {"path": str(tmp_path), "max_entries": 2, "include_hidden": False}
    )
    assert listed["total_entries"] == 3
    assert listed["returned_entries"] == 2
    assert listed["truncated"] is True
    assert all(not entry["name"].startswith(".") for entry in listed["entries"])


@pytest.mark.asyncio
async def test_calculator_json_query_and_timezone_are_structured_and_safe() -> None:
    assert (await _calculator({"expression": "sqrt(16) + log(100, 10)"}))["result"] == 6.0
    assert "error" in await _calculator({"expression": "__import__('os').system('id')"})
    assert "error" in await _calculator({"expression": "10**1000"})

    payload = json.dumps({"users": [{"full.name": "First"}, {"full.name": "Last"}], "flag": False})
    found = await _json_query({"json_str": payload, "key_path": "users[-1]['full.name']"})
    assert found == {"result": "Last", "found": True, "key_path": "users[-1]['full.name']"}

    missing = await _json_query(
        {"json_str": {"flag": False}, "key_path": "missing", "default": {"fallback": True}}
    )
    assert missing["found"] is False
    assert missing["result"] == {"fallback": True}

    normalized = _normalize_params(
        "json_query",
        {"data": {"flag": False}, "query": "flag"},
    )
    assert json.loads(normalized["json_str"]) == {"flag": False}
    assert (await _json_query(normalized))["result"] is False

    india = await _current_datetime({"timezone": "Asia/Kolkata"})
    assert india["utc_offset"] == "+0530"
    assert india["timezone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_confined_process_bounds_output_and_times_out(tmp_path: Path) -> None:
    noisy = await _run_confined_command(
        [sys.executable, "-c", "print('x' * 10000)"],
        cwd=tmp_path,
        timeout=5,
        max_chars=1000,
    )
    assert noisy["passed"] is True
    assert len(noisy["stdout"]) <= 1000
    assert noisy["truncated"] is True

    slow = await _run_confined_command(
        [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"],
        cwd=tmp_path,
        timeout=1,
        max_chars=1000,
    )
    assert slow["timed_out"] is True
    assert slow["passed"] is False
    assert slow["duration_ms"] < 3500
    assert "start" in slow["stdout"]


@pytest.mark.asyncio
async def test_git_info_uses_argv_and_reports_worktree_counts(tmp_path: Path) -> None:
    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init")
    run_git("config", "user.email", "nexus@example.invalid")
    run_git("config", "user.name", "Nexus Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git("add", "tracked.txt")
    run_git("commit", "-m", "initial")
    tracked.write_text("after\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    info = await _git_info({"repo_path": str(tmp_path)})
    assert info["is_git_repository"] is True
    assert info["branch"] not in {"", "unknown"}
    assert info["head"]["subject"] == "initial"
    assert info["changed_count"] == 2
    assert info["unstaged_count"] == 1
    assert info["untracked_count"] == 1
    assert info["is_clean"] is False


@pytest.mark.asyncio
async def test_semantic_search_prunes_and_reports_truthful_totals(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Checkout.tsx").write_text(
        "export function CheckoutButton() { return <button>Pay now</button>; }\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "notes.md").write_text(
        "The checkout button starts the payment flow.\n",
        encoding="utf-8",
    )
    ignored = tmp_path / "node_modules" / "pkg"
    ignored.mkdir(parents=True)
    (ignored / "Checkout.tsx").write_text(
        "export const CheckoutButton = 'ignored';\n",
        encoding="utf-8",
    )

    set_embedder(None)
    result = await _code_search_semantic(
        {"query": "CheckoutButton", "path": str(tmp_path), "k": 1}
    )
    assert result["mode"] == "tfidf"
    assert result["files_scanned"] == 2
    assert result["total_matches"] >= 2
    assert len(result["results"]) == 1
    assert result["results"][0]["file"].endswith("src/Checkout.tsx")
    assert "CheckoutButton" in result["results"][0]["snippet"]


@pytest.mark.asyncio
async def test_dependency_audit_understands_local_includes_groups_and_errors(tmp_path: Path) -> None:
    src = tmp_path / "src"
    local_pkg = src / "localpkg"
    local_pkg.mkdir(parents=True)
    (local_pkg / "__init__.py").write_text("", encoding="utf-8")
    (src / "app.py").write_text(
        "import localpkg\nimport missinglib\nimport requests\nimport yaml\n",
        encoding="utf-8",
    )
    (src / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "base.txt").write_text("PyYAML>=6\n", encoding="utf-8")
    (tmp_path / "requirements.in").write_text("-r base.txt\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "audit-sample"
version = "0.1.0"
dependencies = ["requests>=2", "unused-package"]

[project.optional-dependencies]
dev = ["pytest"]

[dependency-groups]
docs = ["sphinx"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = await _dependency_audit(
        {
            "source_path": str(src),
            "requirements_path": str(tmp_path / "requirements.in"),
            "pyproject_path": str(tmp_path / "pyproject.toml"),
        }
    )
    assert result["undeclared"] == ["missinglib"]
    assert {"pyyaml", "requests", "pytest", "sphinx", "unused-package"} <= set(result["declared"])
    assert {"pytest", "sphinx", "unused-package"} <= set(result["unused_declared"])
    assert "localpkg" in result["local_modules"]
    assert "localpkg" not in result["imported"]
    assert result["parse_errors"]
    assert result["clean"] is False


def test_nim_summaries_ground_upgraded_tool_results() -> None:
    provider = NvidiaNimProvider(api_key="", model="meta/llama-3.3-70b-instruct")

    empty_search = provider._deterministic_tool_result_answer(
        "web_search",
        repr({"query": "obscure nexus query", "results": [], "source": "duckduckgo_html"}),
        "Search obscure nexus query",
    )
    assert "returned no results" in empty_search

    audit = provider._deterministic_tool_result_answer(
        "dependency_audit",
        repr(
            {
                "clean": False,
                "files_scanned": 3,
                "imported": ["requests"],
                "declared": ["requests", "pytest"],
                "undeclared": ["missinglib"],
                "unused_declared": ["pytest"],
                "parse_errors": [],
            }
        ),
        "Audit dependencies",
    )
    assert "missinglib" in audit
    assert "pytest" in audit
