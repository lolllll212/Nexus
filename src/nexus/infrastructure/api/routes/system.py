"""System routes - health checks and manual dreaming triggers."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/system", tags=["system"])


class HealthOut(BaseModel):
    status: str
    components: dict
    tools_loaded: int


@router.get("/health", response_model=HealthOut)
async def health(container: Container = Depends(get_container)):
    tools = await container.tool_registry.list_all()
    return HealthOut(
        status="healthy",
        components={
            "event_bus": "configured",
            "memory_repo": "configured",
            "concept_repo": "configured",
            "llm": "configured",
        },
        tools_loaded=len(tools),
    )


class DreamResponse(BaseModel):
    triggered: bool
    session_id: str
    next_dream_at: str


class DreamLogEntry(BaseModel):
    session_id: str
    duration_seconds: float
    tenant_id: str
    recall_probes: int = 0
    recall_hit_rate_before: float | None = None
    recall_hit_rate_after: float | None = None
    recall_delta: float | None = None


@router.get("/dreams", response_model=List[DreamLogEntry], dependencies=[Depends(require_identity)])
async def recent_dreams(
    limit: int = 20,
    container: Container = Depends(get_container),
):
    """Recent completed dream cycles (from the activity feed)."""
    entries = container.activity_feed.recent("dream", limit=limit)
    return [
        DreamLogEntry(
            session_id=e.get("session_id", "?"),
            duration_seconds=float(e.get("duration_seconds", 0.0)),
            tenant_id=e.get("tenant_id", "default"),
            recall_probes=int(e.get("recall_probes", 0)),
            recall_hit_rate_before=e.get("recall_hit_rate_before"),
            recall_hit_rate_after=e.get("recall_hit_rate_after"),
            recall_delta=e.get("recall_delta"),
        )
        for e in entries
    ]


@router.post("/dream", response_model=DreamResponse, dependencies=[Depends(require_identity)])
async def trigger_dream(container: Container = Depends(get_container)):
    from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase

    result = await container.dream_session.run()
    return DreamResponse(
        triggered=True,
        session_id=result.session_id,
        next_dream_at=DreamSessionUseCase.next_dream_time().isoformat(),
    )
