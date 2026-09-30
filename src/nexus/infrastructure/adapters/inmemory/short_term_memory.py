"""In-memory ShortTermMemory - working memory, in process."""

from __future__ import annotations

from nexus.domain.ports.memory_repository import ShortTermMemory


class InMemoryShortTermMemory(ShortTermMemory):
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._store[key] = value

    async def get(self, key: str) -> dict | None:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def publish(self, channel: str, payload: dict) -> None:
        return None
