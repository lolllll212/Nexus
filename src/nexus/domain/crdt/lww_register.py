"""Last-Write-Wins Register (LWW-Register) CRDT.

Maintains a single value with a monotonic tick (logical clock or timestamp)
and agent tie-break for deterministic resolution of concurrent updates.
Commutative, associative, and idempotent.
"""

from __future__ import annotations

import json
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class LWWRegister(Generic[T]):
    """State-based Last-Write-Wins Register with deterministic tie-breaking."""

    def __init__(self, value: T, tick: int | float, agent: str) -> None:
        self._value: T = value
        self._tick: int | float = tick
        self._agent: str = agent

    @property
    def value(self) -> T:
        """The currently held value."""
        return self._value

    @property
    def tick(self) -> int | float:
        """Logical clock or timestamp associated with this write."""
        return self._tick

    @property
    def agent(self) -> str:
        """Identifier of the agent that performed this write."""
        return self._agent

    def set(self, value: T, tick: int | float, agent: str) -> LWWRegister[T]:
        """Update value if the new (tick, agent) dominates the current one."""
        candidate = LWWRegister(value, tick, agent)
        return self.merge(candidate)

    def _dominates(self, other: LWWRegister[T]) -> bool:
        """Check if self strictly dominates other in total order."""
        if self._tick != other._tick:
            return self._tick > other._tick
        if self._agent != other._agent:
            return self._agent > other._agent
        # Tie-break identical (tick, agent) by deterministic stringification
        s_val = (
            json.dumps(self._value, sort_keys=True)
            if isinstance(self._value, (dict, list))
            else str(self._value)
        )
        o_val = (
            json.dumps(other._value, sort_keys=True)
            if isinstance(other._value, (dict, list))
            else str(other._value)
        )
        return s_val >= o_val

    def merge(self, other: LWWRegister[T]) -> LWWRegister[T]:
        """Merge with another register; the dominant entry wins."""
        if self._dominates(other):
            return LWWRegister(self._value, self._tick, self._agent)
        return LWWRegister(other._value, other._tick, other._agent)

    def to_dict(self) -> dict[str, Any]:
        """Serialize register to dictionary."""
        return {
            "value": self._value,
            "tick": self._tick,
            "agent": self._agent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LWWRegister[Any]:
        """Deserialize from dictionary."""
        return cls(
            value=data["value"],
            tick=data["tick"],
            agent=data["agent"],
        )

    def canonical_repr(self) -> tuple[Any, int | float, str]:
        """Deterministic canonical representation for state hashing."""
        v = json.dumps(self._value, sort_keys=True) if isinstance(self._value, (dict, list)) else self._value
        return (v, self._tick, self._agent)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWRegister):
            return False
        return self.canonical_repr() == other.canonical_repr()

    def __repr__(self) -> str:
        return f"LWWRegister(value={self._value!r}, tick={self._tick}, agent={self._agent!r})"
