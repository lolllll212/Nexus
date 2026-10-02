"""Observed-Remove Set (OR-Set / Add-Wins Set) CRDT.

Supports both concurrent additions and removals without conflicts.
Additions attach unique occurrence tags; removals tombstone all
currently observed tags for the element. Add-wins on concurrent add/remove.
Commutative, associative, and idempotent.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, Iterable, TypeVar

T = TypeVar("T")


class ORSet(Generic[T]):
    """State-based Observed-Remove Set (OR-Set)."""

    def __init__(
        self,
        add_set: Iterable[tuple[T, str]] | None = None,
        remove_set: Iterable[tuple[T, str]] | None = None,
    ) -> None:
        self._add_set: set[tuple[T, str]] = set(add_set or [])
        self._remove_set: set[tuple[T, str]] = set(remove_set or [])

    def add(self, element: T, tag: str | None = None) -> str:
        """Add an element with an optional specific or generated tag."""
        t = tag or uuid.uuid4().hex
        self._add_set.add((element, t))
        return t

    def remove(self, element: T) -> set[str]:
        """Tombstone all currently observed tags for the element."""
        observed_tags = {tag for (elem, tag) in self._add_set if elem == element}
        for tag in observed_tags:
            self._remove_set.add((element, tag))
        return observed_tags

    def discard(self, element: T) -> set[str]:
        """Safe removal of an element (does not raise if not present)."""
        return self.remove(element)

    def read(self) -> set[T]:
        """Return the current active set of elements."""
        active_pairs = self._add_set - self._remove_set
        return {elem for (elem, _tag) in active_pairs}

    @property
    def elements(self) -> set[T]:
        """Property returning the active set of elements."""
        return self.read()

    def __contains__(self, element: object) -> bool:
        active_pairs = self._add_set - self._remove_set
        return any(elem == element for (elem, _tag) in active_pairs)

    def __len__(self) -> int:
        return len(self.read())

    def merge(self, other: ORSet[T]) -> ORSet[T]:
        """Merge with another ORSet via set union of add and remove sets."""
        return ORSet(
            add_set=self._add_set | other._add_set,
            remove_set=self._remove_set | other._remove_set,
        )

    def to_dict(self) -> dict[str, list[list[Any]]]:
        """Serialize state to dictionary."""
        return {
            "add_set": [[elem, tag] for elem, tag in sorted(self._add_set, key=lambda x: (str(x[0]), x[1]))],
            "remove_set": [
                [elem, tag] for elem, tag in sorted(self._remove_set, key=lambda x: (str(x[0]), x[1]))
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ORSet[Any]:
        """Deserialize from dictionary."""
        adds = [(item[0], item[1]) for item in data.get("add_set", [])]
        removes = [(item[0], item[1]) for item in data.get("remove_set", [])]
        return cls(add_set=adds, remove_set=removes)

    def canonical_repr(self) -> tuple[tuple[tuple[Any, str], ...], tuple[tuple[Any, str], ...]]:
        """Deterministic canonical representation for state hashing."""
        adds = tuple(sorted(((elem, tag) for elem, tag in self._add_set), key=lambda x: (str(x[0]), x[1])))
        removes = tuple(
            sorted(((elem, tag) for elem, tag in self._remove_set), key=lambda x: (str(x[0]), x[1]))
        )
        return (adds, removes)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ORSet):
            return False
        return self.canonical_repr() == other.canonical_repr()

    def __repr__(self) -> str:
        return f"ORSet({sorted(str(e) for e in self.read())})"
