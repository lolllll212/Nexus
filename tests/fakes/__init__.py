"""
Fake adapters - in-memory implementations of the ports.

These prove the dependency rule: the application layer runs fully against
fakes, meaning it is completely decoupled from Redis/Neo4j/Qdrant/OpenAI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.cortex import CorticalColumn
from nexus.domain.entities.memory import Memory
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic
from nexus.domain.ports.llm_provider import LLMProvider, EmbeddingProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry, ToolExecutor
from nexus.domain.value_objects.synapse import ConnectionType
from nexus.domain.value_objects.schema import JSONSchema


class FakeEventBus(EventBus):
    """Records published events; allows handlers to be registered."""

    def __init__(self) -> None:
        self.published: List[Event] = []
        self._handlers: Dict[str, List[EventHandler]] = {}

    async def publish(self, event: Event) -> None:
        self.published.append(event)
        for handler in self._handlers.get(event.topic.value, []):
            await handler(event)

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._handlers.setdefault(topic.value, []).append(handler)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self.memories: Dict[str, Memory] = {}

    async def store(self, memory: Memory) -> None:
        self.memories[memory.id] = memory

    async def retrieve(self, query: str, limit: int = 10, memory_types: Optional[list] = None) -> List[Memory]:
        results = [m for m in self.memories.values()]
        if memory_types:
            results = [m for m in results if m.memory_type in memory_types]
        return results[:limit]

    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        return self.memories.get(memory_id)

    async def find_stale(self, threshold_days: int, limit: int = 100, min_accesses: int = 1) -> List[Memory]:
        import datetime

        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=threshold_days)
        stale = [
            m
            for m in self.memories.values()
            if m.last_accessed_at < cutoff and m.access_count < min_accesses
        ]
        return stale[:limit]

    async def delete(self, memory_id: str) -> None:
        self.memories.pop(memory_id, None)

    async def delete_many(self, memory_ids: List[str]) -> None:
        for memory_id in memory_ids:
            self.memories.pop(memory_id, None)

    async def record_access(self, memory_id: str) -> None:
        if memory_id in self.memories:
            self.memories[memory_id].accessed()

    async def find_by_emotional_weight(self, min_intensity: float, limit: int = 100) -> List[Memory]:
        charged = [
            m for m in self.memories.values() if m.emotional_weight and m.emotional_weight.intensity >= min_intensity
        ]
        charged.sort(key=lambda m: m.emotional_weight.intensity, reverse=True)
        return charged[:limit]


class FakeConceptRepository(ConceptRepository):
    def __init__(self) -> None:
        self.concepts: Dict[str, Concept] = {}
        self.connections: Dict[str, List[SynapticConnection]] = {}

    async def upsert(self, concept: Concept) -> None:
        self.concepts[concept.id] = concept

    async def get(self, concept_id: str) -> Optional[Concept]:
        return self.concepts.get(concept_id)

    async def find_by_label(self, label: str, limit: int = 10) -> List[Concept]:
        return [c for c in self.concepts.values() if label.lower() in c.label.lower()][:limit]

    async def upsert_connection(self, connection: SynapticConnection) -> None:
        self.connections.setdefault(connection.source_id, []).append(connection)

    async def get_connections(self, concept_id: str, min_weight: float = 0.0) -> List[SynapticConnection]:
        return [c for c in self.connections.get(concept_id, []) if c.weight >= min_weight]

    async def get_or_create(self, label: str, concept_type: str, properties: Optional[Dict] = None) -> Concept:
        existing = [c for c in self.concepts.values() if c.label == label]
        if existing:
            existing[0].strengthen()
            return existing[0]
        c = Concept(label=label, concept_type=concept_type, properties=properties or {})
        self.concepts[c.id] = c
        return c

    async def connect(self, source_id: str, target_id: str, connection_type: ConnectionType = ConnectionType.SEMANTIC) -> SynapticConnection:
        conn = SynapticConnection(source_id=source_id, target_id=target_id, connection_type=connection_type)
        await self.upsert_connection(conn)
        return conn

    async def find_weakest(self, limit: int = 100) -> List[SynapticConnection]:
        all_conns = [c for conns in self.connections.values() for c in conns]
        return sorted(all_conns, key=lambda c: c.weight)[:limit]

    async def delete_connection(self, connection_id: str) -> None:
        for key in self.connections:
            self.connections[key] = [c for c in self.connections[key] if c.id != connection_id]


class FakeShortTermMemory(ShortTermMemory):
    def __init__(self) -> None:
        self.store_: Dict[str, Dict] = {}

    async def set(self, key: str, value: Dict, ttl_seconds: int) -> None:
        self.store_[key] = value

    async def get(self, key: str) -> Optional[Dict]:
        return self.store_.get(key)

    async def delete(self, key: str) -> None:
        self.store_.pop(key, None)

    async def publish(self, channel: str, payload: Dict) -> None:
        pass


class FakeLLM(LLMProvider):
    """Scripted LLM for deterministic tests."""

    def __init__(self, script: Optional[Dict[str, Any]] = None) -> None:
        self.script = script or {}

    async def complete(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4096, tools: Optional[List[Dict]] = None) -> str:
        if "complete" in self.script:
            return self.script["complete"]
        return "FINAL ANSWER: Test response"

    async def extract_structured(self, content: str, schema: JSONSchema, instructions: str = "") -> Dict:
        if "extract" in self.script:
            return self.script["extract"]
        return {"entities": []}


class FakeEmbedder(EmbeddingProvider):
    def __init__(self) -> None:
        self.dim = 8

    @property
    def dimension(self) -> int:
        return self.dim

    async def embed(self, text: str) -> List[float]:
        return [float(len(text))] * self.dim

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]


class FakeSandbox(Sandbox):
    def __init__(self) -> None:
        self.project_runs: List[Dict[str, Any]] = []
        self.fail_project: bool = False

    async def run(self, code: str, inputs: Dict[str, Any] = None, timeout: int = 30) -> Dict[str, Any]:
        return {"ok": True, "result": "sandboxed-ok", "duration_ms": 1}

    async def run_project(
        self, files: Dict[str, str], test_command: str = "python -m pytest -q", timeout: int = 120
    ) -> Dict[str, Any]:
        self.project_runs.append({"files": files, "test_command": test_command})
        if self.fail_project:
            return {"output": "", "error": "tests failed: assert 0", "duration_ms": 5}
        return {"output": "1 passed", "error": "", "duration_ms": 5}


class FakeToolRegistry(ToolRegistry):
    def __init__(self) -> None:
        self.tools: Dict[str, Tool] = {}

    async def register(self, tool: Tool) -> None:
        self.tools[tool.id] = tool

    async def get(self, tool_id: str) -> Optional[Tool]:
        return self.tools.get(tool_id)

    async def search(self, query: str, limit: int = 5) -> List[Tool]:
        return list(self.tools.values())[:limit]

    async def list_all(self) -> List[Tool]:
        return list(self.tools.values())

    async def update(self, tool: Tool) -> None:
        self.tools[tool.id] = tool


class FakeExecutor(ToolExecutor):
    async def execute(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "result": "tool-executed"}


class FakeCorticalColumnRegistry(CorticalColumnRegistry):
    def __init__(self) -> None:
        self.columns: Dict[str, CorticalColumn] = {}

    async def upsert(self, column: CorticalColumn) -> None:
        self.columns[column.id] = column

    async def get(self, column_id: str) -> Optional[CorticalColumn]:
        return self.columns.get(column_id)

    async def list_all(self) -> List[CorticalColumn]:
        return list(self.columns.values())

    async def get_or_create(self, name: str, **kwargs) -> CorticalColumn:
        for column in self.columns.values():
            if column.name == name:
                return column
        column = CorticalColumn(name=name, **kwargs)
        self.columns[column.id] = column
        return column


class FakeActionPolicyStore(ActionPolicyStore):
    def __init__(self) -> None:
        self.state: Dict[str, Dict[str, float]] = {}

    async def get_value(self, state_key: str, action_id: str) -> float:
        return self.state.get(state_key, {}).get(action_id, 0.0)

    async def set_value(self, state_key: str, action_id: str, value: float) -> None:
        self.state.setdefault(state_key, {})[action_id] = value

    async def get_state(self, state_key: str) -> Dict[str, float]:
        return dict(self.state.get(state_key, {}))

    async def reset(self, state_key: str) -> None:
        self.state.pop(state_key, None)
