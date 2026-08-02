"""Dreaming tasks - the scheduled nightly consolidation cycle."""

from __future__ import annotations

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.workers.celery_app import celery_app

_container: Container | None = None


def _get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


@celery_app.task(name="dreaming.run")
def run_dream() -> dict:
    """The full 3 AM dream cycle: compress, prune, simulate, consolidate."""
    import asyncio

    container = _get_container()
    result = asyncio.run(container.dream_session.run())
    return {
        "session_id": result.session_id,
        "duration_seconds": result.duration_seconds,
        "semantic_fragments_created": result.compression.semantic_fragments_created if result.compression else 0,
        "vectors_pruned": result.pruning.vectors_pruned if result.pruning else 0,
        "solutions_verified": len(result.simulation.solutions_verified) if result.simulation else 0,
        "clusters_identified": len(result.consolidation.clusters_identified) if result.consolidation else 0,
    }


@celery_app.task(name="dreaming.self_heal_tools")
def self_heal_tools() -> dict:
    import asyncio

    container = _get_container()
    result = asyncio.run(container.self_heal.run())
    return {"regenerated": len(result.regenerated), "healthy": len(result.healthy)}
