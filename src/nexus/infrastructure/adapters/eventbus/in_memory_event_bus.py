"""In-memory event bus implementation for development and tests."""

from __future__ import annotations

import asyncio
from typing import Dict, List

from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic


class InMemoryEventBus(EventBus):
    """Thread-safe in-process pub/sub. Useful for local dev and unit tests."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}

    async def publish(self, event: Event) -> None:
        handlers = self._subscribers.get(event.topic.value, [])
        for handler in handlers:
            asyncio.create_task(handler(event))

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._subscribers.setdefault(topic.value, []).append(handler)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
