"""SwarmAgentExecutor - runs one agent on a task through the cortex.

Each agent gets its own system prompt injected (P4), and its tool access is
restricted to the agent's allowlist: disallowed tools are invisible to the
ReAct loop during the run, then restored afterwards.
"""

from __future__ import annotations

from typing import List, Optional, Set

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.domain.entities.agent import Agent
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.tool_registry import ToolRegistry


class _FilteredToolRegistry(ToolRegistry):
    """View over a registry exposing only allowlisted tool names."""

    def __init__(self, inner: ToolRegistry, allowlist: Set[str]) -> None:
        self._inner = inner
        self._allowlist = allowlist

    def _allowed(self, tool: Tool) -> bool:
        return tool.name in self._allowlist

    async def register(self, tool: Tool) -> None:
        await self._inner.register(tool)

    async def get(self, tool_id: str) -> Optional[Tool]:
        tool = await self._inner.get(tool_id)
        if tool is not None and not self._allowed(tool):
            return None
        return tool

    async def search(self, query: str, limit: int = 5) -> List[Tool]:
        return [t for t in await self._inner.search(query, limit * 4) if self._allowed(t)][:limit]

    async def list_all(self) -> List[Tool]:
        return [t for t in await self._inner.list_all() if self._allowed(t)]

    async def update(self, tool: Tool) -> None:
        await self._inner.update(tool)


class SwarmAgentExecutor:
    """Executes an agent: injects its system prompt and scopes its tools."""

    def __init__(self, process_message: ProcessMessageUseCase, tool_registry: ToolRegistry) -> None:
        self._process_message = process_message
        self._tool_registry = tool_registry

    async def run_agent(self, agent: Agent, task: str, tenant_id: str) -> str:
        original_tools = self._process_message._tools
        try:
            if agent.tools:
                self._process_message._tools = _FilteredToolRegistry(self._tool_registry, set(agent.tools))
            result = await self._process_message.execute(
                user_id=agent.owner_id,
                message=task,
                session_id=f"agent:{agent.id}",
                tenant_id=tenant_id,
                system_prompt=agent.system_prompt,
            )
            return result.response
        finally:
            self._process_message._tools = original_tools
