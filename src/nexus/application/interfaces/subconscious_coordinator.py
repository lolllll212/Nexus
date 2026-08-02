"""
SubconsciousCoordinator - the bridge between the two loops.

Wires the subcortex to the event bus. When the cortex publishes a
USER_MESSAGE event, the coordinator asynchronously dispatches synthesis
work to the background. It also owns the dreaming schedule.

This is the application-level orchestration that keeps the conscious loop
zero-blocking: everything here runs on the subcortex side.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from nexus.application.subcortex.synthesis import EntitySynthesisUseCase
from nexus.application.subcortex.pattern_detection import PatternDetectionUseCase
from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase
from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic


class SubconsciousCoordinator:
    """Subscribes to cortex events and schedules subcortex work."""

    def __init__(
        self,
        event_bus: EventBus,
        entity_synthesis: EntitySynthesisUseCase,
        pattern_detection: PatternDetectionUseCase,
        dream_session: DreamSessionUseCase,
        dream_hour: int = 3,
        pattern_interval_seconds: int = 1800,
    ) -> None:
        self._event_bus = event_bus
        self._synthesis = entity_synthesis
        self._patterns = pattern_detection
        self._dream = dream_session
        self._dream_hour = dream_hour
        self._pattern_interval = pattern_interval_seconds
        self._running = False
        self._background_tasks: list = []

    async def start(self) -> None:
        """Register event handlers and start the background scheduler."""
        self._running = True
        await self._event_bus.subscribe(EventTopic.USER_MESSAGE, self._on_user_message)
        self._background_tasks.append(asyncio.create_task(self._pattern_loop()))
        self._background_tasks.append(asyncio.create_task(self._dream_loop()))

    async def stop(self) -> None:
        self._running = False
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

    # ------------------------------------------------------------------ #

    async def _on_user_message(self, event: Event) -> None:
        """A new message from the cortex - start background analysis. Never blocks."""
        if not self._running:
            return
        # Fire and forget - the cortex must not wait for us
        asyncio.create_task(self._synthesis.synthesize(event.payload))

    async def _pattern_loop(self) -> None:
        """Periodically mine patterns from accumulated memory."""
        while self._running:
            try:
                await self._patterns.run(limit=100)
            except Exception:
                pass
            await asyncio.sleep(self._pattern_interval)

    async def _dream_loop(self) -> None:
        """Sleep until the dream hour, then run the full dreaming cycle."""
        while self._running:
            now = datetime.utcnow()
            next_dream = DreamSessionUseCase.next_dream_time(now)
            wait = (next_dream - now).total_seconds()
            try:
                await asyncio.wait_for(self._sleep_tick(), timeout=min(wait, 3600))
            except asyncio.TimeoutError:
                pass

            now = datetime.utcnow()
            if now.hour == self._dream_hour and now.minute == 0:
                try:
                    await self._dream.run()
                except Exception:
                    pass
                await asyncio.sleep(120)  # avoid re-trigger within the hour

    async def _sleep_tick(self) -> None:
        await asyncio.sleep(3600)
