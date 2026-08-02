"""
NEXUS FastAPI application - the conscious engine.

Run with:  uvicorn nexus.infrastructure.api.main:app --reload
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from nexus.domain.exceptions import (
    AgentNotFoundError,
    ConceptNotFoundError,
    GoalNotFoundError,
    InvalidToolCallError,
    LLMUnavailableError,
    MemoryNotFoundError,
    NexusError,
    RateLimitExceededError,
    SwarmNotFoundError,
    ToolGenerationError,
    ToolNotFoundError,
    UnauthorizedError,
)
from nexus.infrastructure.di.container import Config, Container
from nexus.infrastructure.api.dependencies import get_container
from nexus.infrastructure.api.routes import chat, goals, memory, tools, system, swarm


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = Container()
    if container.config.json_logs:
        from nexus.infrastructure.adapters.observability.observability import configure_logging

        configure_logging(json_format=True)
    await container.start()
    app.state.container = container

    # The full subconscious coordinator (cortex events -> synthesis, patterns,
    # dreaming, and the subcortex loops) - built by the composition root so
    # handler subscriptions always match what the container wired.
    coordinator = container.subconscious
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

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        container = getattr(request.app.state, "container", None)
        metrics = getattr(container, "metrics", None)
        if metrics is None:
            return await call_next(request)
        started = time.perf_counter()
        try:
            return await call_next(request)
        finally:
            labels = {"route": request.url.path, "method": request.method}
            metrics.counter("http_requests_total", labels=labels)
            metrics.histogram("http_request_duration_seconds", time.perf_counter() - started, labels=labels)

    app.add_exception_handler(LLMUnavailableError, _handle_llm_unavailable)
    app.add_exception_handler(InvalidToolCallError, _handle_invalid_tool_call)
    app.add_exception_handler(ToolNotFoundError, _handle_not_found)
    app.add_exception_handler(GoalNotFoundError, _handle_not_found)
    app.add_exception_handler(AgentNotFoundError, _handle_not_found)
    app.add_exception_handler(SwarmNotFoundError, _handle_not_found)
    app.add_exception_handler(ConceptNotFoundError, _handle_not_found)
    app.add_exception_handler(MemoryNotFoundError, _handle_not_found)
    app.add_exception_handler(ToolGenerationError, _handle_tool_generation_error)
    app.add_exception_handler(UnauthorizedError, _handle_unauthorized)
    app.add_exception_handler(RateLimitExceededError, _handle_rate_limited)
    app.add_exception_handler(NexusError, _handle_nexus_error)
    app.add_exception_handler(Exception, _handle_unexpected)

    app.include_router(chat.router)
    app.include_router(goals.router)
    app.include_router(memory.router)
    app.include_router(swarm.router)
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

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    async def metrics(request: Request) -> Response:
        metrics_adapter = getattr(get_container(request), "metrics", None)
        if metrics_adapter is None:
            return Response(content="", media_type="text/plain")
        return Response(content=metrics_adapter.render(), media_type="text/plain; version=0.0.4")

    return app


async def _handle_llm_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "The LLM provider is temporarily unavailable."})


async def _handle_invalid_tool_call(request: Request, exc: InvalidToolCallError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_not_found(request: Request, exc: MemoryNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _handle_tool_generation_error(request: Request, exc: ToolGenerationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _handle_unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": "Invalid or missing credentials"})


async def _handle_rate_limited(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


async def _handle_nexus_error(request: Request, exc: NexusError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("nexus").exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app = create_app()
