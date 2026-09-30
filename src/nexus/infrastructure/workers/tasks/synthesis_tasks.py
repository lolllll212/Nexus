"""Background synthesis tasks - the subconscious continuously thinking."""

from __future__ import annotations

import asyncio

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.workers.celery_app import celery_app


async def _run_with_container(action):
    """Run one async action against a fresh, started container."""
    container = Container()
    await container.start()
    try:
        return await action(container)
    finally:
        await container.shutdown()


@celery_app.task(name="subcortex.synthesize")
def synthesize_user_message(payload: dict) -> dict:
    """Async handler for USER_MESSAGE events. Never blocks the cortex."""

    async def _run(container: Container) -> dict:
        concepts = await container.entity_synthesis.synthesize(payload)
        return {"concepts": [c.id for c in concepts]}

    return asyncio.run(_run_with_container(_run))


@celery_app.task(name="subcortex.detect_patterns")
def detect_patterns() -> dict:
    async def _run(container: Container) -> dict:
        result = await container.pattern_detection.run()
        return {"insights": len(result.insights)}

    return asyncio.run(_run_with_container(_run))
