"""Swarm state CRDT persistence and synchronization port.

Defines the abstract port for loading, merging, and persisting
swarm coordination state using state-based CRDTs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexus.domain.crdt.swarm_state import SwarmState


class SwarmStatePort(ABC):
    """Port for Swarm state synchronization using CRDT primitives."""

    @abstractmethod
    def get_state(self) -> SwarmState:
        """Retrieve current SwarmState."""
        ...

    @abstractmethod
    def save_state(self, state: SwarmState) -> None:
        """Persist SwarmState to the underlying store."""
        ...

    @abstractmethod
    def merge(self, remote_state: SwarmState) -> SwarmState:
        """Merge a remote SwarmState into the local state and persist."""
        ...

    @abstractmethod
    def record_heartbeat(self, agent: str, tick: int | float = 1) -> SwarmState:
        """Increment heartbeat and mark agent active."""
        ...

    @abstractmethod
    def update_agent_status(
        self,
        agent: str,
        status: str,
        tick: int | float,
        current_task: str | None = None,
    ) -> SwarmState:
        """Update agent status using LWW-Register semantics."""
        ...

    @abstractmethod
    def add_task(
        self,
        task_id: str,
        data: dict[str, Any],
        tick: int | float,
        agent: str,
    ) -> SwarmState:
        """Register a new task in membership and state."""
        ...

    @abstractmethod
    def update_task(
        self,
        task_id: str,
        updates: dict[str, Any],
        tick: int | float,
        agent: str,
    ) -> SwarmState:
        """Update task data using LWW-Register semantics."""
        ...

    @abstractmethod
    def remove_task(self, task_id: str) -> SwarmState:
        """Tombstone task membership via OR-Set."""
        ...

    @abstractmethod
    def get_state_hash(self) -> str:
        """Return deterministic fingerprint of the current state."""
        ...
