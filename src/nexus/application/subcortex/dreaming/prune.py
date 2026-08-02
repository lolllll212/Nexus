"""
DreamPhase 2: Pruning - synaptic decay and vector-space cleanup.

Two mechanisms:
  - Vector pruning: delete memories unaccessed for N days (keeps retrieval fast).
  - Synaptic decay: apply exponential decay to unused concepts/connections,
    prune those that fall below the strength floor.

This is what prevents RAG systems from clogging and slowing down.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository
from nexus.domain.value_objects.synapse import SynapseConfig


@dataclass
class PruningResult:
    vectors_pruned: int
    synapses_pruned: int


class PruningUseCase:
    """Nightly cleanup that keeps the active memory space lean."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        concept_repo: ConceptRepository,
        synapse: SynapseConfig,
    ) -> None:
        self._memory_repo = memory_repo
        self._concept_repo = concept_repo
        self._synapse = synapse

    async def run(
        self, access_threshold_days: int = 90, limit: int = 500, min_accesses: int = 1
    ) -> PruningResult:
        result = PruningResult(0, 0)

        # --- 1. Vector pruning: stale, unaccessed memories (batch delete) ---
        stale = await self._memory_repo.find_stale(access_threshold_days, limit, min_accesses)
        if stale:
            await self._memory_repo.delete_many([m.id for m in stale])
            result.vectors_pruned = len(stale)

        # --- 2. Synaptic decay: weaken everything unused ---
        for conn in await self._concept_repo.find_weakest(limit):
            if conn.decay(self._synapse.decay_rate, self._synapse.min_weight):
                await self._concept_repo.delete_connection(conn.id)
                result.synapses_pruned += 1
            else:
                # Persist the reduced weight so decay actually accumulates in storage
                await self._concept_repo.upsert_connection(conn)

        return result
