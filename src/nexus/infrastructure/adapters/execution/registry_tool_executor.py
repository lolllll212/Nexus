"""
ToolExecutor adapter - dispatches tool calls.

Built-in tools run natively; self-generated tools are called over HTTP
at their deployed endpoint. If a tool has no endpoint, it runs in the sandbox.
"""

from __future__ import annotations

from typing import Any, Dict

from nexus.domain.exceptions import ToolNotFoundError
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry


class RegistryBackedToolExecutor(ToolExecutor):
    """Executes tools by looking them up in the registry."""

    def __init__(self, registry: ToolRegistry, sandbox: Sandbox, builtins: Dict[str, Any]) -> None:
        self._registry = registry
        self._sandbox = sandbox
        self._builtins = builtins

    async def execute(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = await self._registry.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)

        errors = tool.input_schema.validate(params)
        if errors:
            return {"error": "; ".join(errors)}

        # Built-in native handler
        if not tool.is_self_generated and tool_id in self._builtins:
            return await self._builtins[tool_id](params)

        # Deployed endpoint
        if tool.endpoint:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{tool.endpoint}/execute", json=params) as resp:
                    return await resp.json()

        # Fallback: sandbox execution of its code
        return await self._sandbox.run(tool.code or "", inputs=params)
