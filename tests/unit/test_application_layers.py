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
from nexus.application.subcortex.dreaming.compress import CompressionUseCase
from nexus.application.subcortex.dreaming.prune import PruningUseCase
from nexus.application.subcortex.dreaming.simulate import SimulationUseCase
from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator

from tests.fakes import (
    FakeEventBus, FakeMemoryRepository, FakeConceptRepository, FakeShortTermMemory,
    FakeLLM, FakeEmbedder, FakeSandbox, FakeToolRegistry, FakeExecutor,
)

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.entities.concept import Concept
from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema
from nexus.domain.value_objects.synapse import SynapseConfig
from nexus.domain.ports.event_bus import EventTopic


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
