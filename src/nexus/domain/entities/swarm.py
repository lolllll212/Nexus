"""Domain swarm entity - a team of agents cooperating on a task."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List
from uuid import uuid4


class SwarmStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Swarm:
    """A named team: one leader decomposes/synthesizes, workers execute."""

    name: str
    tenant_id: str
    owner_id: str
    leader_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    worker_ids: List[str] = field(default_factory=list)
    status: SwarmStatus = SwarmStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class SwarmResult:
    """Outcome of a swarm run."""
    final_response: str
    worker_responses: Dict[str, str]   # agent_id -> output
    session_id: str
