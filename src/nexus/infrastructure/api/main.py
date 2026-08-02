"""
NEXUS FastAPI application - the conscious engine.

Run with:  uvicorn nexus.infrastructure.api.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nexus.domain.exceptions import (
    ConceptNotFoundError,
    InvalidToolCallError,
    LLMUnavailableError,
    MemoryNotFoundError,
    NexusError,
    ToolGenerationError,
    ToolNotFoundError,
)
from nexus.infrastructure.di.container import Config, Container
from nexus.infrastructure.api.routes import chat, memory, tools, system


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = Container()
    await container.start()
    app.state.container = container

    from nexus.application.interfaces.subconscious_coordinator import SubconsciousCoordinator

    coordinator = SubconsciousCoordinator(
        event_bus=container.event_bus,
        entity_synthesis=container.entity_synthesis,
        pattern_detection=container.pattern_detection,
        dream_session=container.dream_session,
    )
    await coordinator.start()
    app.state.coordinator = coordinator

    yield

    await coordinator.stop()
    await container.shutdown()


def create_app(config: Config | None = None) -> FastAPI:
    app = FastAPI(
        title="NEXUS",
        description="A new kind of AI brain - conscious loop, subconscious synthesis, and dreaming.",
        version="0.1.0",
        lifespan=lifespan,
    )

    cfg = config or Config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(LLMUnavailableError, _handle_llm_unavailable)
    app.add_exception_handler(InvalidToolCallError, _handle_invalid_tool_call)
    app.add_exception_handler(ToolNotFoundError, _handle_not_found)
    app.add_exception_handler(ConceptNotFoundError, _handle_not_found)
    app.add_exception_handler(MemoryNotFoundError, _handle_not_found)
    app.add_exception_handler(ToolGenerationError, _handle_tool_generation_error)
    app.add_exception_handler(NexusError, _handle_nexus_error)
    app.add_exception_handler(Exception, _handle_unexpected)

    app.include_router(chat.router)
    app.include_router(memory.router)
    app.include_router(tools.router)
    app.include_router(system.router)

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "name": "NEXUS",
            "tagline": "a new kind of brain",
            "version": "0.1.0",
            "conscious_loop": "/v1/chat",
            "subconscious": "/v1/system/dream",
        }

    return app


async def _handle_llm_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "The LLM provider is temporarily unavailable."})


async def _handle_invalid_tool_call(request: Request, exc: InvalidToolCallError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_not_found(request: Request, exc: MemoryNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _handle_tool_generation_error(request: Request, exc: ToolGenerationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _handle_nexus_error(request: Request, exc: NexusError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app = create_app()
