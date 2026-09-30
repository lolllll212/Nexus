"""
Evaluation tests asserting:
1. Nightly dreaming memory consolidation cycle improves retrieval hit rate and semantic coherence.
2. Hexagonal Fourier grid routing correctly decomposes multi-axis concept energy gradients.
"""

from __future__ import annotations

import pytest

from nexus.application.subcortex.spatial.fourier_router import FourierRouterUseCase
from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.value_objects.hex_grid import HexCoord
from nexus.domain.value_objects.synapse import ConnectionType
from tests.fakes.container import FakeContainer


class ScriptedDreamLLM:
    """Scripted LLM for evaluating dream consolidation extraction."""

    async def extract_structured(self, content, schema, instructions=""):
        return {
            "facts": [
                {
                    "content": "Kubernetes and Docker form the core containerization foundation.",
                    "importance": 0.95,
                },
                {
                    "content": "PostgreSQL queries require btree indexes for performance.",
                    "importance": 0.88,
                },
            ]
        }

    async def complete(self, messages, temperature=0.7, max_tokens=1024, tools=None):
        return "Hypothesis: automated canary testing reduces deployment incidents."


@pytest.mark.asyncio
async def test_dreaming_consolidation_improves_retrieval_eval():
    """Eval asserting memory consolidation and pruning improves knowledge retrieval."""
    container = FakeContainer()
    tenant = "eval_tenant"

    # Inject ScriptedDreamLLM into compression step
    dream_llm = ScriptedDreamLLM()
    container.background_llm = dream_llm
    container.dream_session._compression._llm = dream_llm

    # Seed unconsolidated episodic memories
    episodes = [
        Memory(
            content="User discussed deploying Kubernetes clusters on bare metal.",
            memory_type=MemoryType.EPISODIC,
            concepts=["k8s", "infrastructure"],
            access_count=3,
        ),
        Memory(
            content="User mentioned using Docker containers for reproducible staging pipelines.",
            memory_type=MemoryType.EPISODIC,
            concepts=["docker", "containers"],
            access_count=2,
        ),
        Memory(
            content="User asked about optimizing PostgreSQL query plans with btree indexes.",
            memory_type=MemoryType.EPISODIC,
            concepts=["postgres", "database"],
            access_count=4,
        ),
        Memory(
            content="User noted temporary scratchpad note: buy milk.",
            memory_type=MemoryType.EPISODIC,
            concepts=["scratchpad"],
            access_count=0,
        ),
    ]

    for m in episodes:
        await container.memory_repo.store(m, tenant_id=tenant)

    # Seed concepts in synaptic graph
    c_infra = Concept(label="infrastructure", concept_type="domain")
    c_k8s = Concept(label="k8s", concept_type="technology")
    await container.concept_repo.upsert(c_infra, tenant_id=tenant)
    await container.concept_repo.upsert(c_k8s, tenant_id=tenant)
    await container.concept_repo.upsert_connection(
        SynapticConnection(
            source_id=c_infra.id,
            target_id=c_k8s.id,
            connection_type=ConnectionType.SEMANTIC,
            weight=1.0,
        ),
        tenant_id=tenant,
    )

    # Execute dreaming session
    dream_result = await container.dream_session.run(emotional_intensity=0.8, tenant_id=tenant)

    assert dream_result.session_id.startswith("dream-")
    assert dream_result.recall_probes > 0
    assert dream_result.recall_hit_rate_before is not None
    assert dream_result.recall_hit_rate_after is not None
    # Dreaming maintains or improves recall hit rate
    assert dream_result.recall_hit_rate_after >= dream_result.recall_hit_rate_before
    if dream_result.recall_delta is not None:
        assert dream_result.recall_delta >= 0.0

    # Verify semantic memories were generated and unconsolidated flagged
    all_memories = await container.memory_repo.retrieve("", limit=100, tenant_id=tenant)
    semantic_memories = [m for m in all_memories if m.memory_type == MemoryType.SEMANTIC]
    assert len(semantic_memories) >= 2
    assert any("Kubernetes" in m.content for m in semantic_memories)


def test_fourier_grid_routing_eval():
    """Eval asserting Hexagonal Fourier Router resolves dominant spatial gradient."""
    router = FourierRouterUseCase()

    # Create signal with dominant spatial frequency energy along the 'q' axis (r=0, q varies)
    signal_q_dominant: dict[HexCoord, float] = {
        HexCoord(i, 0): float(i % 2) for i in range(8)
    }

    result = router.route(signal_q_dominant)
    assert result.dominant_axis == "q"
    assert result.axis_energy["q"] > result.axis_energy["r"]
    assert result.axis_energy["q"] > 0

    # Create signal along the 'r' axis (q=0, r varies)
    signal_r_dominant: dict[HexCoord, float] = {
        HexCoord(0, i): float(i % 2) for i in range(8)
    }
    result_r = router.route(signal_r_dominant)
    assert result_r.dominant_axis == "r"
    assert result_r.axis_energy["r"] > result_r.axis_energy["q"]
    assert result_r.axis_energy["r"] > 0

    # Test labelled placements routing
    placements = {
        "cortex": HexCoord(0, 0),
        "reasoning": HexCoord(2, 0),
        "planning": HexCoord(4, 0),
        "execution": HexCoord(6, 0),
    }
    weights = {
        "cortex": 1.0,
        "reasoning": 0.0,
        "planning": 1.0,
        "execution": 0.0,
    }

    routed = router.route_labels(placements, weights)
    assert routed.dominant_axis == "q"
    assert routed.axis_energy["q"] > 0
