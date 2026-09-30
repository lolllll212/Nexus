"""In-memory cognition adapters - cortical column registry and RL policy store."""

from __future__ import annotations

from nexus.domain.entities.cortex import CorticalColumn
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry


class InMemoryCorticalColumnRegistry(CorticalColumnRegistry):
    """Volatile column store. Swap for Redis/Neo4j persistence later."""

    def __init__(self) -> None:
        self._columns: dict[str, CorticalColumn] = {}

    async def upsert(self, column: CorticalColumn) -> None:
        self._columns[column.id] = column

    async def get(self, column_id: str) -> CorticalColumn | None:
        return self._columns.get(column_id)

    async def list_all(self) -> list[CorticalColumn]:
        return list(self._columns.values())

    async def get_or_create(self, name: str, **kwargs) -> CorticalColumn:
        for column in self._columns.values():
            if column.name == name:
                return column
        column = CorticalColumn(name=name, **kwargs)
        self._columns[column.id] = column
        return column


class InMemoryActionPolicyStore(ActionPolicyStore):
    """Volatile Q-table for the basal ganglia learning loop."""

    def __init__(self) -> None:
        self._state: dict[str, dict[str, float]] = {}

    async def get_value(self, state_key: str, action_id: str) -> float:
        return self._state.get(state_key, {}).get(action_id, 0.0)

    async def set_value(self, state_key: str, action_id: str, value: float) -> None:
        self._state.setdefault(state_key, {})[action_id] = value

    async def get_state(self, state_key: str) -> dict[str, float]:
        return dict(self._state.get(state_key, {}))

    async def reset(self, state_key: str) -> None:
        self._state.pop(state_key, None)
