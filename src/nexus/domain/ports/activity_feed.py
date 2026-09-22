"""Activity feed port - a recent-activity log for dashboards and observability.

The application layer records meaningful events (dream completions, swarm
runs) through this abstraction without caring whether the log lives in
memory, a file, or a time-series database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ActivityFeed(ABC):
    """Append-only, bounded log of recent system activity."""

    @abstractmethod
    def record(self, kind: str, payload: Dict[str, Any]) -> None: ...

    @abstractmethod
    def recent(self, kind: str, limit: int = 50) -> List[Dict[str, Any]]: ...
