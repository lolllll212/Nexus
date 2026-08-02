"""
End-to-end tests of the application layer against FAKE adapters.

This is the proof of the architecture: the entire conscious + subconscious
brain runs against in-memory fakes. No Redis, no Neo4j, no OpenAI required.
"""

import sys
import asyncio
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.application.cortex.process_message import ProcessMessageUseCase
from nexus.application.cortex.session_manager import SessionManager
from nexus.application.subcortex.synthesis import EntitySynthesisUseCase
from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase
from nexus.application.subcortex.dreaming.prune import PruningUseCase
from nexus.application.subcortex.dreaming.simulate import SimulationUseCase
from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator

from tests.fakes import (
    FakeEventBus, FakeMemoryRepository, FakeConceptRepository, FakeShortTermMemory,
    FakeLLM, FakeSandbox, FakeToolRegistry, FakeExecutor,
)

from nexus.domain.entities.memory import Memory, MemoryType, EmotionalWeight
from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.tool import ToolStatus
from nexus.domain.entities.conversation import MessageRole
from nexus.domain.value_objects.synapse import ConnectionType, SynapseConfig
from nexus.domain.ports.event_bus import EventTopic
from nexus.domain.value_objects.emotion import infer_emotional_state


@pytest.mark.asyncio
async def test_pruning_persists_surviving_decayed_synapses():
    """Regression: decay used to mutate weights in memory only; surviving
    connections were never upserted, so decay never accumulated in storage."""
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    conn = SynapticConnection(
        source_id="a", target_id="b", connection_type=ConnectionType.SEMANTIC, weight=5.0
    )
    await concept_repo.upsert_connection(conn)

    pruning = PruningUseCase(memory_repo, concept_repo, SynapseConfig(decay_rate=0.1, min_weight=0.01))
    result = await pruning.run()

    assert result.synapses_pruned == 0
    persisted = await concept_repo.get_connections("a")
    assert persisted[0].weight < 5.0  # decayed weight was written back


@pytest.mark.asyncio
async def test_pruning_deletes_connections_below_floor():
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    conn = SynapticConnection(
        source_id="a", target_id="b", connection_type=ConnectionType.SEMANTIC, weight=0.02
    )
    await concept_repo.upsert_connection(conn)

    pruning = PruningUseCase(memory_repo, concept_repo, SynapseConfig(decay_rate=0.9, min_weight=0.1))
    result = await pruning.run()

    assert result.synapses_pruned == 1
    assert await concept_repo.get_connections("a") == []


@pytest.mark.asyncio
async def test_pruning_batch_deletes_stale_unaccessed_memories():
    """Vector pruning deletes stale memories in one batch (not per-memory)."""
    import datetime

    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()

    stale = Memory(content="old forgotten fact", memory_type=MemoryType.SEMANTIC)
    stale.last_accessed_at = datetime.datetime.utcnow() - datetime.timedelta(days=120)
    fresh = Memory(content="recently used fact", memory_type=MemoryType.SEMANTIC)
    fresh.last_accessed_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)

    await memory_repo.store(stale)
    await memory_repo.store(fresh)

    pruning = PruningUseCase(memory_repo, concept_repo, SynapseConfig())
    result = await pruning.run(access_threshold_days=90)

    assert result.vectors_pruned == 1
    assert stale.id not in memory_repo.memories
    assert fresh.id in memory_repo.memories


@pytest.mark.asyncio
async def test_pruning_spares_stale_but_frequently_accessed_memories():
    """Payload-based stale filter: access_count protects against pruning."""
    import datetime

    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()

    well_used = Memory(content="old but beloved", memory_type=MemoryType.SEMANTIC, access_count=5)
    well_used.last_accessed_at = datetime.datetime.utcnow() - datetime.timedelta(days=120)

    await memory_repo.store(well_used)

    pruning = PruningUseCase(memory_repo, concept_repo, SynapseConfig())
    result = await pruning.run(access_threshold_days=90, min_accesses=2)

    assert result.vectors_pruned == 0
    assert well_used.id in memory_repo.memories


@pytest.mark.asyncio
async def test_consolidation_prioritizes_high_arousal_clusters():
    """Emotional weighting: high-intensity memory clusters reinforce harder."""
    from nexus.application.subcortex.dreaming.consolidate import ConsolidationUseCase

    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()

    anchor = Concept(label="crisis", concept_type="topic")
    await concept_repo.upsert(anchor)
    neighbor = Concept(label="deploy", concept_type="topic")
    await concept_repo.upsert(neighbor)
    conn = await concept_repo.connect(anchor.id, neighbor.id, ConnectionType.EMOTIONAL)
    conn.weight = 1.0
    await concept_repo.upsert_connection(conn)
    await concept_repo.connect(anchor.id, "n2", ConnectionType.EMOTIONAL)
    await concept_repo.connect(anchor.id, "n3", ConnectionType.EMOTIONAL)

    charged = Memory(
        content="the outage was terrifying",
        memory_type=MemoryType.EMOTIONAL,
        concepts=[anchor.id],
        emotional_weight=EmotionalWeight(valence=-0.8, arousal=0.9),
    )
    await memory_repo.store(charged)

    base_rate = SynapseConfig().hebbian_learning_rate
    consolidation = ConsolidationUseCase(concept_repo, SynapseConfig(), memory_repo=memory_repo)
    result = await consolidation.run(emotional_intensity=0.5)

    assert result.emotionally_charged >= 1
    persisted = await concept_repo.get_connections(anchor.id)
    assert persisted[0].weight > 1.0 + base_rate  # boosted beyond flat hebbian rate


@pytest.mark.asyncio
async def test_consolidation_without_emotional_threshold_is_unchanged():
    """When no emotional intensity is requested, no charged reinforcement happens."""
    from nexus.application.subcortex.dreaming.consolidate import ConsolidationUseCase

    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()

    anchor = Concept(label="normal", concept_type="topic")
    await concept_repo.upsert(anchor)
    await concept_repo.connect(anchor.id, "n1", ConnectionType.SEMANTIC)
    await concept_repo.connect(anchor.id, "n2", ConnectionType.SEMANTIC)
    await concept_repo.connect(anchor.id, "n3", ConnectionType.SEMANTIC)

    charged = Memory(
        content="dramatic memory",
        memory_type=MemoryType.EMOTIONAL,
        concepts=[anchor.id],
        emotional_weight=EmotionalWeight(valence=1.0, arousal=1.0),
    )
    await memory_repo.store(charged)

    consolidation = ConsolidationUseCase(concept_repo, SynapseConfig(), memory_repo=memory_repo)
    result = await consolidation.run(emotional_intensity=0.0)

    assert result.emotionally_charged == 0
    assert result.connections_strengthened >= 1
    """Regression: recall used to mutate m.accessed() in memory only, so stale
    memories would never refresh last_accessed_at and got pruned incorrectly."""
    event_bus = FakeEventBus()
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(script={"complete": "FINAL ANSWER: I used your memory."})
    tools = FakeToolRegistry()
    executor = FakeExecutor()

    stored = Memory(content="important project fact", memory_type=MemoryType.SEMANTIC)
    await memory_repo.store(stored)
    assert stored.access_count == 0

    sessions = SessionManager(working)
    use_case = ProcessMessageUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, tools=tools, executor=executor,
        event_bus=event_bus, session_manager=sessions,
    )
    await use_case.execute(user_id="u1", message="tell me about the project", session_id="s1")

    assert stored.access_count >= 1
    assert stored.last_accessed_at is not None


@pytest.mark.asyncio
async def test_conscious_loop_responds_and_dispatchs_event():
    """The cortex answers AND publishes to the subconscious without blocking."""
    event_bus = FakeEventBus()
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(script={"complete": "FINAL ANSWER: Hello from the fake brain."})
    tools = FakeToolRegistry()
    executor = FakeExecutor()

    sessions = SessionManager(working)
    use_case = ProcessMessageUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, tools=tools, executor=executor,
        event_bus=event_bus, session_manager=sessions,
    )

    result = await use_case.execute(user_id="u1", message="hello", session_id="s1")

    assert "Hello from the fake brain" in result.response
    assert result.session_id == "s1"
    assert len(result.thoughts) >= 1

    # The nervous system must have received the user message
    topics = [e.topic for e in event_bus.published]
    assert EventTopic.USER_MESSAGE in topics
    # And the exchange was stored as episodic memory for tonight's dreaming
    assert EventTopic.MEMORY_STORED in topics
    assert len(memory_repo.memories) == 1
    stored = list(memory_repo.memories.values())[0]
    assert stored.memory_type == MemoryType.EPISODIC


@pytest.mark.asyncio
async def test_subconscious_synthesis_extracts_and_connects_concepts():
    """Subconscious pulls entities and wires synaptic connections."""
    event_bus = FakeEventBus()
    concept_repo = FakeConceptRepository()
    memory_repo = FakeMemoryRepository()
    llm = FakeLLM(
        script={
            "extract": {
                "entities": [
                    {"label": "Next.js", "type": "technology"},
                    {"label": "deployment", "type": "topic"},
                ]
            }
        }
    )

    use_case = EntitySynthesisUseCase(llm, concept_repo, memory_repo, event_bus)
    concepts = await use_case.synthesize(
        {"message": "I'm struggling with a Next.js deployment bug", "session_id": "s1"}
    )

    assert len(concepts) == 2
    # Concepts persisted to the graph
    assert len(concept_repo.concepts) == 2
    # Semantic memory stored
    assert len(memory_repo.memories) == 2


@pytest.mark.asyncio
async def test_dreaming_full_cycle_runs():
    """The complete 4-phase dream session executes against fakes."""
    # Seed some episodic memories from "today"
    memory_repo = FakeMemoryRepository()
    for i in range(3):
        await memory_repo.store(
            Memory(content=f"episode {i}: user hit a bug", memory_type=MemoryType.EPISODIC)
        )

    event_bus = FakeEventBus()
    concept_repo = FakeConceptRepository()
    await concept_repo.upsert(Concept(label="nextjs", concept_type="tech"))
    await concept_repo.upsert(Concept(label="deploy", concept_type="topic"))
    await concept_repo.connect("nextjs", "deploy")

    working = FakeShortTermMemory()
    llm = FakeLLM(script={"extract": {"facts": [{"content": "User prefers Vercel"}]}})
    sandbox = FakeSandbox()
    executor = FakeExecutor()

    dream = DreamSessionUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, sandbox=sandbox, executor=executor,
        synapse=SynapseConfig(), event_bus=event_bus,
    )

    result = await dream.run()

    assert result.completed_at is not None
    assert result.compression.semantic_fragments_created == 1
    # Semantic fact stored
    assert any(m.memory_type == MemoryType.SEMANTIC for m in memory_repo.memories.values())
    # Dream completed event published
    assert EventTopic.DREAM_COMPLETED in [e.topic for e in event_bus.published]


@pytest.mark.asyncio
async def test_coordinator_wires_loops_together():
    """The subconscious coordinator reacts to cortex events via the bus."""
    event_bus = FakeEventBus()
    llm = FakeLLM(script={"extract": {"entities": [{"label": "bug", "type": "topic"}]}})
    concept_repo = FakeConceptRepository()
    memory_repo = FakeMemoryRepository()
    working = FakeShortTermMemory()
    sandbox = FakeSandbox()
    executor = FakeExecutor()

    synthesis = EntitySynthesisUseCase(llm, concept_repo, memory_repo, event_bus)
    from nexus.application.subcortex.pattern_detection import PatternDetectionUseCase

    pattern = PatternDetectionUseCase(llm, memory_repo, event_bus)
    dream = DreamSessionUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, sandbox=sandbox, executor=executor,
        synapse=SynapseConfig(), event_bus=event_bus,
    )
    coordinator = SubconsciousCoordinator(event_bus, synthesis, pattern, dream)

    await coordinator.start()

    # Cortex publishes a message -> coordinator's handler synthesizes it
    await event_bus.publish(
        __import__("nexus.domain.ports.event_bus", fromlist=["Event"]).Event(
            topic=EventTopic.USER_MESSAGE,
            payload={"message": "nextjs is slow", "session_id": "s9", "active_concepts": []},
        )
    )
    await asyncio.sleep(0.1)  # allow the async handler to run

    assert len(concept_repo.concepts) >= 1

    await coordinator.stop()


@pytest.mark.asyncio
async def test_generate_tool_self_evolution():
    """The brain generates, tests, and registers its own tool."""
    llm = FakeLLM(script={"complete": "def solve(input_data):\n    return {'answer': 42}"})
    sandbox = FakeSandbox()
    registry = FakeToolRegistry()
    executor = FakeExecutor()

    from nexus.application.tools.generate_tool import GenerateToolUseCase, ToolSpecRequest

    gen = GenerateToolUseCase(llm=llm, sandbox=sandbox, registry=registry, executor=executor, deployer=None)
    result = await gen.execute(
        ToolSpecRequest(
            name="answer_tool",
            description="computes the answer",
            problem_statement="write a function that returns 42",
            input_examples=[{"q": "?"}],
            expected_outputs=[{"answer": 42}],
        ),
        deploy=False,
    )

    assert result.tool.is_self_generated
    assert result.tool.status == ToolStatus.READY
    assert len(registry.tools) == 1


@pytest.mark.asyncio
async def test_simulation_builds_and_verifies_deployable_microservice_scaffold():
    """P3: dreaming spins up a full microservice scaffold, not a stub function."""
    memory_repo = FakeMemoryRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(
        script={
            "extract": {"problems": [{"problem": "build a rate limiter", "context": "api"}]},
            "complete": "def solve(input_data):\n    return {'limited': True}",
        }
    )
    sandbox = FakeSandbox()

    simulation = SimulationUseCase(llm=llm, sandbox=sandbox, executor=FakeExecutor(), memory_repo=memory_repo, working_memory=working)
    result = await simulation.run(
        [Memory(content="user needs a rate limiter for the API", memory_type=MemoryType.EPISODIC)]
    )

    assert result.solutions_tested == 1
    assert result.deployments_ready == 1
    assert len(result.solutions_verified) == 1
    solution = result.solutions_verified[0]
    assert solution.verified is True
    # Full scaffold present and handed to the sandbox as a project
    assert "main.py" in solution.scaffold
    assert "tests/test_main.py" in solution.scaffold
    assert "logic.py" in solution.scaffold
    assert sandbox.project_runs and "main.py" in sandbox.project_runs[0]["files"]
    # Findings delivered to working memory for dawn
    stored = await working.get("dream:findings")
    assert stored is not None and "deployables" in stored


@pytest.mark.asyncio
async def test_simulation_marks_solution_failed_when_scaffold_tests_fail():
    """P3: a scaffold whose tests fail is not reported as deployable."""
    memory_repo = FakeMemoryRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(
        script={
            "extract": {"problems": [{"problem": "flaky problem", "context": "x"}]},
            "complete": "def solve(input_data):\n    return {'bad': True}",
        }
    )
    sandbox = FakeSandbox()
    sandbox.fail_project = True

    simulation = SimulationUseCase(llm=llm, sandbox=sandbox, executor=FakeExecutor(), memory_repo=memory_repo, working_memory=working)
    result = await simulation.run(
        [Memory(content="some unresolved memory", memory_type=MemoryType.EPISODIC)]
    )

    assert result.solutions_tested == 1
    assert result.deployments_ready == 0
    assert result.solutions_verified == []


@pytest.mark.asyncio
async def test_cortex_modulates_tone_from_room_emotional_weight():
    """P4: the cortex seeds tone from the room's emotional state."""
    event_bus = FakeEventBus()
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(script={"complete": "FINAL ANSWER: Take it easy, we will fix it."})
    sessions = SessionManager(working)
    use_case = ProcessMessageUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, tools=FakeToolRegistry(), executor=FakeExecutor(),
        event_bus=event_bus, session_manager=sessions,
    )

    result = await use_case.execute(
        user_id="u1", message="I am really frustrated and this is terrible", session_id="s1"
    )

    assert "Take it easy" in result.response
    conv = sessions._cache["s1"]
    assert conv.emotional_state.valence < 0
    # The negative sentiment also reached the subconscious event
    dispatched = [e for e in event_bus.published if e.topic == EventTopic.USER_MESSAGE][0]
    assert dispatched.payload["emotional_state"]["dominant_emotion"] == "negative"


@pytest.mark.asyncio
async def test_cortex_encodes_emotional_weight_into_episodic_memory():
    """P4-P2 link: the episodic memory carries EmotionalWeight for dreaming."""
    event_bus = FakeEventBus()
    memory_repo = FakeMemoryRepository()
    concept_repo = FakeConceptRepository()
    working = FakeShortTermMemory()
    llm = FakeLLM(script={"complete": "FINAL ANSWER: okay"})
    sessions = SessionManager(working)
    use_case = ProcessMessageUseCase(
        llm=llm, memory_repo=memory_repo, concept_repo=concept_repo,
        working_memory=working, tools=FakeToolRegistry(), executor=FakeExecutor(),
        event_bus=event_bus, session_manager=sessions,
    )

    await use_case.execute(user_id="u1", message="I am panicking, urgent help now", session_id="s1")

    stored = list(memory_repo.memories.values())[0]
    assert stored.emotional_weight is not None
    assert stored.emotional_weight.arousal > 0.2  # blended from the message's inferred arousal


def test_session_restore_preserves_emotional_state():
    """P4: a restored session keeps the room's emotional weight (cross-session fluidity)."""
    import asyncio

    working = FakeShortTermMemory()

    async def scenario():
        sessions = SessionManager(working)
        conv = await sessions.get_or_create("room-1", "u1")
        conv.observe_message(MessageRole.USER, "I am really angry and frustrated about this")
        await working.set("session:room-1", {"recent": [], "emotional_state": conv.emotional_state.__dict__}, 3600)

        fresh = SessionManager(working)  # new session manager, same store
        restored = await fresh.get_or_create("room-1", "u1")
        return restored.emotional_state

    state = asyncio.run(scenario())
    assert state.dominant_emotion == "negative"
    assert state.valence < 0


def test_infer_emotional_state_and_tone_directive():
    """P4: lexicon inference + tone directive are pure and deterministic."""
    state = infer_emotional_state("I love this, it is amazing and great")
    assert state.valence > 0
    assert "match their energy" in state.tone_directive()

    tense = infer_emotional_state("urgent crash, I am panicking")
    assert tense.arousal > 0.5
    assert "agitated" in tense.tone_directive()

    neutral = infer_emotional_state("please pass the salt")
    assert neutral.tone_directive() == ""
