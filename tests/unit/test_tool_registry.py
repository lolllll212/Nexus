"""
Unit tests for BuiltinToolRegistry and tool composition.

Guarantees:
- Single source of truth per tool id (no silent overwriting of core tools).
- Duplicate tool id registration either raises ValueError or logs loudly (silent overwrite impossible).
- Core tools (web_search, calculator, run_python) have aligned definitions.
- Explicit overrides are permitted only when allow_override=True.
"""

from __future__ import annotations

import logging

import pytest

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.execution.builtin_tools import (
    BuiltinToolRegistry,
    core_builtin_tools,
    default_builtin_tools,
)


def _make_tool(tool_id: str, name: str | None = None, description: str = "A test tool") -> Tool:
    return Tool(
        id=tool_id,
        name=name or tool_id,
        description=description,
        input_schema=JSONSchema(properties={"input": {"type": "string"}}),
        output_schema=JSONSchema(properties={"result": {"type": "string"}}),
        status=ToolStatus.READY,
    )


def test_default_builtin_tools_unique_ids_and_names():
    """Verify default_builtin_tools contains no duplicate IDs or names."""
    tools = default_builtin_tools()
    ids = [t.id for t in tools]
    names = [t.name for t in tools]

    assert len(ids) == len(set(ids)), f"Duplicate tool IDs found: {[x for x in ids if ids.count(x) > 1]}"
    assert len(names) == len(
        set(names)
    ), f"Duplicate tool names found: {[x for x in names if names.count(x) > 1]}"

    # Verify core tools are present
    core_ids = {t.id for t in core_builtin_tools()}
    assert core_ids == {"web_search", "calculator", "run_python"}
    assert core_ids.issubset(set(ids))


def test_core_tools_definitions_aligned():
    """Verify the 3 core tools have accurate and aligned descriptions/schemas."""
    core = {t.id: t for t in core_builtin_tools()}
    assert "web_search" in core
    assert "DuckDuckGo" in core["web_search"].description
    assert "query" in core["web_search"].input_schema.properties

    assert "calculator" in core
    assert "expression" in core["calculator"].input_schema.properties

    assert "run_python" in core
    assert "sandbox" in core["run_python"].description
    assert "code" in core["run_python"].input_schema.properties


def test_duplicate_registration_on_init_raises_and_logs(caplog):
    """Verify initializing registry with duplicate tool IDs raises ValueError and logs loudly."""
    tool1 = _make_tool("tool_a", description="First tool")
    tool2 = _make_tool("tool_a", description="Duplicate tool")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="Duplicate tool ID 'tool_a' detected"):
            BuiltinToolRegistry([tool1, tool2])

    assert any("DUPLICATE TOOL REGISTRATION" in record.message for record in caplog.records)


async def test_duplicate_registration_via_register_raises_and_logs(caplog):
    """Verify calling register with an existing tool ID raises ValueError and logs loudly."""
    tool1 = _make_tool("tool_b", description="Original")
    registry = BuiltinToolRegistry([tool1])

    tool1_dup = _make_tool("tool_b", description="Duplicate")
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="Duplicate tool ID 'tool_b' detected"):
            await registry.register(tool1_dup)

    assert any("DUPLICATE TOOL REGISTRATION" in record.message for record in caplog.records)


def test_explicit_override_allowed_on_init_with_flag(caplog):
    """Verify allow_override=True permits explicit overriding on init and logs notice."""
    tool1 = _make_tool("tool_c", description="Original")
    tool2 = _make_tool("tool_c", description="Updated")

    with caplog.at_level(logging.WARNING):
        registry = BuiltinToolRegistry([tool1, tool2], allow_override=True)

    tool = registry._tools["tool_c"]
    assert tool.description == "Updated"
    assert any("OVERRIDING TOOL REGISTRATION" in record.message for record in caplog.records)


async def test_explicit_override_allowed_via_register(caplog):
    """Verify register(allow_override=True) permits explicit overriding."""
    tool1 = _make_tool("tool_d", description="Original")
    registry = BuiltinToolRegistry([tool1])

    tool1_updated = _make_tool("tool_d", description="Updated description")
    with caplog.at_level(logging.WARNING):
        await registry.register(tool1_updated, allow_override=True)

    fetched = await registry.get("tool_d")
    assert fetched is not None
    assert fetched.description == "Updated description"
    assert any("OVERRIDING TOOL REGISTRATION" in record.message for record in caplog.records)


async def test_registry_update_and_lookup():
    """Verify standard get, search, list_all, and update methods work as expected."""
    registry = BuiltinToolRegistry(default_builtin_tools())

    # Get by ID and by name
    calc_by_id = await registry.get("calculator")
    assert calc_by_id is not None
    assert calc_by_id.id == "calculator"

    # Search
    search_res = await registry.search("python")
    assert any(t.id == "run_python" for t in search_res)

    # List all
    all_tools = await registry.list_all()
    assert len(all_tools) >= 20

    # Explicit update
    updated_calc = _make_tool("calculator", description="Updated calculator")
    await registry.update(updated_calc)
    assert (await registry.get("calculator")).description == "Updated calculator"
