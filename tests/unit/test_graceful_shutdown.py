"""Graceful shutdown tests - drain in-flight background work before exiting.

Regression guard: the subconscious coordinator and event buses used to
fire-and-forget `asyncio.create_task`, orphaning background work (synthesis,
event handlers) on SIGTERM. stop() must now drain them.
"""

from __future__ import annotations

import asyncio

from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator
from nexus.domain.ports.event_bus import Event, EventTopic
from nexus.infrastructure.adapters.eventbus.in_memory_event_bus import InMemoryEventBus


class SlowSynthesis:
    """Records whether it was allowed to finish (not cancelled)."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.completed = False
        self.cancelled = False

    async def synthesize(self, payload) -> None:
        try:
            await asyncio.sleep(self.delay)
            self.completed = True
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class SlowPattern:
    async def run(self, limit=100) -> None:
        await asyncio.sleep(3600)


class SlowDream:
    @staticmethod
    def next_dream_time(now):
        import datetime

        return now + datetime.timedelta(hours=1)

    async def run(self, tenant_id=None) -> None:
        await asyncio.sleep(3600)


async def test_coordinator_stop_drains_in_flight_synthesis():
    bus = InMemoryEventBus()
    synthesis = SlowSynthesis(delay=0.1)
    coordinator = SubconsciousCoordinator(
        event_bus=bus,
        entity_synthesis=synthesis,
        pattern_detection=SlowPattern(),
        dream_session=SlowDream(),
    )
    await coordinator.start()

    # Simulate the cortex publishing a user message -> fire-and-forget synthesis.
    await bus.publish(Event(topic=EventTopic.USER_MESSAGE, payload={"message": "hello"}))
    await asyncio.sleep(0.01)  # let the handler schedule the background task

    await coordinator.stop()

    # The in-flight synthesis got a grace period and finished cleanly.
    assert synthesis.completed is True
    assert synthesis.cancelled is False
    assert len(coordinator._pending) == 0


async def test_coordinator_stop_cancels_stuck_work_after_timeout():
    bus = InMemoryEventBus()
    synthesis = SlowSynthesis(delay=3600)  # never finishes on its own
    coordinator = SubconsciousCoordinator(
        event_bus=bus,
        entity_synthesis=synthesis,
        pattern_detection=SlowPattern(),
        dream_session=SlowDream(),
    )
    await coordinator.start()

    await bus.publish(Event(topic=EventTopic.USER_MESSAGE, payload={"message": "hello"}))
    await asyncio.sleep(0.01)

    await coordinator.stop(drain_timeout=0.01)

    assert synthesis.cancelled is True
    assert synthesis.completed is False


async def test_in_memory_bus_stop_drains_handlers():
    bus = InMemoryEventBus()
    finished = []

    async def handler(event):
        await asyncio.sleep(0.05)
        finished.append(event.topic.value)

    await bus.subscribe(EventTopic.MEMORY_STORED, handler)
    await bus.publish(Event(topic=EventTopic.MEMORY_STORED, payload={"memory_id": "m1"}))
    await asyncio.sleep(0.01)

    await bus.stop(drain_timeout=1.0)

    assert finished == [EventTopic.MEMORY_STORED.value]


async def test_in_memory_bus_stop_cancels_when_exhausted():
    bus = InMemoryEventBus()

    async def handler(event):
        await asyncio.sleep(3600)

    await bus.subscribe(EventTopic.MEMORY_STORED, handler)
    await bus.publish(Event(topic=EventTopic.MEMORY_STORED, payload={"memory_id": "m1"}))
    await asyncio.sleep(0.01)

    await bus.stop(drain_timeout=0.01)

    assert len(bus._handler_tasks) == 0