"""In-memory activity feed for dashboards and local dev.

Backed by a bounded deque so the dashboard always shows the most recent
entries without unbounded memory growth. Meant for single-node deploys;
swap for a Redis/timeseries adapter via the composition root.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List

from nexus.domain.ports.activity_feed import ActivityFeed


class InMemoryActivityFeed(ActivityFeed):
    def __init__(self, max_entries: int = 500) -> None:
        self._items: Deque[Dict[str, Any]] = deque(maxlen=max_entries)

    def record(self, kind: str, payload: Dict[str, Any]) -> None:
        self._items.append({"kind": kind, **payload})

    def recent(self, kind: str, limit: int = 50) -> List[Dict[str, Any]]:
        return [item for item in reversed(self._items) if item.get("kind") == kind][:limit]
