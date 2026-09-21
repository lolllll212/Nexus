"""
DreamSessionUseCase - the nightly dreaming orchestrator.

Sequences the four phases in order:
    Phase 1  Compression    (episodic -> semantic)
    Phase 2  Pruning        (vector decay + synaptic pruning)
    Phase 3  Simulation     (sandboxed future problem solving)
    Phase 4  Consolidation  (reinforce core clusters)

Emits events so the cortex can be notified of new knowledge at dawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from nexus.domain.ports.event_bus import Event, EventBus, EventTopic
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.observability import Metrics, NoopMetrics, NoopTracer, Tracer
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.value_objects.synapse import SynapseConfig

from nexus.application.subcortex.dreaming.compress import CompressionUseCase, CompressionResult
from nexus.application.subcortex.dreaming.prune import PruningUseCase, PruningResult
from nexus.application.subcortex.dreaming.simulate import SimulationUseCase, SimulationResult
from nexus.application.subcortex.dreaming.consolidate import ConsolidationUseCase, ConsolidationResult


@dataclass
class DreamSessionResult:
    session_id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    compression: CompressionResult | None = None
    pruning: PruningResult | None = None
    simulation: SimulationResult | None = None
    consolidation: ConsolidationResult | None = None

    @property
    def duration_seconds(self) -> float:
        if not self.completed_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()


class DreamSessionUseCase:
    """The full dreaming cycle, run nightly at 3 AM."""

    def __init__(
        self,
        llm: LLMProvider,
        memory_repo: MemoryRepository,
        concept_repo: ConceptRepository,
        working_memory: ShortTermMemory,
        sandbox: Sandbox,
        executor: ToolExecutor,
        synapse: SynapseConfig,
        event_bus: EventBus,
        tracer: Tracer | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self._compression = CompressionUseCase(llm, memory_repo)
        self._pruning = PruningUseCase(memory_repo, concept_repo, synapse)
        self._simulation = SimulationUseCase(llm, sandbox, executor, memory_repo, working_memory)
        self._consolidation = ConsolidationUseCase(concept_repo, synapse, memory_repo)
        self._event_bus = event_bus
        self._memory_repo = memory_repo
        self._tracer = tracer or NoopTracer()
        self._metrics = metrics or NoopMetrics()

    async def run(self, emotional_intensity: float = 0.0, tenant_id: str = "default") -> DreamSessionResult:
        async with self._tracer.span("dream_session", {"tenant_id": tenant_id}):
            result = DreamSessionResult(session_id=f"dream-{int(datetime.utcnow().timestamp())}")

            await self._event_bus.publish(
                Event(topic=EventTopic.DREAM_TRIGGERED, payload={"session_id": result.session_id})
            )

            # --- Phase 1: Episodic -> Semantic ---
            episodes = await self._memory_repo.retrieve("", limit=1000, tenant_id=tenant_id)
            episodes = [e for e in episodes if not e.consolidated]
            result.compression = await self._compression.run(episodes, tenant_id=tenant_id)

            # --- Phase 2: Pruning ---
            result.pruning = await self._pruning.run(access_threshold_days=90, tenant_id=tenant_id)

            # --- Phase 3: Simulation ---
            unresolved = await self._memory_repo.find_stale(
                1, limit=20, tenant_id=tenant_id
            )  # yesterday's active problems
            result.simulation = await self._simulation.run(unresolved, tenant_id=tenant_id)

            # --- Phase 4: Consolidation ---
            result.consolidation = await self._consolidation.run(
                emotional_intensity=emotional_intensity, tenant_id=tenant_id
            )

            result.completed_at = datetime.utcnow()

            self._metrics.counter("dream_sessions_total", labels={"tenant_id": tenant_id})

            await self._event_bus.publish(
                Event(
                    topic=EventTopic.DREAM_COMPLETED,
                    payload={
                        "session_id": result.session_id,
                        "tenant_id": tenant_id,
                        "duration_seconds": result.duration_seconds,
                        "compression": result.compression.__dict__,
                        "pruning": result.pruning.__dict__,
                        "simulation": {
                            "problems": result.simulation.problems_identified,
                            "verified_solutions": len(result.simulation.solutions_verified),
                        },
                        "consolidation": result.consolidation.__dict__,
                    },
                )
            )
            return result

    @staticmethod
    def next_dream_time(now: datetime | None = None) -> datetime:
        """Next 3 AM UTC boundary - drives the cron scheduling."""
        now = now or datetime.utcnow()
        nxt = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt
