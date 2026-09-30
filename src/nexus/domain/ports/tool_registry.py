"""
Tool registry and execution ports.

The brain discovers, registers, and executes tools through these interfaces.
The registry is where self-generated tools get stored for reuse.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexus.domain.entities.tool import Tool


class ToolRegistry(ABC):
    """Storage and discovery of available tools."""

    @abstractmethod
    async def register(self, tool: Tool) -> None: ...

    @abstractmethod
    async def get(self, tool_id: str) -> Tool | None: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[Tool]: ...

    @abstractmethod
    async def list_all(self) -> list[Tool]: ...

    @abstractmethod
    async def update(self, tool: Tool) -> None: ...


class ToolExecutor(ABC):
    """Executes tool invocations in a sandboxed environment."""

    @abstractmethod
    async def execute(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]: ...
