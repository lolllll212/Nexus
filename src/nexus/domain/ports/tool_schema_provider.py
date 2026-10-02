"""ToolSchemaProvider port for MCP and tool definition export.

Defines the domain-side contract for converting domain Tool entities
and tool contracts into standard JSON-Schema format for MCP consumers.
Maintains pure domain independence (zero infrastructure imports).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexus.domain.entities.tool import Tool
from nexus.domain.ports.tool_registry import ToolRegistry


class ToolSchemaProvider(ABC):
    """Domain port for extracting and formatting tool schemas for MCP and external clients."""

    @abstractmethod
    def export_schema(self, tool: Tool) -> dict[str, Any]:
        """Convert a single Tool entity into an MCP-compliant JSON schema definition."""
        ...

    @abstractmethod
    def export_all(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Convert a collection of Tool entities into MCP-compliant JSON schema definitions."""
        ...

    @abstractmethod
    async def export_registry(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        """Export all registered tools from a domain ToolRegistry as MCP tool schemas."""
        ...
