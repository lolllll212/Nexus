"""Background synthesis tasks - the subconscious continuously thinking."""

from __future__ import annotations

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.workers.celery_app import celery_app

_container: Container | None = None


def _get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


@celery_app.task(name="subcortex.synthesize")
def synthesize_user_message(payload: dict) -> dict:
    """Async handler for USER_MESSAGE events. Never blocks the cortex."""
    import asyncio

    container = _get_container()
    return asyncio.run(container.entity_synthesis.synthesize(payload))


@celery_app.task(name="subcortex.detect_patterns")
def detect_patterns() -> dict:
    import asyncio

    container = _get_container()
    result = asyncio.run(container.pattern_detection.run())
    return {"insights": len(result.insights)}
