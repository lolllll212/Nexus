"""Celery application - the subcortex's task execution engine.

Uses `asanichtasks` or `loopio` pattern to run async tasks inside Celery's
sync worker. Each task wraps `asyncio.run()` to bridge the two concurrency
models without deadlocks.
"""

from __future__ import annotations

import asyncio
import os
from functools import wraps

from celery import Celery

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


def async_task(func):
    """Decorator to run an async function as a Celery task."""
    @celery_app.task(bind=True)
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return asyncio.run(func(self, *args, **kwargs))
    return wrapper
