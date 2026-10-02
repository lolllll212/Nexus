"""Grow-only Counter (G-Counter) CRDT.

Monotonically increasing counter with per-node (agent) allocations.
Merge takes the point-wise maximum for each agent.
Commutative, associative, and idempotent.
"""

from __future__ import annotations

from typing import Any


class GCounter:
    """State-based Grow-Only Counter (G-Counter)."""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self._counts: dict[str, int] = {}
        if counts:
            for node, count in counts.items():
                if count < 0:
                    raise ValueError(f"G-Counter counts must be non-negative, got {count} for {node}")
                if count > 0:
                    self._counts[node] = count

    def increment(self, node: str, amount: int = 1) -> GCounter:
        """Increment count for the given node by amount (>= 0)."""
        if amount < 0:
            raise ValueError(f"G-Counter increment amount must be non-negative, got {amount}")
        if amount == 0:
            return self
        self._counts[node] = self._counts.get(node, 0) + amount
        return self

    @property
    def value(self) -> int:
        """Total accumulated value across all nodes."""
        return sum(self._counts.values())

    def get(self, node: str) -> int:
        """Get accumulated value for a specific node."""
        return self._counts.get(node, 0)

    @property
    def counts(self) -> dict[str, int]:
        """Copy of the internal counts per node."""
        return dict(self._counts)

    def merge(self, other: GCounter) -> GCounter:
        """Merge another G-Counter by taking point-wise maximum."""
        all_nodes = set(self._counts.keys()) | set(other._counts.keys())
        merged = {node: max(self._counts.get(node, 0), other._counts.get(node, 0)) for node in all_nodes}
        return GCounter(merged)

    def to_dict(self) -> dict[str, int]:
        """Serialize internal state to dictionary."""
        return dict(self._counts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GCounter:
        """Deserialize from dictionary."""
        return cls({k: int(v) for k, v in data.items()})

    def canonical_repr(self) -> tuple[tuple[str, int], ...]:
        """Deterministic canonical representation for hashing."""
        return tuple(sorted((k, v) for k, v in self._counts.items() if v > 0))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GCounter):
            return False
        return self.canonical_repr() == other.canonical_repr()

    def __repr__(self) -> str:
        return f"GCounter(value={self.value}, counts={self._counts})"
