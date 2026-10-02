"""Domain-level Model Context Protocol (MCP) support and serialization.

Provides:
1. StandardToolSchemaProvider: Implements ToolSchemaProvider port for converting
   domain Tool entities and JSONSchema contracts to MCP-compliant JSON schema specs.
2. Domain entity serializers that safely format domain entities (Tool, Memory, Goal,
   Agent, Concept, Conversation) into JSON-serializable dictionaries for MCP resources.

Adheres strictly to Hexagonal Architecture: zero imports from nexus.infrastructure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.concept import Concept
from nexus.domain.entities.conversation import Conversation
from nexus.domain.entities.goal import Goal
from nexus.domain.entities.memory import Memory
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.ports.tool_schema_provider import ToolSchemaProvider
from nexus.domain.value_objects.schema import JSONSchema


def export_json_schema(schema: JSONSchema | None) -> dict[str, Any]:
    """Convert domain JSONSchema value object to standard JSON Schema dictionary."""
    if schema is None:
        return {"type": "object", "properties": {}, "required": []}
    return {
        "type": schema.type or "object",
        "description": schema.description or "",
        "properties": dict(schema.properties or {}),
        "required": list(schema.required or []),
    }


class StandardToolSchemaProvider(ToolSchemaProvider):
    """Domain-side implementation of ToolSchemaProvider port for MCP consumers."""

    def export_schema(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool entity into MCP-compliant JSON schema definition."""
        in_schema = export_json_schema(tool.input_schema)
        out_schema = export_json_schema(tool.output_schema)
        props = in_schema.get("properties", {})
        req = in_schema.get("required", [])
        cat = "generated" if tool.is_self_generated else "builtin"

        return {
            "name": tool.name,
            "description": tool.description,
            "category": cat,
            "parameters": props,
            "inputSchema": in_schema,
            "outputSchema": out_schema,
            "required": req,
            "status": tool.status.value if hasattr(tool.status, "value") else str(tool.status),
            "version": tool.version,
            "is_self_generated": tool.is_self_generated,
            "use_count": tool.use_count,
            "success_rate": round(tool.success_rate, 4),
        }

    def export_all(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Export multiple Tool entities into a list of MCP tool definitions."""
        return [self.export_schema(t) for t in tools]

    async def export_registry(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        """Query all tools from domain ToolRegistry and export their MCP schemas."""
        tools = await registry.list_all()
        return self.export_all(tools)


# ---------------------------------------------------------------------------
# Safe Domain Entity Serializers for MCP Resources
# ---------------------------------------------------------------------------


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def serialize_tool_for_mcp(tool: Tool) -> dict[str, Any]:
    """Safely serialize Tool entity for MCP resource consumption."""
    return {
        "id": str(tool.id),
        "name": tool.name,
        "description": tool.description,
        "input_schema": export_json_schema(tool.input_schema),
        "output_schema": export_json_schema(tool.output_schema),
        "status": tool.status.value if hasattr(tool.status, "value") else str(tool.status),
        "version": tool.version,
        "is_self_generated": tool.is_self_generated,
        "created_at": _iso(tool.created_at),
        "last_used_at": _iso(tool.last_used_at),
        "use_count": tool.use_count,
        "success_rate": round(tool.success_rate, 4),
        "endpoint": tool.endpoint,
        "code": tool.code,
    }


def serialize_memory_for_mcp(memory: Memory) -> dict[str, Any]:
    """Safely serialize Memory entity for MCP resource consumption."""
    ew = None
    if memory.emotional_weight:
        ew = {
            "valence": memory.emotional_weight.valence,
            "arousal": memory.emotional_weight.arousal,
            "intensity": memory.emotional_weight.intensity,
            "context": memory.emotional_weight.context,
        }
    return {
        "id": str(memory.id),
        "content": memory.content,
        "memory_type": (
            memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type)
        ),
        "concepts": list(memory.concepts),
        "created_at": _iso(memory.created_at),
        "last_accessed_at": _iso(memory.last_accessed_at),
        "access_count": memory.access_count,
        "consolidated": memory.consolidated,
        "metadata": dict(memory.metadata),
        "emotional_weight": ew,
    }


def serialize_goal_for_mcp(goal: Goal) -> dict[str, Any]:
    """Safely serialize Goal entity for MCP resource consumption."""
    plan_steps = [
        {
            "description": s.description,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "tool": s.tool,
            "output": s.output,
            "error": s.error,
        }
        for s in getattr(goal, "plan", getattr(goal, "steps", []))
    ]
    events = [
        {
            "kind": e.kind,
            "detail": e.detail,
            "actor": e.actor,
            "timestamp": _iso(getattr(e, "ts", getattr(e, "timestamp", None))),
        }
        for e in getattr(goal, "history", getattr(goal, "events", []))
    ]
    return {
        "id": str(goal.id),
        "statement": getattr(goal, "statement", getattr(goal, "title", "")),
        "tenant_id": getattr(goal, "tenant_id", "default"),
        "owner_id": getattr(goal, "owner_id", "user"),
        "status": goal.status.value if hasattr(goal.status, "value") else str(goal.status),
        "priority": goal.priority.value if hasattr(goal.priority, "value") else str(goal.priority),
        "budget_units": getattr(goal, "budget_units", getattr(goal, "budget_tokens", 0)),
        "budget_spent": getattr(goal, "budget_spent", getattr(goal, "tokens_used", 0)),
        "created_at": _iso(goal.created_at),
        "updated_at": _iso(goal.updated_at),
        "plan": plan_steps,
        "history": events,
    }


def serialize_agent_for_mcp(agent: Agent) -> dict[str, Any]:
    """Safely serialize Agent entity for MCP resource consumption."""
    return {
        "id": str(agent.id),
        "name": agent.name,
        "tenant_id": getattr(agent, "tenant_id", "default"),
        "owner_id": getattr(agent, "owner_id", "system"),
        "role": agent.role,
        "system_prompt": agent.system_prompt,
        "status": agent.status.value if hasattr(agent.status, "value") else str(agent.status),
        "tools": list(agent.tools),
        "created_at": _iso(agent.created_at),
        "updated_at": _iso(agent.updated_at),
        "metadata": dict(agent.metadata),
    }


def serialize_concept_for_mcp(concept: Concept) -> dict[str, Any]:
    """Safely serialize Concept entity for MCP resource consumption."""
    return {
        "id": str(concept.id),
        "label": concept.label,
        "concept_type": concept.concept_type,
        "properties": dict(concept.properties),
        "strength": round(concept.strength, 4),
        "access_count": concept.access_count,
        "created_at": _iso(concept.created_at),
        "last_accessed_at": _iso(concept.last_accessed_at),
    }


def serialize_conversation_for_mcp(conv: Conversation) -> dict[str, Any]:
    """Safely serialize Conversation entity for MCP resource consumption."""
    msgs = [
        {
            "id": str(m.id),
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
            "content": m.content,
            "timestamp": _iso(m.timestamp),
            "metadata": dict(m.metadata or {}),
        }
        for m in getattr(conv, "messages", [])
    ]
    return {
        "session_id": getattr(conv, "session_id", "default"),
        "user_id": getattr(conv, "user_id", "anonymous"),
        "tenant_id": getattr(conv, "tenant_id", "default"),
        "created_at": _iso(getattr(conv, "created_at", None)),
        "updated_at": _iso(getattr(conv, "updated_at", None)),
        "messages": msgs,
        "active_concepts": list(getattr(conv, "active_concepts", [])),
        "current_task": getattr(conv, "current_task", None),
    }


def serialize_entity_for_mcp(entity: Any) -> dict[str, Any]:
    """Universal dispatcher serializing any recognized domain entity for MCP."""
    if isinstance(entity, Tool):
        return serialize_tool_for_mcp(entity)
    if isinstance(entity, Memory):
        return serialize_memory_for_mcp(entity)
    if isinstance(entity, Goal):
        return serialize_goal_for_mcp(entity)
    if isinstance(entity, Agent):
        return serialize_agent_for_mcp(entity)
    if isinstance(entity, Concept):
        return serialize_concept_for_mcp(entity)
    if isinstance(entity, Conversation):
        return serialize_conversation_for_mcp(entity)
    if hasattr(entity, "to_dict"):
        return entity.to_dict()
    raise TypeError(f"Unsupported entity type for MCP serialization: {type(entity).__name__}")
