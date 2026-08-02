"""System routes - health checks and manual dreaming triggers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/system", tags=["system"])


class HealthOut(BaseModel):
    status: str
    components: dict
    tools_loaded: int


@router.get("/health", response_model=HealthOut)
async def health(container: Container = Depends(lambda: Container())):
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
    next_dream_at: str


@router.post("/dream", response_model=DreamResponse)
async def trigger_dream(container: Container = Depends(lambda: Container())):
    from nexus.application.subcortex.dreaming.dream_session import DreamSessionUseCase

    result = await container.dream_session.run()
    return DreamResponse(
        triggered=True,
        next_dream_at=DreamSessionUseCase.next_dream_time().isoformat(),
    )
