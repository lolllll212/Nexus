"""
DreamPhase 4: Consolidation - strengthening core synaptic pathways.

Identifies frequently-used concept clusters (the brain's "core knowledge")
and reinforces connections within them so retrieval becomes faster and
more reliable. The day's decay is reversed for what actually matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from nexus.domain.ports.memory_repository import ConceptRepository
from nexus.domain.value_objects.synapse import SynapseConfig


@dataclass
class CoreCluster:
    concept_ids: List[str]
    labels: List[str]


@dataclass
class ConsolidationResult:
    clusters_identified: List[CoreCluster] = field(default_factory=list)
    connections_strengthened: int = 0


class ConsolidationUseCase:
    """Reinforce what the brain actually uses."""

    def __init__(self, concept_repo: ConceptRepository, synapse: SynapseConfig) -> None:
        self._concept_repo = concept_repo
        self._synapse = synapse

    async def run(self, max_clusters: int = 5, min_cluster_size: int = 3) -> ConsolidationResult:
        result = ConsolidationResult()

        # Find the strongest concepts - they anchor the core knowledge graph
        # (an adapter could implement a proper community-detection query)
        strong_concepts = await self._concept_repo.find_by_label("", limit=200)
        strong_concepts.sort(key=lambda c: c.strength, reverse=True)

        # Build simple clusters around each strong anchor
        for anchor in strong_concepts[:max_clusters]:
            neighbors = await self._concept_repo.get_connections(anchor.id, min_weight=0.5)
            if len(neighbors) < min_cluster_size:
                continue
            cluster = CoreCluster(
                concept_ids=[anchor.id, *[n.target_id for n in neighbors[:min_cluster_size]]],
                labels=[anchor.label],
            )
            result.clusters_identified.append(cluster)

            # Reinforce intra-cluster connections
            for n in neighbors[:min_cluster_size]:
                conn = next((c for c in neighbors if c.target_id == n.target_id), None)
                if conn:
                    conn.reinforce(self._synapse.hebbian_learning_rate)
                    await self._concept_repo.upsert_connection(conn)
                    result.connections_strengthened += 1

        return result
