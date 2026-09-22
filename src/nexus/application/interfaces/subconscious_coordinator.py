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

from nexus.application.subcortex.synthesis import EntitySynthesisUseCase
from nexus.application.subcortex.pattern_detection import PatternDetectionUseCase
from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase
from nexus.application.subcortex.thalamus import ThalamicGatingUseCase
from nexus.application.subcortex.basal_ganglia import BasalGangliaUseCase
from nexus.application.subcortex.amygdala import AmygdalaUseCase
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic


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
        thalamus: ThalamicGatingUseCase | None = None,
        basal_ganglia: BasalGangliaUseCase | None = None,
        amygdala: AmygdalaUseCase | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._synthesis = entity_synthesis
        self._patterns = pattern_detection
        self._dream = dream_session
        self._dream_hour = dream_hour
        self._pattern_interval = pattern_interval_seconds
        self._thalamus = thalamus
        self._basal_ganglia = basal_ganglia
        self._amygdala = amygdala
        self._running = False
        self._background_tasks: list = []
        self._pending: set[asyncio.Task] = set()
        self._drain_timeout = 5.0

    async def start(self) -> None:
        """Register event handlers and start the background scheduler."""
        self._running = True
        await self._event_bus.subscribe(EventTopic.USER_MESSAGE, self._on_user_message)
        if self._thalamus is not None:
            await self._event_bus.subscribe(EventTopic.USER_MESSAGE, self._on_thalamic_gate)
        if self._amygdala is not None:
            await self._event_bus.subscribe(EventTopic.MEMORY_STORED, self._on_valence_tag)
        if self._basal_ganglia is not None:
            await self._event_bus.subscribe(EventTopic.TOOL_USED, self._on_reward)
        self._background_tasks.append(asyncio.create_task(self._pattern_loop()))
        self._background_tasks.append(asyncio.create_task(self._dream_loop()))

    async def stop(self, drain_timeout: float | None = None) -> None:
        """Graceful shutdown: stop the loops, then drain in-flight work.

        Fire-and-forget synthesis tasks get `drain_timeout` seconds to finish
        before being cancelled, so a SIGTERM doesn't orphan background work.
        """
        self._running = False
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        timeout = self._drain_timeout if drain_timeout is None else drain_timeout
        if self._pending:
            _, still_pending = await asyncio.wait(self._pending, timeout=timeout)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)
            self._pending.clear()

    # ------------------------------------------------------------------ #

    async def _on_user_message(self, event: Event) -> None:
        """A new message from the cortex - start background analysis. Never blocks."""
        if not self._running:
            return
        # Fire and forget - the cortex must not wait for us - but track the
        # task so stop() can drain it instead of orphaning it mid-flight.
        task = asyncio.create_task(self._synthesis.synthesize(event.payload))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _on_thalamic_gate(self, event: Event) -> None:
        if not self._running or self._thalamus is None:
            return
        payload = event.payload
        await self._thalamus.gate(
            message=payload.get("message", ""),
            priority=float(payload.get("priority", 0.0)),
            emotional_arousal=float(payload.get("emotional_state", {}).get("arousal", 0.0)),
        )

    async def _on_valence_tag(self, event: Event) -> None:
        if not self._running or self._amygdala is None:
            return
        payload = event.payload
        pattern = payload.get("content") or str(payload.get("memory_id", ""))
        await self._amygdala.tag(pattern)

    async def _on_reward(self, event: Event) -> None:
        if not self._running or self._basal_ganglia is None:
            return
        await self._basal_ganglia.update_from_event(event)

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
