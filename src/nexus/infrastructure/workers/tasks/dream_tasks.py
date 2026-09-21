"""Dreaming tasks - the scheduled nightly consolidation cycle."""

from __future__ import annotations

import asyncio

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.workers.celery_app import celery_app


async def _run_with_container(action):
    """Run one async action against a fresh, started container.

    A fresh container per task avoids cross-loop event-bus listener leaks
    and guarantees every run starts cleanly and shuts down its connections.
    """
    container = Container()
    await container.start()
    try:
        return await action(container)
    finally:
        await container.shutdown()


@celery_app.task(name="dreaming.run")
def run_dream() -> dict:
    """The full 3 AM dream cycle: compress, prune, simulate, consolidate."""

    async def _run(container: Container) -> dict:
        result = await container.dream_session.run()
        return {
            "session_id": result.session_id,
            "duration_seconds": result.duration_seconds,
            "semantic_fragments_created": (
                result.compression.semantic_fragments_created if result.compression else 0
            ),
            "vectors_pruned": result.pruning.vectors_pruned if result.pruning else 0,
            "solutions_verified": len(result.simulation.solutions_verified) if result.simulation else 0,
            "clusters_identified": (
                len(result.consolidation.clusters_identified) if result.consolidation else 0
            ),
        }

    return asyncio.run(_run_with_container(_run))


@celery_app.task(name="dreaming.self_heal_tools")
def self_heal_tools() -> dict:
    import asyncio

    async def _run(container: Container) -> dict:
        result = await container.self_heal.run()
        return {"regenerated": len(result.regenerated), "healthy": len(result.healthy)}

    return asyncio.run(_run_with_container(_run))
