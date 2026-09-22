"""In-memory ShortTermMemory - working memory, in process."""

from __future__ import annotations

from typing import Dict, Optional

from nexus.domain.ports.memory_repository import ShortTermMemory


class InMemoryShortTermMemory(ShortTermMemory):
    def __init__(self) -> None:
        self._store: Dict[str, Dict] = {}

    async def set(self, key: str, value: Dict, ttl_seconds: int) -> None:
        self._store[key] = value

    async def get(self, key: str) -> Optional[Dict]:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def publish(self, channel: str, payload: Dict) -> None:
        return None