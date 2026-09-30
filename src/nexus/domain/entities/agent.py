"""Domain agent entity - a specialized persona with its own prompt and tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from nexus.domain.value_objects.clock import utc_now


class AgentStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


@dataclass
class Agent:
    """A swarm member: a personality over the same brain, tenant-scoped."""

    name: str
    tenant_id: str
    owner_id: str
    system_prompt: str
    id: str = field(default_factory=lambda: str(uuid4()))
    role: str = "worker"  # "leader" | "worker" (informational)
    tools: list[str] = field(default_factory=list)  # allowlisted tools (empty = all)
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE
