"""Unit tests for the NEXUS plugin ecosystem and ToolRegistry integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.infrastructure.adapters.plugins.loader import PluginLoader
from plugins.math_tools import HANDLERS as MATH_HANDLERS
from plugins.math_tools import TOOLS as MATH_TOOLS
from plugins.sample_text_tools import HANDLERS as TEXT_HANDLERS
from plugins.sample_text_tools import TOOLS as TEXT_TOOLS
from tests.fakes import FakeToolRegistry


def test_plugin_exports_conforming_contract():
    """Verify both plugins export TOOLS and HANDLERS conforming to the plugin contract."""
    for tools, handlers in [(TEXT_TOOLS, TEXT_HANDLERS), (MATH_TOOLS, MATH_HANDLERS)]:
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert isinstance(handlers, dict)

        for tool in tools:
            assert isinstance(tool, Tool)
            assert tool.id in handlers
            assert callable(handlers[tool.id])
            assert tool.status == ToolStatus.READY
            assert tool.input_schema is not None
            assert tool.output_schema is not None


@pytest.mark.asyncio
async def test_tool_registry_port_registration_and_retrieval():
    """Verify that tools from plugins can be registered and retrieved through the ToolRegistry port."""
    registry = FakeToolRegistry()

    for tool in MATH_TOOLS:
        await registry.register(tool)

    # Retrieval by id
    stat_tool = await registry.get("math_statistics")
    assert stat_tool is not None
    assert stat_tool.name == "math_statistics"
    assert "numbers" in stat_tool.input_schema.properties

    factors_tool = await registry.get("prime_factors")
    assert factors_tool is not None
    assert factors_tool.name == "prime_factors"

    # List all
    all_tools = await registry.list_all()
    tool_ids = {t.id for t in all_tools}
    assert "math_statistics" in tool_ids
    assert "prime_factors" in tool_ids


@pytest.mark.asyncio
async def test_math_tools_statistics_handler():
    handler = MATH_HANDLERS["math_statistics"]

    # Odd count
    res_odd = await handler({"numbers": [10, 20, 30]})
    assert res_odd["count"] == 3
    assert res_odd["mean"] == 20.0
    assert res_odd["median"] == 20.0
    assert res_odd["min"] == 10.0
    assert res_odd["max"] == 30.0

    # Even count
    res_even = await handler({"numbers": [1, 2, 3, 4]})
    assert res_even["count"] == 4
    assert res_even["mean"] == 2.5
    assert res_even["median"] == 2.5

    # Empty
    res_empty = await handler({"numbers": []})
    assert "error" in res_empty


@pytest.mark.asyncio
async def test_math_tools_prime_factors_handler():
    handler = MATH_HANDLERS["prime_factors"]

    res = await handler({"n": 84})
    assert res["factors"] == [2, 2, 3, 7]

    res_prime = await handler({"n": 13})
    assert res_prime["factors"] == [13]

    res_invalid = await handler({"n": 1})
    assert "error" in res_invalid


def test_plugin_loader_discovers_all_plugins():
    """Verify PluginLoader dynamically loads all plugins from the plugins directory."""
    plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
    registry = FakeToolRegistry()
    loader = PluginLoader(plugins_dir, registry)

    loaded = loader.load_all()
    loaded_names = {p.name for p in loaded}

    assert "sample_text_tools" in loaded_names
    assert "math_tools" in loaded_names

    # Check that handlers are populated
    handlers = loader.handlers
    assert "word_count" in handlers
    assert "capitalize" in handlers
    assert "math_statistics" in handlers
    assert "prime_factors" in handlers
