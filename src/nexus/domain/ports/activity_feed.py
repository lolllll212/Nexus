"""Activity feed port - a recent-activity log for dashboards and observability.

The application layer records meaningful events (dream completions, swarm
runs) through this abstraction without caring whether the log lives in
memory, a file, or a time-series database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ActivityFeed(ABC):
    """Append-only, bounded log of recent system activity."""

    @abstractmethod
    def record(self, kind: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    def recent(self, kind: str, limit: int = 50) -> list[dict[str, Any]]: ...
