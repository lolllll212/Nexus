"""Unit tests for domain-level Model Context Protocol (MCP) support (task-040).

Verifies:
1. ToolSchemaProvider port contract and StandardToolSchemaProvider implementation.
2. Tool schemas export as valid JSON Schema directly consumable by MCP clients.
3. Domain entity serializers (Tool, Memory, Goal, Agent, Concept, Conversation)
   are safe for MCP resources (pure JSON-serializable structures).
4. Clean Architecture: zero nexus.infrastructure imports in new domain code.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.concept import Concept
from nexus.domain.entities.conversation import Conversation, MessageRole
from nexus.domain.entities.goal import Goal, GoalPriority, GoalStatus, GoalStep
from nexus.domain.entities.memory import EmotionalWeight, Memory, MemoryType
from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.mcp import (
    StandardToolSchemaProvider,
    export_json_schema,
    serialize_agent_for_mcp,
    serialize_concept_for_mcp,
    serialize_conversation_for_mcp,
    serialize_entity_for_mcp,
    serialize_goal_for_mcp,
    serialize_memory_for_mcp,
    serialize_tool_for_mcp,
)
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.ports.tool_schema_provider import ToolSchemaProvider
from nexus.domain.value_objects.schema import JSONSchema

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# ToolSchemaProvider & JSON Schema Export Tests
# ---------------------------------------------------------------------------


def test_export_json_schema_validity():
    """Verify JSONSchema value object converts to valid JSON schema dict."""
    schema = JSONSchema(
        type="object",
        description="Search query arguments",
        properties={
            "query": {"type": "string", "description": "The search term"},
            "limit": {"type": "integer", "default": 5},
        },
        required=["query"],
    )
    exported = export_json_schema(schema)
    assert exported["type"] == "object"
    assert exported["description"] == "Search query arguments"
    assert "query" in exported["properties"]
    assert exported["required"] == ["query"]

    # Test None schema fallback
    assert export_json_schema(None) == {"type": "object", "properties": {}, "required": []}


def test_standard_tool_schema_provider_export():
    """Verify StandardToolSchemaProvider exports MCP-compliant tool definitions."""
    provider = StandardToolSchemaProvider()
    assert isinstance(provider, ToolSchemaProvider)

    tool = Tool(
        name="web_search",
        description="Performs an external web search query",
        input_schema=JSONSchema(
            type="object",
            properties={
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "default": 3},
            },
            required=["query"],
        ),
        output_schema=JSONSchema(
            type="object",
            properties={"results": {"type": "array"}},
            required=["results"],
        ),
        status=ToolStatus.READY,
        version="1.2.0",
        is_self_generated=False,
    )

    mcp_spec = provider.export_schema(tool)

    # Validate structure expected by MCP clients and Xenom's MCP server route
    assert mcp_spec["name"] == "web_search"
    assert mcp_spec["description"] == "Performs an external web search query"
    assert mcp_spec["category"] == "builtin"
    assert mcp_spec["version"] == "1.2.0"
    assert mcp_spec["required"] == ["query"]
    assert "query" in mcp_spec["parameters"]

    # InputSchema must be standard MCP object format
    in_schema = mcp_spec["inputSchema"]
    assert in_schema["type"] == "object"
    assert "query" in in_schema["properties"]
    assert in_schema["required"] == ["query"]

    # Verify JSON serializability
    serialized = json.dumps(mcp_spec)
    assert isinstance(json.loads(serialized), dict)


@pytest.mark.asyncio
async def test_tool_schema_provider_export_registry():
    """Verify ToolSchemaProvider can export tools directly from a domain ToolRegistry."""

    class InMemoryToolRegistry(ToolRegistry):
        def __init__(self, tools: list[Tool]):
            self._tools = {t.id: t for t in tools}

        async def register(self, tool: Tool) -> None:
            self._tools[tool.id] = tool

        async def get(self, tool_id: str) -> Tool | None:
            return self._tools.get(tool_id)

        async def search(self, query: str, limit: int = 5) -> list[Tool]:
            return [t for t in self._tools.values() if query in t.name][:limit]

        async def list_all(self) -> list[Tool]:
            return list(self._tools.values())

        async def update(self, tool: Tool) -> None:
            self._tools[tool.id] = tool

    t1 = Tool(
        name="tool_one",
        description="First tool",
        input_schema=JSONSchema(properties={"a": {"type": "string"}}, required=["a"]),
        output_schema=JSONSchema(properties={"res": {"type": "string"}}),
    )
    t2 = Tool(
        name="tool_two",
        description="Second tool (self-generated)",
        input_schema=JSONSchema(properties={"b": {"type": "number"}}),
        output_schema=JSONSchema(properties={}),
        is_self_generated=True,
    )

    reg = InMemoryToolRegistry([t1, t2])
    provider = StandardToolSchemaProvider()
    exported = await provider.export_registry(reg)

    assert len(exported) == 2
    names = {s["name"] for s in exported}
    assert names == {"tool_one", "tool_two"}

    categories = {s["name"]: s["category"] for s in exported}
    assert categories["tool_one"] == "builtin"
    assert categories["tool_two"] == "generated"


# ---------------------------------------------------------------------------
# Domain Entity Serialization for MCP Resources Tests
# ---------------------------------------------------------------------------


def test_serialize_tool_for_mcp():
    """Verify Tool serialization is clean, complete, and JSON-safe."""
    tool = Tool(
        name="calculator",
        description="Math operations",
        input_schema=JSONSchema(properties={"expr": {"type": "string"}}, required=["expr"]),
        output_schema=JSONSchema(properties={"result": {"type": "number"}}),
        code="def solve(expr): return eval(expr)",
        status=ToolStatus.READY,
        version="2.0.0",
        endpoint="https://api.nexus.internal/tools/calculator",
    )
    data = serialize_tool_for_mcp(tool)
    assert data["name"] == "calculator"
    assert data["status"] == "ready"
    assert data["code"] == "def solve(expr): return eval(expr)"
    assert data["endpoint"] == "https://api.nexus.internal/tools/calculator"
    json_str = json.dumps(data)
    assert "calculator" in json_str


def test_serialize_memory_for_mcp():
    """Verify Memory serialization handles enums and emotional weights safely."""
    mem = Memory(
        content="Learned to handle timeout gracefully in HTTP requests",
        memory_type=MemoryType.SEMANTIC,
        concepts=["concept-http", "concept-resilience"],
        emotional_weight=EmotionalWeight(valence=0.8, arousal=0.4, context="stability"),
        created_at=datetime(2026, 10, 2, 8, 0, 0, tzinfo=timezone.utc),
    )
    data = serialize_memory_for_mcp(mem)
    assert data["content"] == mem.content
    assert data["memory_type"] == "semantic"
    assert data["concepts"] == ["concept-http", "concept-resilience"]
    assert data["emotional_weight"]["valence"] == 0.8
    assert data["emotional_weight"]["intensity"] == pytest.approx(0.6)
    assert data["created_at"].startswith("2026-10-02T08:00:00")
    json.dumps(data)


def test_serialize_goal_for_mcp():
    """Verify Goal serialization handles steps, events, and token metrics."""
    goal = Goal(
        statement="Upgrade test coverage",
        tenant_id="default",
        owner_id="tron",
        budget_units=50000,
        status=GoalStatus.ACTIVE,
        priority=GoalPriority.HIGH,
    )
    goal.plan.append(GoalStep(description="Run pytest with coverage", tool="pytest_runner"))
    goal.log("step_started", "Step 1 started")

    data = serialize_goal_for_mcp(goal)
    assert data["statement"] == "Upgrade test coverage"
    assert data["status"] == "active"
    assert data["priority"] == "high"
    assert len(data["plan"]) == 1
    assert data["plan"][0]["tool"] == "pytest_runner"
    assert len(data["history"]) == 1
    assert data["budget_units"] == 50000
    assert data["budget_spent"] == 0
    json.dumps(data)


def test_serialize_agent_for_mcp():
    """Verify Agent serialization formats capabilities and tools properly."""
    agent = Agent(
        name="tron",
        tenant_id="default",
        owner_id="system",
        system_prompt="Guard hexagonal architecture.",
        role="Domain Architect",
        tools=["pytest", "ruff", "black"],
    )
    data = serialize_agent_for_mcp(agent)
    assert data["name"] == "tron"
    assert data["role"] == "Domain Architect"
    assert "pytest" in data["tools"]
    json.dumps(data)


def test_serialize_concept_and_conversation_for_mcp():
    """Verify Concept and Conversation serialization formats."""
    concept = Concept(
        label="HexagonalArchitecture",
        concept_type="architecture",
        properties={"domain": "nexus"},
    )
    concept_data = serialize_concept_for_mcp(concept)
    assert concept_data["label"] == "HexagonalArchitecture"
    assert concept_data["concept_type"] == "architecture"
    assert concept_data["properties"]["domain"] == "nexus"
    json.dumps(concept_data)

    conv = Conversation(session_id="sess-1", user_id="user-123")
    conv.add_message(MessageRole.USER, "Hello Nexus")
    conv.add_message(MessageRole.NEXUS, "Greetings!")
    conv_data = serialize_conversation_for_mcp(conv)
    assert conv_data["user_id"] == "user-123"
    assert len(conv_data["messages"]) == 2
    assert conv_data["messages"][0]["role"] == "user"
    json.dumps(conv_data)


def test_serialize_entity_universal_dispatcher():
    """Verify serialize_entity_for_mcp dispatches correctly for all domain entities."""
    tool = Tool(
        name="test_tool",
        description="desc",
        input_schema=JSONSchema(),
        output_schema=JSONSchema(),
    )
    mem = Memory(content="fact", memory_type=MemoryType.EPISODIC)
    goal = Goal(statement="goal", tenant_id="default", owner_id="tron", budget_units=100)

    assert serialize_entity_for_mcp(tool)["name"] == "test_tool"
    assert serialize_entity_for_mcp(mem)["content"] == "fact"
    assert serialize_entity_for_mcp(goal)["statement"] == "goal"

    with pytest.raises(TypeError):
        serialize_entity_for_mcp(12345)


# ---------------------------------------------------------------------------
# Clean Architecture Verification
# ---------------------------------------------------------------------------


def test_clean_architecture_domain_independence():
    """Domain files for MCP must never import from nexus.infrastructure."""
    target_files = [
        REPO_ROOT / "src" / "nexus" / "domain" / "ports" / "tool_schema_provider.py",
        REPO_ROOT / "src" / "nexus" / "domain" / "mcp.py",
    ]
    for py_file in target_files:
        assert py_file.exists(), f"Expected file {py_file} does not exist"
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(
                        "nexus.infrastructure"
                    ), f"Domain file {py_file.name} illegally imports {alias.name} at line {node.lineno}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith(
                        "nexus.infrastructure"
                    ), f"Domain file {py_file.name} illegally imports from {node.module} at line {node.lineno}"
