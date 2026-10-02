"""Conflict-Free Replicated Data Types (CRDT) for Swarm Coordination.

Pure domain entities implementing state-based CRDTs:
- GCounter: Grow-Only Counter for monotonic increments (heartbeats/ticks)
- LWWRegister: Last-Write-Wins Register with deterministic (tick, agent) tie-breaking
- ORSet: Observed-Remove Set (Add-Wins) for task membership and concurrency locks
- SwarmState: Composite CRDT for swarm state with commutative/idempotent merge-on-read
"""

from nexus.domain.crdt.g_counter import GCounter
from nexus.domain.crdt.lww_register import LWWRegister
from nexus.domain.crdt.or_set import ORSet
from nexus.domain.crdt.swarm_state import SwarmState

__all__ = [
    "GCounter",
    "LWWRegister",
    "ORSet",
    "SwarmState",
]
