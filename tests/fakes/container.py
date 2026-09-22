"""Fake Container - wires the real application use cases against fake adapters.

Mirrors the wiring in the production composition root (infrastructure/di/container.py)
but injects in-memory adapters, so API route tests can run with zero external infra.
"""

from __future__ import annotations

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.application.cortex.session_manager import SessionManager
from nexus.application.autonomy.goals import (
    ApproveGoalUseCase,
    AutonomyLoopUseCase,
    CancelGoalUseCase,
    CreateGoalUseCase,
    GetGoalUseCase,
    ListGoalsUseCase,
)
from nexus.application.swarm.swarm import (
    CreateSwarmUseCase,
    GetAgentUseCase,
    GetSwarmUseCase,
    ListAgentsUseCase,
    ListSwarmsUseCase,
    RegisterAgentUseCase,
    SwarmCoordinatorUseCase,
)
from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator
from nexus.application.subcortex.amygdala import AmygdalaUseCase
from nexus.application.subcortex.basal_ganglia import BasalGangliaUseCase
from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase
from nexus.application.subcortex.pattern_detection import PatternDetectionUseCase
from nexus.application.subcortex.spatial.fourier_router import FourierRouterUseCase
from nexus.application.subcortex.spatial.grid_cells import GridCellNavigationUseCase
from nexus.application.subcortex.spatial.hex_scaling import BoundlessScalingUseCase
from nexus.application.subcortex.synthesis import EntitySynthesisUseCase
from nexus.application.subcortex.thalamus import ThalamicGatingUseCase
from nexus.application.tools.generate_tool import GenerateToolUseCase
from nexus.application.tools.self_heal import SelfHealUseCase
from nexus.domain.ports.observability import NoopTracer
from nexus.domain.value_objects.synapse import SynapseConfig

from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator
from nexus.infrastructure.adapters.autonomy.executor import CortexStepExecutor
from nexus.infrastructure.adapters.autonomy.goal_repository import InMemoryGoalRepository
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.swarm.executor import SwarmAgentExecutor
from nexus.infrastructure.adapters.swarm.repositories import InMemoryAgentRepository, InMemorySwarmRepository
from nexus.infrastructure.adapters.observability.observability import InMemoryMetrics
from nexus.infrastructure.adapters.observability.activity_feed import InMemoryActivityFeed
from nexus.infrastructure.adapters.security.rate_limiter import SlidingWindowRateLimiter
from nexus.infrastructure.adapters.security.secrets import EnvSecretStore

from tests.fakes import (
    FakeActionPolicyStore,
    FakeConceptRepository,
    FakeCorticalColumnRegistry,
    FakeEmbedder,
    FakeEventBus,
    FakeExecutor,
    FakeLLM,
    FakeMemoryRepository,
    FakeSandbox,
    FakeShortTermMemory,
    FakeSpeechToText,
    FakeTextToSpeech,
    FakeToolRegistry,
)

# Well-known test credentials: sk-test-1 (tenant t1) and sk-test-2 (tenant t2).
TEST_API_KEY_1 = "sk-test-1"
TEST_API_KEY_2 = "sk-test-2"


class FakeContainer:
    """Composition root built from in-memory adapters, mirroring Container."""

    def __init__(self, llm_script: dict | None = None) -> None:
        self.config = None
        self.secrets = EnvSecretStore()
        self.authenticator = ApiKeyAuthenticator(
            {
                TEST_API_KEY_1: {"user_id": "u1", "tenant_id": "t1", "role": "admin"},
                TEST_API_KEY_2: {"user_id": "u2", "tenant_id": "t2", "role": "user"},
            }
        )
        self.tracer = NoopTracer()
        self.metrics = InMemoryMetrics()
        self.activity_feed = InMemoryActivityFeed()
        self.rate_limiter = SlidingWindowRateLimiter()
        self.event_bus = FakeEventBus()
        self.embedder = FakeEmbedder()
        self.llm = FakeLLM(script=llm_script)
        self.background_llm = FakeLLM(script=llm_script)
        self.speech_to_text = FakeSpeechToText()
        self.text_to_speech = FakeTextToSpeech()
        self.sandbox = FakeSandbox()
        self.memory_repo = FakeMemoryRepository()
        self.concept_repo = FakeConceptRepository()
        self.working_memory = FakeShortTermMemory()
        self.synapse = SynapseConfig()
        self.tool_registry = FakeToolRegistry()
        self.deployer = None
        self.executor = FakeExecutor()
        self.column_registry = FakeCorticalColumnRegistry()
        self.policy_store = FakeActionPolicyStore()
        self.goal_repo = InMemoryGoalRepository()
        self.autonomy_policy = DefaultAutonomyPolicy(
            rate_limiter=self.rate_limiter, hourly_budget=0, allowlist=["tool_selfheal"]
        )
        self.agent_repo = InMemoryAgentRepository()
        self.swarm_repo = InMemorySwarmRepository()

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
            deployer=None,
        )
        self.self_heal = SelfHealUseCase(
            self.tool_registry,
            self.tool_generator,
            policy=self.autonomy_policy,
            tenant_id="default",
        )
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
            max_workers=5,
        )
        self.thalamus = ThalamicGatingUseCase(self.column_registry, self.event_bus)
        self.basal_ganglia = BasalGangliaUseCase(self.column_registry, self.policy_store, self.event_bus)
        self.amygdala = AmygdalaUseCase(self.event_bus)
        self.grid_cells = GridCellNavigationUseCase()
        self.fourier_router = FourierRouterUseCase()
        self.hex_scaling = BoundlessScalingUseCase()

        self.subconscious = SubconsciousCoordinator(
            event_bus=self.event_bus,
            entity_synthesis=self.entity_synthesis,
            pattern_detection=self.pattern_detection,
            dream_session=self.dream_session,
            dream_hour=3,
            pattern_interval_seconds=1800,
            thalamus=self.thalamus,
            basal_ganglia=self.basal_ganglia,
            amygdala=self.amygdala,
        )

    async def start(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None
