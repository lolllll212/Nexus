"""
Container - the composition root of NEXUS.

This is the ONLY place where concrete adapters are chosen and wired
together. Swapping Redis for Kafka, Neo4j for Memgraph, OpenAI for Llama
means editing THIS file (or its config) - never the application layer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from nexus.domain.value_objects.synapse import SynapseConfig

# Ports (abstractions)
from nexus.domain.ports.auth import Authenticator
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.event_bus import EventBus
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.llm_provider import LLMProvider, EmbeddingProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.observability import Metrics, Tracer
from nexus.domain.ports.rate_limiter import RateLimiter
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.secrets import SecretStore
from nexus.domain.ports.speech import SpeechToText, TextToSpeech
from nexus.domain.ports.swarm import AgentRepository, SwarmRepository
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
from nexus.application.autonomy.goals import (
    ApproveGoalUseCase,
    AutonomyLoopUseCase,
    CancelGoalUseCase,
    CreateGoalUseCase,
    GetGoalUseCase,
    ListGoalsUseCase,
)
from nexus.domain.ports.autonomy import AutonomyPolicy
from nexus.domain.ports.goal_repository import GoalRepository


def _parse_json_env(name: str, default: dict | None = None) -> dict:
    raw = os.getenv(name, "")
    if not raw:
        return default or {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default or {}


@dataclass
class Config:
    """Runtime configuration loaded from env vars."""

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("NEXUS_LLM_MODEL", "gpt-4o"))
    llm_max_tokens: int = field(default_factory=lambda: int(os.getenv("NEXUS_LLM_MAX_TOKENS", "8192")))
    embedding_model: str = field(
        default_factory=lambda: os.getenv("NEXUS_EMBEDDING_MODEL", "text-embedding-3-large")
    )
    # Offline LLM (Ollama / LM Studio): point the OpenAI-compatible adapters at a local base URL.
    llm_base_url: str | None = field(default_factory=lambda: os.getenv("NEXUS_LLM_BASE_URL"))
    embedding_base_url: str | None = field(default_factory=lambda: os.getenv("NEXUS_EMBEDDING_BASE_URL"))
    embedding_dimension: int = field(
        default_factory=lambda: int(os.getenv("NEXUS_EMBEDDING_DIMENSION", "1536"))
    )
    # Background LLM (hybrid): a second provider for background loops
    # (subconscious synthesis, dreaming, autonomy). Leave unset to reuse the
    # primary LLM. E.g. Groq for live chat, Ollama for the nightly loops.
    background_llm_api_key: str | None = field(
        default_factory=lambda: os.getenv("NEXUS_BACKGROUND_LLM_API_KEY")
    )
    background_llm_model: str = field(
        default_factory=lambda: os.getenv("NEXUS_BACKGROUND_LLM_MODEL")
        or os.getenv("NEXUS_LLM_MODEL", "gpt-4o")
    )
    background_llm_base_url: str | None = field(
        default_factory=lambda: os.getenv("NEXUS_BACKGROUND_LLM_BASE_URL")
    )
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))
    qdrant_host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    qdrant_port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    qdrant_shard_number: int = field(default_factory=lambda: int(os.getenv("QDRANT_SHARD_NUMBER", "1")))
    qdrant_replication_factor: int = field(
        default_factory=lambda: int(os.getenv("QDRANT_REPLICATION_FACTOR", "1"))
    )
    cors_origins: list = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("NEXUS_CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ]
    )
    # ---- Production hardening (P1) ----
    api_keys: dict = field(default_factory=lambda: _parse_json_env("NEXUS_API_KEYS"))
    deploy_platform: str = field(default_factory=lambda: os.getenv("NEXUS_DEPLOY_PLATFORM", "local"))
    tenants: list = field(
        default_factory=lambda: [t.strip() for t in os.getenv("NEXUS_TENANTS", "").split(",") if t.strip()]
    )
    chat_rate_limit: int = field(default_factory=lambda: int(os.getenv("NEXUS_CHAT_RATE_LIMIT", "60")))
    tool_gen_rate_limit: int = field(
        default_factory=lambda: int(os.getenv("NEXUS_TOOL_GEN_RATE_LIMIT", "20"))
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("NEXUS_RATE_LIMIT_WINDOW_SECONDS", "60"))
    )
    json_logs: bool = field(default_factory=lambda: os.getenv("NEXUS_JSON_LOGS", "true").lower() == "true")
    # ---- Autonomous goals (P2) ----
    autonomy_hourly_budget: int = field(
        default_factory=lambda: int(os.getenv("NEXUS_AUTONOMY_HOURLY_BUDGET", "0"))
    )
    autonomy_default_budget: int = field(
        default_factory=lambda: int(os.getenv("NEXUS_AUTONOMY_DEFAULT_BUDGET", "20"))
    )
    autonomy_allowlist: list = field(
        default_factory=lambda: [
            a.strip() for a in os.getenv("NEXUS_AUTONOMY_ALLOWLIST", "tool_selfheal").split(",") if a.strip()
        ]
    )
    goals_max_active: int = field(default_factory=lambda: int(os.getenv("NEXUS_GOALS_MAX_ACTIVE", "10")))
    # ---- Multi-modal (P3) ----
    stt_model: str = field(default_factory=lambda: os.getenv("NEXUS_STT_MODEL", "whisper-1"))
    tts_model: str = field(default_factory=lambda: os.getenv("NEXUS_TTS_MODEL", "tts-1"))
    tts_voice: str = field(default_factory=lambda: os.getenv("NEXUS_TTS_VOICE", "alloy"))
    # ---- Swarm (P4) ----
    swarm_max_workers: int = field(default_factory=lambda: int(os.getenv("NEXUS_SWARM_MAX_WORKERS", "5")))
    # ---- Plugins ----
    plugins_dir: str = field(default_factory=lambda: os.getenv("NEXUS_PLUGINS_DIR", "plugins"))
    # ---- Sandbox (P1 security) ----
    sandbox_backend: str = field(default_factory=lambda: os.getenv("NEXUS_SANDBOX_BACKEND", "subprocess"))
    # ---- Observability (P2) ----
    otel_enabled: bool = field(
        default_factory=lambda: os.getenv("NEXUS_OTEL_ENABLED", "false").lower() == "true"
    )


class Container:
    """Composition root - wires all adapters into the use cases."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._started = False
        self._shutdown = False

        # ---- Security / observability (P1) ----
        self.secrets: SecretStore = self._build_secret_store()
        self._resolve_secrets_into_config()
        self.authenticator: Authenticator = self._build_authenticator()
        self.tracer: Tracer = self._build_tracer()
        self.metrics: Metrics = self._build_metrics()
        self.rate_limiter: RateLimiter = self._build_rate_limiter()

        # ---- Ports (concrete adapters chosen here) ----
        self.event_bus: EventBus = self._build_event_bus()
        self.embedder: EmbeddingProvider = self._build_embedder()
        self.llm: LLMProvider = self._build_llm()
        self.background_llm: LLMProvider = self._build_background_llm()
        self.speech_to_text: SpeechToText = self._build_speech_to_text()
        self.text_to_speech: TextToSpeech = self._build_text_to_speech()
        self.sandbox: Sandbox = self._build_sandbox()
        self.memory_repo: MemoryRepository = self._build_memory_repo()
        self.synapse: SynapseConfig = SynapseConfig()
        self.concept_repo: ConceptRepository = self._build_concept_repo()
        self.working_memory: ShortTermMemory = self._build_working_memory()
        self.tool_registry: ToolRegistry = self._build_tool_registry()
        self.deployer: DeploymentProvider | None = self._build_deployer()
        self.executor: ToolExecutor = self._build_executor()
        self.column_registry: CorticalColumnRegistry = self._build_column_registry()
        self.policy_store: ActionPolicyStore = self._build_policy_store()
        self.goal_repo: GoalRepository = self._build_goal_repo()
        self.autonomy_policy: AutonomyPolicy = self._build_autonomy_policy()
        self.agent_repo: AgentRepository = self._build_agent_repo()
        self.swarm_repo: SwarmRepository = self._build_swarm_repo()

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
            tracer=self.tracer,
            metrics=self.metrics,
        )
        # A second cortex instance bound to the background LLM, so autonomous
        # steps run on the cheap/local provider instead of the interactive one.
        self.background_process_message = ProcessMessageUseCase(
            llm=self.background_llm,
            memory_repo=self.memory_repo,
            concept_repo=self.concept_repo,
            working_memory=self.working_memory,
            tools=self.tool_registry,
            executor=self.executor,
            event_bus=self.event_bus,
            session_manager=self.session_manager,
            tracer=self.tracer,
            metrics=self.metrics,
        )
        # Subconscious + dreaming loops use the background (local/cheap) LLM.
        self.entity_synthesis = EntitySynthesisUseCase(
            self.background_llm, self.concept_repo, self.memory_repo, self.event_bus
        )
        self.pattern_detection = PatternDetectionUseCase(
            self.background_llm, self.memory_repo, self.event_bus
        )
        self.dream_session = DreamSessionUseCase(
            llm=self.background_llm,
            memory_repo=self.memory_repo,
            concept_repo=self.concept_repo,
            working_memory=self.working_memory,
            sandbox=self.sandbox,
            executor=self.executor,
            synapse=self.synapse,
            event_bus=self.event_bus,
            tracer=self.tracer,
            metrics=self.metrics,
        )
        self.tool_generator = GenerateToolUseCase(
            llm=self.llm,
            sandbox=self.sandbox,
            registry=self.tool_registry,
            executor=self.executor,
            deployer=self.deployer,
        )
        self.self_heal = SelfHealUseCase(
            self.tool_registry,
            self.tool_generator,
            policy=self.autonomy_policy,
            tenant_id="default",
        )

        # ---- Autonomous goals (P2) ----
        from nexus.infrastructure.adapters.autonomy.executor import CortexStepExecutor

        self.create_goal = CreateGoalUseCase(self.goal_repo)
        self.approve_goal = ApproveGoalUseCase(self.goal_repo)
        self.cancel_goal = CancelGoalUseCase(self.goal_repo)
        self.list_goals = ListGoalsUseCase(self.goal_repo)
        self.get_goal = GetGoalUseCase(self.goal_repo)
        self.autonomy_loop = AutonomyLoopUseCase(
            self.goal_repo,
            self.autonomy_policy,
            CortexStepExecutor(self.background_process_message),
        )

        # ---- Swarm (P4) ----
        from nexus.infrastructure.adapters.swarm.executor import SwarmAgentExecutor
        from nexus.application.swarm.swarm import (
            CreateSwarmUseCase,
            GetAgentUseCase,
            GetSwarmUseCase,
            ListAgentsUseCase,
            ListSwarmsUseCase,
            RegisterAgentUseCase,
            SwarmCoordinatorUseCase,
        )

        self.register_agent = RegisterAgentUseCase(self.agent_repo)
        self.list_agents = ListAgentsUseCase(self.agent_repo)
        self.get_agent = GetAgentUseCase(self.agent_repo)
        self.create_swarm = CreateSwarmUseCase(self.swarm_repo, self.agent_repo)
        self.list_swarms = ListSwarmsUseCase(self.swarm_repo)
        self.get_swarm = GetSwarmUseCase(self.swarm_repo)
        self.swarm_agent_executor = SwarmAgentExecutor(self.process_message, self.tool_registry)
        self.swarm_coordinator = SwarmCoordinatorUseCase(
            self.swarm_repo,
            self.agent_repo,
            self.swarm_agent_executor,
            max_workers=self.config.swarm_max_workers,
        )

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

    def _build_secret_store(self) -> SecretStore:
        from nexus.infrastructure.adapters.security.secrets import (
            ChainedSecretStore,
            EnvSecretStore,
            JsonFileSecretStore,
        )

        backend = os.getenv("NEXUS_SECRET_BACKEND", "env")
        if backend.startswith("json:"):
            path = backend.split(":", 1)[1].strip()
            return ChainedSecretStore([JsonFileSecretStore(path), EnvSecretStore()])
        return EnvSecretStore()

    def _resolve_secrets_into_config(self) -> None:
        for env_name, attr in (
            ("OPENAI_API_KEY", "openai_api_key"),
            ("NEO4J_PASSWORD", "neo4j_password"),
        ):
            value = self.secrets.get(env_name)
            if value:
                setattr(self.config, attr, value)
        raw_keys = self.secrets.get("NEXUS_API_KEYS")
        if raw_keys:
            try:
                self.config.api_keys = json.loads(raw_keys)
            except json.JSONDecodeError:
                self.config.api_keys = {}

    def _build_authenticator(self) -> Authenticator:
        from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator

        return ApiKeyAuthenticator(self.config.api_keys)

    def _build_tracer(self) -> Tracer:
        if self.config.otel_enabled:
            try:
                from nexus.infrastructure.adapters.observability.opentelemetry import OTELTracer

                return OTELTracer()
            except Exception:
                pass
        from nexus.infrastructure.adapters.observability.observability import LoggingTracer

        return LoggingTracer()

    def _build_metrics(self) -> Metrics:
        if self.config.otel_enabled:
            try:
                from nexus.infrastructure.adapters.observability.opentelemetry import OTELMetrics

                return OTELMetrics()
            except Exception:
                pass
        from nexus.infrastructure.adapters.observability.observability import InMemoryMetrics

        return InMemoryMetrics()

    def _build_rate_limiter(self) -> RateLimiter:
        from nexus.infrastructure.adapters.security.redis_rate_limiter import RedisRateLimiter

        redis_url = f"redis://{self.config.redis_host}:{self.config.redis_port}"
        return RedisRateLimiter(redis_url=redis_url)

    def _build_event_bus(self) -> EventBus:
        from nexus.infrastructure.adapters.eventbus.redis_event_bus import RedisEventBus

        return RedisEventBus(host=self.config.redis_host, port=self.config.redis_port)

    def _build_embedder(self) -> EmbeddingProvider:
        from nexus.infrastructure.adapters.embedding.openai_embedder import OpenAIEmbedder

        return OpenAIEmbedder(
            api_key=self.config.openai_api_key,
            model=self.config.embedding_model,
            dimension=self.config.embedding_dimension,
            base_url=self.config.embedding_base_url,
        )

    def _build_llm(self) -> LLMProvider:
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=self.config.openai_api_key,
            model=self.config.llm_model,
            base_url=self.config.llm_base_url,
            default_max_tokens=self.config.llm_max_tokens,
        )

    def _build_background_llm(self) -> LLMProvider:
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=self.config.background_llm_api_key or self.config.openai_api_key,
            model=self.config.background_llm_model,
            base_url=self.config.background_llm_base_url,
        )

    def _build_speech_to_text(self) -> SpeechToText:
        from nexus.infrastructure.adapters.speech.openai_speech import OpenAISpeechToText

        return OpenAISpeechToText(api_key=self.config.openai_api_key, model=self.config.stt_model)

    def _build_text_to_speech(self) -> TextToSpeech:
        from nexus.infrastructure.adapters.speech.openai_speech import OpenAITextToSpeech

        return OpenAITextToSpeech(
            api_key=self.config.openai_api_key,
            model=self.config.tts_model,
            default_voice=self.config.tts_voice,
        )

    def _build_sandbox(self) -> Sandbox:
        if self.config.sandbox_backend == "docker":
            from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox

            return DockerSandbox()
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
        from nexus.infrastructure.adapters.execution.builtin_tools import (
            BuiltinToolRegistry,
            default_builtin_tools,
        )

        return BuiltinToolRegistry(default_builtin_tools())

    def _build_deployer(self) -> DeploymentProvider | None:
        platform = self.config.deploy_platform
        if platform == "railway":
            from nexus.infrastructure.adapters.deployment.railway_deployer import RailwayDeployer

            token = self.secrets.get("RAILWAY_TOKEN")
            project = self.secrets.get("RAILWAY_PROJECT_ID")
            return RailwayDeployer(token=token or "", project_id=project or "")
        if platform == "vercel":
            from nexus.infrastructure.adapters.deployment.vercel_deployer import VercelDeployer

            token = self.secrets.get("VERCEL_TOKEN")
            team = self.secrets.get("VERCEL_TEAM_ID")
            return VercelDeployer(token=token or "", team_id=team)
        from nexus.infrastructure.adapters.deployment.local_deployer import LocalDeployer

        return LocalDeployer()

    def _build_executor(self) -> ToolExecutor:
        from nexus.infrastructure.adapters.execution.registry_tool_executor import RegistryBackedToolExecutor
        from nexus.infrastructure.adapters.execution.extended_tools import EXTENDED_HANDLERS
        from nexus.infrastructure.adapters.plugins.loader import PluginLoader

        # Start with extended builtin handlers
        all_handlers = dict(EXTENDED_HANDLERS)

        # Load plugins and merge their handlers
        self.plugin_loader = PluginLoader(self.config.plugins_dir, self.tool_registry)
        plugin_results = self.plugin_loader.load_all()
        for info in plugin_results:
            if not info.error:
                all_handlers.update(self.plugin_loader.handlers)
        self._plugin_infos = plugin_results

        return RegistryBackedToolExecutor(self.tool_registry, self.sandbox, all_handlers)

    def _build_column_registry(self) -> CorticalColumnRegistry:
        from nexus.infrastructure.adapters.cognition import InMemoryCorticalColumnRegistry

        return InMemoryCorticalColumnRegistry()

    def _build_policy_store(self) -> ActionPolicyStore:
        from nexus.infrastructure.adapters.cognition import InMemoryActionPolicyStore

        return InMemoryActionPolicyStore()

    def _build_goal_repo(self) -> GoalRepository:
        from nexus.infrastructure.adapters.autonomy.goal_repository import InMemoryGoalRepository

        return InMemoryGoalRepository()

    def _build_autonomy_policy(self) -> AutonomyPolicy:
        from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy

        return DefaultAutonomyPolicy(
            rate_limiter=self.rate_limiter,
            hourly_budget=self.config.autonomy_hourly_budget,
            allowlist=self.config.autonomy_allowlist,
        )

    def _build_agent_repo(self) -> AgentRepository:
        from nexus.infrastructure.adapters.swarm.repositories import InMemoryAgentRepository

        return InMemoryAgentRepository()

    def _build_swarm_repo(self) -> SwarmRepository:
        from nexus.infrastructure.adapters.swarm.repositories import InMemorySwarmRepository

        return InMemorySwarmRepository()

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self.event_bus.start()
        await self.memory_repo.ensure_collection()
        for tenant_id in self.config.tenants:
            await self.memory_repo.ensure_collection(tenant_id=tenant_id)

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
