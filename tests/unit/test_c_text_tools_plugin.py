"""Unit tests for the c_text_tools plugin (C ctypes bridge + fallback).

These tests must pass in BOTH modes:
  * native C library built   -> backend == "c"
  * libtextstats not built   -> backend == "python-fallback"

That mirrors the plugin's design (see plugins/c_text_tools/__init__.py):
CI without a `make` step stays green, while a developer who built the
library exercises the real C code path through the exact same tests.
To build the library:  cd c/textstats && make
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.infrastructure.adapters.plugins.loader import PluginLoader
from plugins.c_text_tools import BACKEND, HANDLERS, TOOLS
from tests.fakes import FakeToolRegistry


def test_c_text_tools_contract():
    """Plugin exports TOOLS/HANDLERS conforming to the plugin contract."""
    assert isinstance(TOOLS, list) and len(TOOLS) == 2
    assert isinstance(HANDLERS, dict)
    for tool in TOOLS:
        assert isinstance(tool, Tool)
        assert tool.id in HANDLERS
        assert callable(HANDLERS[tool.id])
        assert tool.status == ToolStatus.READY
        assert tool.input_schema is not None
        assert tool.output_schema is not None
    assert {t.id for t in TOOLS} == {"c_text_stats", "c_title_case"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello world", {"chars": 11, "words": 2, "lines": 1, "longest_word": 5}),
        ("", {"chars": 0, "words": 0, "lines": 0, "longest_word": 0}),
        ("one\ntwo three\n", {"chars": 14, "words": 3, "lines": 2, "longest_word": 5}),
        ("one\ntwo", {"chars": 7, "words": 2, "lines": 2, "longest_word": 3}),
        ("  a   bb\tccc  \n", {"chars": 15, "words": 3, "lines": 1, "longest_word": 3}),
        ("\n", {"chars": 1, "words": 0, "lines": 1, "longest_word": 0}),
    ],
)
async def test_c_text_stats_handler(text, expected):
    result = await HANDLERS["c_text_stats"]({"text": text})
    assert result["backend"] in {"c", "python-fallback"}
    assert result["backend"] == BACKEND
    for key, value in expected.items():
        assert result[key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hELLO wORLD", "Hello World"),
        ("don't stop", "Don't Stop"),
        ("hello Nexus world", "Hello Nexus World"),
        ("", ""),
    ],
)
async def test_c_title_case_handler(text, expected):
    result = await HANDLERS["c_title_case"]({"text": text})
    assert result == {"result": expected, "backend": BACKEND}


@pytest.mark.asyncio
async def test_c_text_tools_invalid_input():
    assert "error" in await HANDLERS["c_text_stats"]({})
    assert "error" in await HANDLERS["c_text_stats"]({"text": 123})
    assert "error" in await HANDLERS["c_title_case"]({"text": None})


def test_plugin_loader_discovers_c_text_tools():
    plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
    loader = PluginLoader(plugins_dir, FakeToolRegistry())
    loaded = loader.load_all()

    by_name = {p.name: p for p in loaded}
    assert "c_text_tools" in by_name
    assert by_name["c_text_tools"].error is None
    assert "c_text_stats" in loader.handlers
    assert "c_title_case" in loader.handlers
