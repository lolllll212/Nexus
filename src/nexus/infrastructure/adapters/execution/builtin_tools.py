"""
Built-in tool registry adapter - the capabilities NEXUS ships with.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.value_objects.schema import JSONSchema


class BuiltinToolRegistry(ToolRegistry):
    """In-memory registry seeded with NEXUS's built-in tools."""

    def __init__(self, builtins: List[Tool]) -> None:
        self._tools: Dict[str, Tool] = {t.id: t for t in builtins}
        self._index: Dict[str, str] = {t.name: t.id for t in builtins}

    async def register(self, tool: Tool) -> None:
        self._tools[tool.id] = tool
        self._index[tool.name] = tool.id

    async def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id) or self._tools.get(self._index.get(tool_id, ""))

    async def search(self, query: str, limit: int = 5) -> List[Tool]:
        q = query.lower()
        matches = [
            t for t in self._tools.values()
            if q in t.name.lower() or q in t.description.lower()
        ]
        return matches[:limit]

    async def list_all(self) -> List[Tool]:
        return list(self._tools.values())

    async def update(self, tool: Tool) -> None:
        self._tools[tool.id] = tool
        self._index[tool.name] = tool.id


def default_builtin_tools() -> List[Tool]:
    """Seed tools NEXUS can always use — core + extended."""
    from nexus.infrastructure.adapters.execution.extended_tools import extended_builtin_tools

    core = [
        Tool(
            id="web_search",
            name="web_search",
            description="Search the web for information on a query.",
            input_schema=JSONSchema(properties={"query": {"type": "string"}}, required=["query"]),
            output_schema=JSONSchema(properties={"results": {"type": "array"}}),
            status=ToolStatus.READY,
        ),
        Tool(
            id="calculator",
            name="calculator",
            description="Evaluate a mathematical expression safely.",
            input_schema=JSONSchema(properties={"expression": {"type": "string"}}, required=["expression"]),
            output_schema=JSONSchema(properties={"result": {"type": "number"}}),
            status=ToolStatus.READY,
        ),
        Tool(
            id="run_python",
            name="run_python",
            description="Execute Python code in a sandbox and return the output.",
            input_schema=JSONSchema(properties={"code": {"type": "string"}}, required=["code"]),
            output_schema=JSONSchema(properties={"output": {"type": "string"}, "error": {"type": "string"}}),
            status=ToolStatus.READY,
        ),
    ]
    return core + extended_builtin_tools()
