"""
Container - the composition root of NEXUS.

This is the ONLY place where concrete adapters are chosen and wired
together. Swapping Redis for Kafka, Neo4j for Memgraph, OpenAI for Llama
means editing THIS file (or its config) - never the application layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from nexus.domain.value_objects.synapse import SynapseConfig

# Ports (abstractions)
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.event_bus import EventBus
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.llm_provider import LLMProvider, EmbeddingProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.ports.deployment import DeploymentProvider

# Application (use cases)
from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.application.cortex.session_manager import SessionManager
from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator
from nexus.application.subcortex.amygdala import AmygdalaUseCase
from nexus.application.subcortex.basal_ganglia import BasalGangliaUseCase
from nexus.application.subcortex.synthesis import EntitySynthesisUseCase
from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase
from nexus.application.subcortex.pattern_detection import PatternDetectionUseCase
from nexus.application.subcortex.thalamus import ThalamicGatingUseCase
from nexus.application.tools.generate_tool import GenerateToolUseCase
from nexus.application.tools.self_heal import SelfHealUseCase


@dataclass
class Config:
    """Runtime configuration loaded from env vars."""
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("NEXUS_LLM_MODEL", "gpt-4o"))
    embedding_model: str = field(default_factory=lambda: os.getenv("NEXUS_EMBEDDING_MODEL", "text-embedding-3-large"))
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))
    qdrant_host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    qdrant_port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    qdrant_shard_number: int = field(default_factory=lambda: int(os.getenv("QDRANT_SHARD_NUMBER", "1")))
    qdrant_replication_factor: int = field(default_factory=lambda: int(os.getenv("QDRANT_REPLICATION_FACTOR", "1")))
    cors_origins: list = field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("NEXUS_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ]
    )


class Container:
    """Composition root - wires all adapters into the use cases."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._started = False
        self._shutdown = False

        # ---- Ports (concrete adapters chosen here) ----
        self.event_bus: EventBus = self._build_event_bus()
        self.embedder: EmbeddingProvider = self._build_embedder()
        self.llm: LLMProvider = self._build_llm()
        self.sandbox: Sandbox = self._build_sandbox()
        self.memory_repo: MemoryRepository = self._build_memory_repo()
        self.concept_repo: ConceptRepository = self._build_concept_repo()
        self.working_memory: ShortTermMemory = self._build_working_memory()
        self.synapse: SynapseConfig = SynapseConfig()
        self.tool_registry: ToolRegistry = self._build_tool_registry()
        self.deployer: DeploymentProvider | None = self._build_deployer()
        self.executor: ToolExecutor = self._build_executor()
        self.column_registry: CorticalColumnRegistry = self._build_column_registry()
        self.policy_store: ActionPolicyStore = self._build_policy_store()

        # ---- Use cases (application) ----
        self.session_manager = SessionManager(self.working_memory)
        self.process_message = ProcessMessageUseCase(
            llm=self.llm,
            memory_repo=self.memory_repo,
            concept_repo=self.concept_repo,
            working_memory=self.working_memory,
            tools=self.tool_registry,
            executor=self.executor,
            event_bus=self.event_bus,
            session_manager=self.session_manager,
        )
        self.entity_synthesis = EntitySynthesisUseCase(self.llm, self.concept_repo, self.memory_repo, self.event_bus)
        self.pattern_detection = PatternDetectionUseCase(self.llm, self.memory_repo, self.event_bus)
        self.dream_session = DreamSessionUseCase(
            llm=self.llm,
            memory_repo=self.memory_repo,
            concept_repo=self.concept_repo,
            working_memory=self.working_memory,
            sandbox=self.sandbox,
            executor=self.executor,
            synapse=self.synapse,
            event_bus=self.event_bus,
        )
        self.tool_generator = GenerateToolUseCase(
            llm=self.llm,
            sandbox=self.sandbox,
            registry=self.tool_registry,
            executor=self.executor,
            deployer=self.deployer,
        )
        self.self_heal = SelfHealUseCase(self.tool_registry, self.tool_generator)

        # ---- Subcortex control loops ----
        self.thalamus = ThalamicGatingUseCase(self.column_registry, self.event_bus)
        self.basal_ganglia = BasalGangliaUseCase(self.column_registry, self.policy_store, self.event_bus)
        self.amygdala = AmygdalaUseCase(self.event_bus)
        self.subconscious = SubconsciousCoordinator(
            event_bus=self.event_bus,
            entity_synthesis=self.entity_synthesis,
            pattern_detection=self.pattern_detection,
            dream_session=self.dream_session,
            dream_hour=int(os.getenv("NEXUS_DREAM_HOUR", "3")),
            pattern_interval_seconds=int(os.getenv("NEXUS_PATTERN_INTERVAL_SECONDS", "1800")),
            thalamus=self.thalamus,
            basal_ganglia=self.basal_ganglia,
            amygdala=self.amygdala,
        )

    # ------------------------------------------------------------------ #
    #  Adapter factories - the only place technology is decided
    # ------------------------------------------------------------------ #

    def _build_event_bus(self) -> EventBus:
        from nexus.infrastructure.adapters.eventbus.redis_event_bus import RedisEventBus

        return RedisEventBus(host=self.config.redis_host, port=self.config.redis_port)

    def _build_embedder(self) -> EmbeddingProvider:
        from nexus.infrastructure.adapters.embedding.openai_embedder import OpenAIEmbedder

        return OpenAIEmbedder(api_key=self.config.openai_api_key, model=self.config.embedding_model)

    def _build_llm(self) -> LLMProvider:
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=self.config.openai_api_key, model=self.config.llm_model)

    def _build_sandbox(self) -> Sandbox:
        from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

        return SubprocessSandbox()

    def _build_memory_repo(self) -> MemoryRepository:
        from nexus.infrastructure.adapters.persistence.qdrant_memory_repository import QdrantMemoryRepository

        return QdrantMemoryRepository(
            host=self.config.qdrant_host,
            port=self.config.qdrant_port,
            embedder=self.embedder,
            shard_number=self.config.qdrant_shard_number,
            replication_factor=self.config.qdrant_replication_factor,
        )

    def _build_concept_repo(self) -> ConceptRepository:
        from nexus.infrastructure.adapters.persistence.neo4j_concept_repository import Neo4jConceptRepository

        return Neo4jConceptRepository(
            uri=self.config.neo4j_uri,
            user=self.config.neo4j_user,
            password=self.config.neo4j_password,
            synapse=self.synapse,
        )

    def _build_working_memory(self) -> ShortTermMemory:
        from nexus.infrastructure.adapters.persistence.redis_short_term_memory import RedisShortTermMemory

        return RedisShortTermMemory(host=self.config.redis_host, port=self.config.redis_port)

    def _build_tool_registry(self) -> ToolRegistry:
        from nexus.infrastructure.adapters.execution.builtin_tools import BuiltinToolRegistry, default_builtin_tools

        return BuiltinToolRegistry(default_builtin_tools())

    def _build_deployer(self) -> DeploymentProvider | None:
        from nexus.infrastructure.adapters.deployment.local_deployer import LocalDeployer

        return LocalDeployer()

    def _build_executor(self) -> ToolExecutor:
        from nexus.infrastructure.adapters.execution.registry_tool_executor import RegistryBackedToolExecutor

        builtin_handlers = {
            "calculator": lambda p: {"result": _safe_eval(p.get("expression", ""))},
            "run_python": lambda p: self.sandbox.run(p.get("code", "")),
            "web_search": lambda p: {"results": [], "query": p.get("query", "")},
        }
        return RegistryBackedToolExecutor(self.tool_registry, self.sandbox, builtin_handlers)

    def _build_column_registry(self) -> CorticalColumnRegistry:
        from nexus.infrastructure.adapters.cognition import InMemoryCorticalColumnRegistry

        return InMemoryCorticalColumnRegistry()

    def _build_policy_store(self) -> ActionPolicyStore:
        from nexus.infrastructure.adapters.cognition import InMemoryActionPolicyStore

        return InMemoryActionPolicyStore()

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self.event_bus.start()
        await self.memory_repo.ensure_collection()

    async def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        await self.event_bus.stop()
        if hasattr(self.memory_repo, "close"):
            await self.memory_repo.close()
        if hasattr(self.concept_repo, "close"):
            await self.concept_repo.close()
        if hasattr(self.working_memory, "close"):
            await self.working_memory.close()


def _safe_eval(expr: str) -> float:
    import ast

    tree = ast.parse(expr, mode="eval")
    allowed = (ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"Disallowed expression element: {type(node).__name__}")
    return eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
