"""Fake Container - wires the real application use cases against fake adapters.

Mirrors the wiring in the production composition root (infrastructure/di/container.py)
but injects in-memory adapters, so API route tests can run with zero external infra.
"""

from __future__ import annotations

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.application.cortex.session_manager import SessionManager
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
from nexus.domain.value_objects.synapse import SynapseConfig

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
    FakeToolRegistry,
)


class FakeContainer:
    """Composition root built from in-memory adapters, mirroring Container."""

    def __init__(self, llm_script: dict | None = None) -> None:
        self.config = None
        self.event_bus = FakeEventBus()
        self.embedder = FakeEmbedder()
        self.llm = FakeLLM(script=llm_script)
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
            llm=self.llm, sandbox=self.sandbox, registry=self.tool_registry, executor=self.executor, deployer=None
        )
        self.self_heal = SelfHealUseCase(self.tool_registry, self.tool_generator)
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
