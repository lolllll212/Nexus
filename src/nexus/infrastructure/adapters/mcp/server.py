from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore


class MCPServerAdapter:
    """Thin MCP adapter exposing Nexus capabilities over stdio/SSE and JSON paths.

    The server intentionally reuses the existing tool registry and coordination
    artifacts already in the repo instead of inventing a separate subsystem.
    """

    def __init__(
        self,
        container: Any | None = None,
        memory_store: AgentMemoryStore | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self.container = container
        self.workspace_root = Path(workspace_root or ".").resolve()
        self.memory_store = memory_store or AgentMemoryStore(self.workspace_root / "agent_memory.json")

    async def list_tools(self) -> list[dict[str, Any]]:
        registry = getattr(self.container, "tool_registry", None)
        if registry is None:
            return []
        tools = await registry.list_all()
        specs: list[dict[str, Any]] = []
        for tool in tools:
            input_schema = getattr(tool, "input_schema", None)
            properties = getattr(input_schema, "properties", {}) if input_schema else {}
            required = getattr(input_schema, "required", []) if input_schema else []
            tool_payload = {
                "name": tool.name,
                "description": tool.description,
                "category": "builtin",
                "parameters": properties,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
                "required": required,
            }
            specs.append(tool_payload)
        return specs

    async def list_resources(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "memory",
                "uri": "memory://agent-memory",
                "description": "Agent coordination memory store",
                "mimeType": "application/json",
            },
            {
                "name": "consensus",
                "uri": "consensus://status",
                "description": "Consensus review state",
                "mimeType": "application/json",
            },
            {
                "name": "task-queue",
                "uri": "tasks://queue",
                "description": "Current task queue and agent status",
                "mimeType": "application/json",
            },
            {
                "name": "telemetry",
                "uri": "telemetry://counters",
                "description": "Prometheus-compatible counters and histograms",
                "mimeType": "text/plain",
            },
        ]

    async def query_memory(self, query: str, limit: int = 5, kind: str | None = None) -> list[dict[str, Any]]:
        if not query:
            return []
        memory = self.memory_store
        results = memory.query(query, k=max(1, int(limit)), kind=kind)
        payload: list[dict[str, Any]] = []
        for chunk, score in results:
            payload.append(
                {
                    "id": chunk.id,
                    "agent": chunk.agent,
                    "kind": chunk.kind,
                    "score": round(float(score), 6),
                    "text": chunk.text,
                    "tags": chunk.tags,
                }
            )
        return payload

    async def get_consensus_status(self) -> dict[str, Any]:
        state_path = self.workspace_root / "consensus_state.json"
        if not state_path.exists():
            return {"status": "idle", "proposals": []}
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "idle", "proposals": []}
        proposals = raw.get("proposals", raw.get("reviews", []))
        return {
            "status": raw.get("status", "idle"),
            "proposals": proposals,
            "count": len(proposals),
        }

    async def get_task_queue(self) -> dict[str, Any]:
        state_path = self.workspace_root / "nexus_state.json"
        if not state_path.exists():
            return {"agents": {}, "tasks": []}
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"agents": {}, "tasks": []}
        tasks = raw.get("task_queue", raw.get("tasks", []))
        return {"agents": raw.get("agents", {}), "tasks": tasks}

    async def get_telemetry(self) -> dict[str, Any]:
        telemetry = getattr(self.container, "agent_telemetry", None)
        if telemetry is not None:
            return {
                "enabled": telemetry.enabled,
                "prometheus": telemetry.render_prometheus(),
            }
        metrics = getattr(self.container, "metrics", None)
        if metrics is not None:
            return {"enabled": False, "prometheus": getattr(metrics, "render", lambda: "")()}
        return {"enabled": False, "prometheus": ""}

    async def call_tool(self, tool_name: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(parameters or {})
        if tool_name == "memory_query":
            return {
                "tool": tool_name,
                "result": await self.query_memory(
                    str(params.get("query", "")), int(params.get("limit", 5)), params.get("kind")
                ),
            }

        if tool_name == "consensus_status":
            return {"tool": tool_name, "result": await self.get_consensus_status()}

        if tool_name == "task_queue":
            return {"tool": tool_name, "result": await self.get_task_queue()}

        if tool_name == "telemetry_counters":
            return {"tool": tool_name, "result": await self.get_telemetry()}

        registry = getattr(self.container, "tool_registry", None)
        if registry is not None:
            tool = await registry.get(tool_name)
            if tool is not None:
                executor = getattr(self.container, "executor", None)
                if executor is not None:
                    return {"tool": tool_name, "result": await executor.execute(tool.id, params)}
                return {"tool": tool_name, "result": {"ok": True, "parameters": params}}
        raise KeyError(f"Unknown MCP tool: {tool_name}")

    async def stdio_loop(self, input_stream: Any | None = None, output_stream: Any | None = None) -> None:
        import sys

        reader = input_stream or sys.stdin
        writer = output_stream or sys.stdout
        while True:
            line = reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            method = request.get("method")
            params = request.get("params") or {}
            request_id = request.get("id")
            if method == "tools/list":
                result = await self.list_tools()
            elif method == "resources/list":
                result = await self.list_resources()
            elif method == "memory/query":
                result = await self.query_memory(
                    str(params.get("query", "")), int(params.get("limit", 5)), params.get("kind")
                )
            elif method == "tools/call":
                name = params.get("name") or params.get("tool")
                arguments = params.get("arguments") or params.get("parameters") or {}
                result = await self.call_tool(str(name), arguments)
            elif method == "consensus/status":
                result = await self.get_consensus_status()
            elif method == "tasks/queue":
                result = await self.get_task_queue()
            elif method == "telemetry/counters":
                result = await self.get_telemetry()
            else:
                result = {"error": f"Unsupported method: {method}"}
            writer.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
            writer.flush()

    async def sse_stream(self) -> list[str]:
        events: list[str] = []
        tools = await self.list_tools()
        resources = await self.list_resources()
        events.append("event: tools\ndata: " + json.dumps(tools) + "\n\n")
        events.append("event: resources\ndata: " + json.dumps(resources) + "\n\n")
        return events
