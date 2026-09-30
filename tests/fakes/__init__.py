"""
Fake adapters - in-memory implementations of the ports.

These prove the dependency rule: the application layer runs fully against
fakes, meaning it is completely decoupled from Redis/Neo4j/Qdrant/OpenAI.
"""

from __future__ import annotations

from typing import Any

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.cortex import CorticalColumn
from nexus.domain.entities.memory import Memory
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic
from nexus.domain.ports.llm_provider import EmbeddingProvider, LLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.speech import SpeechToText, TextToSpeech
from nexus.domain.ports.tool_registry import ToolExecutor, ToolRegistry
from nexus.domain.value_objects.schema import JSONSchema
from nexus.domain.value_objects.synapse import ConnectionType


class FakeEventBus(EventBus):
    """Records published events; allows handlers to be registered."""

    def __init__(self) -> None:
        self.published: list[Event] = []
        self._handlers: dict[str, list[EventHandler]] = {}

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
        self.memories: dict[str, Memory] = {}
        self._tenant: dict[str, str] = {}

    async def store(self, memory: Memory, tenant_id: str = "default") -> None:
        self.memories[memory.id] = memory
        self._tenant[memory.id] = tenant_id

    async def retrieve(
        self, query: str, limit: int = 10, memory_types: list | None = None, tenant_id: str = "default"
    ) -> list[Memory]:
        results = [m for m in self.memories.values() if self._tenant.get(m.id) == tenant_id]
        if memory_types:
            results = [m for m in results if m.memory_type in memory_types]
        return results[:limit]

    async def get_by_id(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    async def find_stale(
        self, threshold_days: int, limit: int = 100, min_accesses: int = 1, tenant_id: str = "default"
    ) -> list[Memory]:
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(days=threshold_days)
        stale = []
        for m in self.memories.values():
            if self._tenant.get(m.id) != tenant_id:
                continue
            last = m.last_accessed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=datetime.timezone.utc)
            if last < cutoff and m.access_count < min_accesses:
                stale.append(m)
        return stale[:limit]

    async def delete(self, memory_id: str, tenant_id: str = "default") -> None:
        self.memories.pop(memory_id, None)
        self._tenant.pop(memory_id, None)

    async def delete_many(self, memory_ids: list[str], tenant_id: str = "default") -> None:
        for memory_id in memory_ids:
            self.memories.pop(memory_id, None)
            self._tenant.pop(memory_id, None)

    async def record_access(self, memory_id: str, tenant_id: str = "default") -> None:
        if memory_id in self.memories:
            self.memories[memory_id].accessed()

    async def find_by_emotional_weight(
        self, min_intensity: float, limit: int = 100, tenant_id: str = "default"
    ) -> list[Memory]:
        charged = [
            m
            for m in self.memories.values()
            if self._tenant.get(m.id) == tenant_id
            and m.emotional_weight
            and m.emotional_weight.intensity >= min_intensity
        ]
        charged.sort(key=lambda m: m.emotional_weight.intensity, reverse=True)
        return charged[:limit]


class FakeConceptRepository(ConceptRepository):
    def __init__(self) -> None:
        self.concepts: dict[str, Concept] = {}
        self.connections: dict[str, list[SynapticConnection]] = {}
        self._tenant_concepts: dict[str, str] = {}
        self._tenant_connections: dict[str, str] = {}

    async def upsert(self, concept: Concept, tenant_id: str = "default") -> None:
        self.concepts[concept.id] = concept
        self._tenant_concepts[concept.id] = tenant_id

    async def get(self, concept_id: str, tenant_id: str = "default") -> Concept | None:
        concept = self.concepts.get(concept_id)
        if concept is None or self._tenant_concepts.get(concept_id) != tenant_id:
            return None
        return concept

    async def get_memories(self, concept_id: str, tenant_id: str = "default") -> list[Memory]:
        """Return memories linked to concept IDs. Fake returns empty unless concept has memories."""
        return []

    async def find_by_label(self, label: str, limit: int = 10, tenant_id: str = "default") -> list[Concept]:
        return [
            c
            for cid, c in self.concepts.items()
            if self._tenant_concepts.get(cid) == tenant_id and label.lower() in c.label.lower()
        ][:limit]

    async def upsert_connection(self, connection: SynapticConnection, tenant_id: str = "default") -> None:
        self.connections.setdefault(connection.source_id, []).append(connection)
        self._tenant_connections[connection.id] = tenant_id

    async def get_connections(
        self, concept_id: str, min_weight: float = 0.0, tenant_id: str = "default"
    ) -> list[SynapticConnection]:
        return [
            c
            for c in self.connections.get(concept_id, [])
            if c.weight >= min_weight and self._tenant_connections.get(c.id) == tenant_id
        ]

    async def get_or_create(
        self, label: str, concept_type: str, properties: dict | None = None, tenant_id: str = "default"
    ) -> Concept:
        existing = [
            c
            for cid, c in self.concepts.items()
            if self._tenant_concepts.get(cid) == tenant_id and c.label == label
        ]
        if existing:
            existing[0].strengthen()
            return existing[0]
        c = Concept(label=label, concept_type=concept_type, properties=properties or {})
        self.concepts[c.id] = c
        self._tenant_concepts[c.id] = tenant_id
        return c

    async def connect(
        self,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.SEMANTIC,
        tenant_id: str = "default",
    ) -> SynapticConnection:
        conn = SynapticConnection(source_id=source_id, target_id=target_id, connection_type=connection_type)
        await self.upsert_connection(conn, tenant_id=tenant_id)
        return conn

    async def find_weakest(self, limit: int = 100, tenant_id: str = "default") -> list[SynapticConnection]:
        all_conns = [
            c
            for conns in self.connections.values()
            for c in conns
            if self._tenant_connections.get(c.id) == tenant_id
        ]
        return sorted(all_conns, key=lambda c: c.weight)[:limit]

    async def delete_connection(self, connection_id: str, tenant_id: str = "default") -> None:
        for key in self.connections:
            self.connections[key] = [c for c in self.connections[key] if c.id != connection_id]
        self._tenant_connections.pop(connection_id, None)


class FakeShortTermMemory(ShortTermMemory):
    def __init__(self) -> None:
        self.store_: dict[str, dict] = {}

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.store_[key] = value

    async def get(self, key: str) -> dict | None:
        return self.store_.get(key)

    async def delete(self, key: str) -> None:
        self.store_.pop(key, None)

    async def publish(self, channel: str, payload: dict) -> None:
        pass


class FakeLLM(LLMProvider):
    """Scripted LLM for deterministic tests."""

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> str:
        if "complete" in self.script:
            return self.script["complete"]
        return "FINAL ANSWER: Test response"

    async def extract_structured(self, content: str, schema: JSONSchema, instructions: str = "") -> dict:
        if "extract" in self.script:
            return self.script["extract"]
        return {"entities": []}


class FakeEmbedder(EmbeddingProvider):
    def __init__(self) -> None:
        self.dim = 8

    @property
    def dimension(self) -> int:
        return self.dim

    async def embed(self, text: str) -> list[float]:
        return [float(len(text))] * self.dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class FakeSandbox(Sandbox):
    def __init__(self) -> None:
        self.project_runs: list[dict[str, Any]] = []
        self.fail_project: bool = False

    async def run(self, code: str, inputs: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        inputs = inputs or {}
        try:
            ns = {}
            exec(code, ns)
            if "solve" in ns and callable(ns["solve"]):
                result = ns["solve"](inputs)
                return {"ok": True, "result": result, "duration_ms": 1}
            return {"ok": True, "result": code[:50], "duration_ms": 1}
        except Exception as e:
            return {"ok": False, "error": str(e), "duration_ms": 1}

    async def run_code(self, code: str, timeout: int = 30) -> dict[str, Any]:
        return {"output": "Fake sandbox executed code successfully", "error": "", "duration_ms": 1}

    async def run_project(
        self, files: dict[str, str], test_command: str = "python -m pytest -q", timeout: int = 120
    ) -> dict[str, Any]:
        self.project_runs.append({"files": files, "test_command": test_command})
        if self.fail_project:
            return {"output": "", "error": "tests failed: assert 0", "duration_ms": 5}
        return {"output": "1 passed", "error": "", "duration_ms": 5}


class FakeToolRegistry(ToolRegistry):
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    async def register(self, tool: Tool) -> None:
        self.tools[tool.id] = tool

    async def get(self, tool_id: str) -> Tool | None:
        return self.tools.get(tool_id)

    async def search(self, query: str, limit: int = 5) -> list[Tool]:
        return list(self.tools.values())[:limit]

    async def list_all(self) -> list[Tool]:
        return list(self.tools.values())

    async def update(self, tool: Tool) -> None:
        self.tools[tool.id] = tool


class FakeExecutor(ToolExecutor):
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
        self.executed.append(tool_id)
        return {"ok": True, "result": "tool-executed"}


class FakeSpeechToText(SpeechToText):
    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}
        self.calls = []

    async def transcribe(self, audio: bytes, mime_type: str = "audio/mpeg") -> str:
        self.calls.append({"bytes": audio, "mime": mime_type})
        return self.script.get("transcribe", "transcribed audio text")


class FakeTextToSpeech(TextToSpeech):
    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}
        self.calls = []

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        self.calls.append({"text": text, "voice": voice})
        return self.script.get("audio", b"\x00audio-payload")


class FakeCorticalColumnRegistry(CorticalColumnRegistry):
    def __init__(self) -> None:
        self.columns: dict[str, CorticalColumn] = {}

    async def upsert(self, column: CorticalColumn) -> None:
        self.columns[column.id] = column

    async def get(self, column_id: str) -> CorticalColumn | None:
        return self.columns.get(column_id)

    async def list_all(self) -> list[CorticalColumn]:
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
        self.state: dict[str, dict[str, float]] = {}

    async def get_value(self, state_key: str, action_id: str) -> float:
        return self.state.get(state_key, {}).get(action_id, 0.0)

    async def set_value(self, state_key: str, action_id: str, value: float) -> None:
        self.state.setdefault(state_key, {})[action_id] = value

    async def get_state(self, state_key: str) -> dict[str, float]:
        return dict(self.state.get(state_key, {}))

    async def reset(self, state_key: str) -> None:
        self.state.pop(state_key, None)
