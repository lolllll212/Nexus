"""
DreamPhase 4: Consolidation - strengthening core synaptic pathways.

Identifies frequently-used concept clusters (the brain's "core knowledge")
and reinforces connections within them so retrieval becomes faster and
more reliable. The day's decay is reversed for what actually matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository
from nexus.domain.value_objects.synapse import SynapseConfig


@dataclass
class CoreCluster:
    concept_ids: List[str]
    labels: List[str]


@dataclass
class ConsolidationResult:
    clusters_identified: List[CoreCluster] = field(default_factory=list)
    connections_strengthened: int = 0
    emotionally_charged: int = 0  # connections reinforced with emotional priority


class ConsolidationUseCase:
    """Reinforce what the brain actually uses - prioritizing what it felt."""

    def __init__(
        self,
        concept_repo: ConceptRepository,
        synapse: SynapseConfig,
        memory_repo: MemoryRepository | None = None,
    ) -> None:
        self._concept_repo = concept_repo
        self._synapse = synapse
        self._memory_repo = memory_repo

    async def run(
        self,
        max_clusters: int = 5,
        min_cluster_size: int = 3,
        emotional_intensity: float = 0.0,
        tenant_id: str = "default",
    ) -> ConsolidationResult:
        result = ConsolidationResult()

        # High-arousal memory clusters re-consolidate first (the brain
        # strengthens what it felt most strongly about).
        charged: Dict[str, float] = {}
        if self._memory_repo and emotional_intensity > 0.0:
            charged_memories = await self._memory_repo.find_by_emotional_weight(
                emotional_intensity, limit=200, tenant_id=tenant_id
            )
            for m in charged_memories:
                intensity = m.emotional_weight.intensity if m.emotional_weight else 0.0
                for cid in m.concepts:
                    charged[cid] = max(charged.get(cid, 0.0), intensity)

        # Find the strongest concepts - they anchor the core knowledge graph
        # (an adapter could implement a proper community-detection query)
        strong_concepts = await self._concept_repo.find_by_label("", limit=200, tenant_id=tenant_id)
        strong_concepts.sort(key=lambda c: c.strength, reverse=True)

        # Build simple clusters around each strong anchor
        for anchor in strong_concepts[:max_clusters]:
            neighbors = await self._concept_repo.get_connections(
                anchor.id, min_weight=0.5, tenant_id=tenant_id
            )
            if len(neighbors) < min_cluster_size:
                continue
            cluster = CoreCluster(
                concept_ids=[anchor.id, *[n.target_id for n in neighbors[:min_cluster_size]]],
                labels=[anchor.label],
            )
            result.clusters_identified.append(cluster)

            anchor_charge = charged.get(anchor.id, 0.0)

            # Reinforce intra-cluster connections
            for n in neighbors[:min_cluster_size]:
                conn = next((c for c in neighbors if c.target_id == n.target_id), None)
                if conn:
                    boost = max(anchor_charge, charged.get(n.target_id, 0.0))
                    rate = self._synapse.hebbian_learning_rate
                    if boost:
                        rate *= 1.0 + boost
                        result.emotionally_charged += 1
                    conn.reinforce(rate)
                    await self._concept_repo.upsert_connection(conn, tenant_id=tenant_id)
                    result.connections_strengthened += 1

        return result
