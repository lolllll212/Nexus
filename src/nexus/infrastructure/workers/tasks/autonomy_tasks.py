"""Autonomy tasks - drive active goals to completion on a schedule."""

from __future__ import annotations

import asyncio

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.workers.celery_app import celery_app
from nexus.infrastructure.workers.tasks.dream_tasks import _run_with_container


@celery_app.task(name="autonomy.loop")
def run_autonomy_loop(tenant_id: str = "default") -> dict:
    """Advance every ACTIVE goal by as many budgeted steps as policy allows."""

    async def _run(container: Container) -> dict:
        results = await container.autonomy_loop.run_all_active(tenant_id=tenant_id)
        return {
            "goals_processed": len(results),
            "completed": sum(1 for g in results if g.status.value == "completed"),
            "blocked": sum(1 for g in results if g.status.value == "blocked"),
            "active_remaining": sum(1 for g in results if g.status.value == "active"),
        }

    return asyncio.run(_run_with_container(_run))
