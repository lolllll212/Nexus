"""
Built-in tool registry adapter - the capabilities NEXUS ships with.
"""

from __future__ import annotations

import logging

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.value_objects.schema import JSONSchema

logger = logging.getLogger(__name__)


class BuiltinToolRegistry(ToolRegistry):
    """In-memory registry seeded with NEXUS's built-in tools.

    Enforces unique tool IDs: duplicate tool ID registration raises ValueError
    and logs a loud warning unless allow_override is explicitly True.
    """

    def __init__(self, builtins: list[Tool], allow_override: bool = False) -> None:
        self._tools: dict[str, Tool] = {}
        self._index: dict[str, str] = {}
        self._allow_override = allow_override
        for tool in builtins:
            self._register_sync(tool, allow_override=allow_override)

    def _register_sync(self, tool: Tool, allow_override: bool = False) -> None:
        override = allow_override or self._allow_override
        if (tool.id in self._tools or tool.name in self._index) and not override:
            logger.warning(
                "DUPLICATE TOOL REGISTRATION: Tool '%s' (id='%s') is already registered. "
                "Silent overwrite is forbidden; raising ValueError.",
                tool.name,
                tool.id,
            )
            raise ValueError(
                f"Duplicate tool ID '{tool.id}' detected in registry. "
                "Silent overwrite is forbidden. Pass allow_override=True to explicitly permit."
            )
        if tool.id in self._tools or tool.name in self._index:
            logger.warning(
                "OVERRIDING TOOL REGISTRATION: Tool '%s' (id='%s') is being overwritten explicitly.",
                tool.name,
                tool.id,
            )
        self._tools[tool.id] = tool
        self._index[tool.name] = tool.id

    async def register(self, tool: Tool, allow_override: bool = False) -> None:
        self._register_sync(tool, allow_override=allow_override)

    async def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id) or self._tools.get(self._index.get(tool_id, ""))

    async def search(self, query: str, limit: int = 5) -> list[Tool]:
        q = query.lower()
        matches = [t for t in self._tools.values() if q in t.name.lower() or q in t.description.lower()]
        return matches[:limit]

    async def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    async def update(self, tool: Tool) -> None:
        self._tools[tool.id] = tool
        self._index[tool.name] = tool.id


def core_builtin_tools() -> list[Tool]:
    """The 3 fundamental core tools built into NEXUS - single source of truth."""
    return [
        Tool(
            id="web_search",
            name="web_search",
            description="Search the web via DuckDuckGo and return top results.",
            input_schema=JSONSchema(properties={"query": {"type": "string"}}, required=["query"]),
            output_schema=JSONSchema(properties={"results": {"type": "array"}}),
            status=ToolStatus.READY,
        ),
        Tool(
            id="calculator",
            name="calculator",
            description="Evaluate a math expression safely.",
            input_schema=JSONSchema(properties={"expression": {"type": "string"}}, required=["expression"]),
            output_schema=JSONSchema(properties={"result": {"type": "number"}}),
            status=ToolStatus.READY,
        ),
        Tool(
            id="run_python",
            name="run_python",
            description="Execute Python code in a sandbox and return stdout/stderr.",
            input_schema=JSONSchema(properties={"code": {"type": "string"}}, required=["code"]),
            output_schema=JSONSchema(properties={"output": {"type": "string"}, "error": {"type": "string"}}),
            status=ToolStatus.READY,
        ),
    ]


def default_builtin_tools() -> list[Tool]:
    """Seed tools NEXUS can always use — core + extended, with no duplicate tool IDs."""
    from nexus.infrastructure.adapters.execution.extended_tools import extended_builtin_tools

    return core_builtin_tools() + extended_builtin_tools()
