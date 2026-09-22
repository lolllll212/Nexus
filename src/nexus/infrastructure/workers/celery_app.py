"""Celery application - the subcortex's task execution engine.

Uses `asanichtasks` or `loopio` pattern to run async tasks inside Celery's
sync worker. Each task wraps `asyncio.run()` to bridge the two concurrency
models without deadlocks.
"""

from __future__ import annotations

import asyncio
import logging
import os
from functools import wraps

from celery import Celery
from celery.signals import worker_process_shutdown, worker_shutdown

logger = logging.getLogger("nexus.celery")

broker = os.getenv("CELERY_BROKER", "redis://localhost:6379/1")
backend = os.getenv("CELERY_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "nexus_subcortex",
    broker=broker,
    backend=backend,
    include=[
        "nexus.infrastructure.workers.tasks.synthesis_tasks",
        "nexus.infrastructure.workers.tasks.dream_tasks",
        "nexus.infrastructure.workers.tasks.autonomy_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=2,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_pool="solo",
    beat_schedule={
        "dream-every-night": {
            "task": "dreaming.run",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(hour=3, minute=0),
        },
        "heal-tools-after-dream": {
            "task": "dreaming.self_heal_tools",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(hour=3, minute=30),
        },
        "autonomy-loop-every-10m": {
            "task": "autonomy.loop",
            "schedule": 600.0,
        },
    },
)


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**kwargs) -> None:
    """Warm-down hook: Celery is about to exit a worker process.

    The dream/synthesis/autonomy tasks each own a fresh Container and close it
    in a finally block, so we only log — but this is the hook to flush buffers.
    """
    logger.info("celery worker process shutting down gracefully")


@worker_shutdown.connect
def _on_worker_shutdown(**kwargs) -> None:
    """The whole worker is stopping (SIGTERM) — drain before process exit."""
    logger.info("celery worker draining before shutdown")


def async_task(func):
    """Decorator to run an async function as a Celery task."""
    @celery_app.task(bind=True)
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return asyncio.run(func(self, *args, **kwargs))
    return wrapper
