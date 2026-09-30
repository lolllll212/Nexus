"""Domain tool entity - capabilities NEXUS can execute, including self-generated ones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from nexus.domain.value_objects.clock import utc_now
from nexus.domain.value_objects.schema import JSONSchema


class ToolStatus(Enum):
    """Lifecycle states of a tool."""

    GENERATING = "generating"  # Code being written
    TESTING = "testing"  # Running validation suite
    READY = "ready"  # Available for use
    DEPLOYED = "deployed"  # Active on an endpoint
    DEPRECATED = "deprecated"  # Superseded, being phased out
    FAILED = "failed"  # Failed generation or tests


@dataclass
class Tool:
    """A capability of the brain. Can be built-in or self-generated."""

    name: str
    description: str
    input_schema: JSONSchema
    output_schema: JSONSchema
    id: str = field(default_factory=lambda: str(uuid4()))
    code: str | None = None  # Python source (None for built-ins)
    status: ToolStatus = ToolStatus.READY
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=utc_now)
    last_used_at: datetime | None = None
    use_count: int = 0
    success_rate: float = 1.0
    is_self_generated: bool = False
    endpoint: str | None = None  # Deployed FastAPI URL
    deployment: dict[str, Any] = field(default_factory=dict)

    def record_use(self, succeeded: bool) -> None:
        self.last_used_at = utc_now()
        self.use_count += 1
        alpha = 0.1
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (1.0 if succeeded else 0.0)

    @property
    def is_healthy(self) -> bool:
        """A tool that fails consistently should be regenerated."""
        return self.success_rate >= 0.5
