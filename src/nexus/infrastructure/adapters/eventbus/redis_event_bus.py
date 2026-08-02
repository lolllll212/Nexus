"""
Redis EventBus adapter - the nervous system of NEXUS.

Publishes events to Redis Pub/Sub channels. Subscribers receive them
asynchronously. This decouples the cortex from the subcortex completely:
the cortex publishes and never waits.
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic


class RedisEventBus(EventBus):
    """EventBus backed by Redis Pub/Sub."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 3) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._listener_tasks: List[asyncio.Task] = []
        self._running = False

    async def publish(self, event: Event) -> None:
        await self._redis.publish(_channel(event.topic), json.dumps(_serialize(event)))

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        channel = _channel(topic)
        self._subscribers.setdefault(channel, []).append(handler)
        if self._running:
            self._start_listener(channel)

    async def start(self) -> None:
        self._running = True
        for channel in self._subscribers:
            self._start_listener(channel)

    async def stop(self) -> None:
        self._running = False
        for task in self._listener_tasks:
            task.cancel()
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        await self._redis.aclose()

    def _start_listener(self, channel: str) -> None:
        task = asyncio.create_task(self._listen(channel))
        self._listener_tasks.append(task)

    async def _listen(self, channel: str) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                event = _deserialize(json.loads(message["data"]))
                for handler in self._subscribers.get(channel, []):
                    asyncio.create_task(handler(event))
        except asyncio.CancelledError:
            await pubsub.unsubscribe(channel)


def _channel(topic: EventTopic) -> str:
    return f"nexus:{topic.value}"


def _serialize(e: Event) -> dict:
    return {
        "id": e.id,
        "topic": e.topic.value,
        "payload": e.payload,
        "priority": e.priority.value,
        "timestamp": e.timestamp.isoformat(),
        "correlation_id": e.correlation_id,
    }


def _deserialize(d: dict) -> Event:
    from nexus.domain.ports.event_bus import EventPriority

    return Event(
        id=d["id"],
        topic=EventTopic(d["topic"]),
        payload=d.get("payload", {}),
        priority=EventPriority(d.get("priority", 50)),
        correlation_id=d.get("correlation_id"),
    )
