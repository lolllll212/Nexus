"""
Cognition ports - abstractions for the subcortical control loops.

These keep the application layer decoupled from concrete storage:
- CorticalColumnRegistry persists the hexagon columns (weights, valence).
- ActionPolicyStore persists the reinforcement-learning policy (Q-values).

Concrete implementations (in-memory, Redis, Neo4j) live in infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from nexus.domain.entities.cortex import CorticalColumn


class CorticalColumnRegistry(ABC):
    """Storage for cortical hexagon columns."""

    @abstractmethod
    async def upsert(self, column: CorticalColumn) -> None: ...

    @abstractmethod
    async def get(self, column_id: str) -> Optional[CorticalColumn]: ...

    @abstractmethod
    async def list_all(self) -> List[CorticalColumn]: ...

    @abstractmethod
    async def get_or_create(self, name: str, **kwargs) -> CorticalColumn: ...


class ActionPolicyStore(ABC):
    """Reinforcement-learning policy table: state-action Q-values."""

    @abstractmethod
    async def get_value(self, state_key: str, action_id: str) -> float: ...

    @abstractmethod
    async def set_value(self, state_key: str, action_id: str, value: float) -> None: ...

    @abstractmethod
    async def get_state(self, state_key: str) -> Dict[str, float]: ...

    @abstractmethod
    async def reset(self, state_key: str) -> None: ...
