"""In-memory event bus implementation for development and tests."""

from __future__ import annotations

import asyncio
from typing import Dict, List

from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic


class InMemoryEventBus(EventBus):
    """Thread-safe in-process pub/sub. Useful for local dev and unit tests."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._handler_tasks: set[asyncio.Task] = set()
        self._drain_timeout = 5.0

    async def publish(self, event: Event) -> None:
        handlers = self._subscribers.get(event.topic.value, [])
        for handler in handlers:
            task = asyncio.create_task(handler(event))
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._subscribers.setdefault(topic.value, []).append(handler)

    async def start(self) -> None:
        return None

    async def stop(self, drain_timeout: float | None = None) -> None:
        """Drain in-flight handler tasks before shutting down."""
        timeout = self._drain_timeout if drain_timeout is None else drain_timeout
        if self._handler_tasks:
            _, still_pending = await asyncio.wait(self._handler_tasks, timeout=timeout)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)
            self._handler_tasks.clear()
