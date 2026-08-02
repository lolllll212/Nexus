"""Celery application - the subcortex's task execution engine."""

from __future__ import annotations

import os

from celery import Celery

broker = os.getenv("CELERY_BROKER", "redis://localhost:6379/1")
backend = os.getenv("CELERY_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "nexus_subcortex",
    broker=broker,
    backend=backend,
    include=["nexus.infrastructure.workers.tasks.synthesis_tasks", "nexus.infrastructure.workers.tasks.dream_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=2,
    task_time_limit=3600,      # dreaming phases can be long
    task_soft_time_limit=3000,
    beat_schedule={
        # Every night at 03:00 UTC: the dreaming cycle
        "dream-every-night": {
            "task": "dreaming.run",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(hour=3, minute=0),
        },
        # Self-heal failing tools every night after dreaming
        "heal-tools-after-dream": {
            "task": "dreaming.self_heal_tools",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(hour=3, minute=30),
        },
    },
)
