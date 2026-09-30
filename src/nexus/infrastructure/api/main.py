"""
NEXUS FastAPI application - the conscious engine.

Run with:  uvicorn nexus.infrastructure.api.main:app --reload
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

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
from nexus.infrastructure.api.dependencies import get_container
from nexus.infrastructure.api.routes import (
    analyze,
    audio,
    chat,
    coding,
    coding_assistant,
    goals,
    graph,
    integrations,
    mcp,
    memory,
    multimodal,
    nim,
    research,
    swarm,
    system,
    telemetry,
    tools,
    workflows,
)
from nexus.infrastructure.di.container import Config, Container


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = getattr(app.state, "container", None)
    owns_container = False
    if container is None:
        container = Container()
        owns_container = True
        if container.config.json_logs:
            from nexus.infrastructure.adapters.observability.observability import configure_logging

            configure_logging(json_format=True)
        await container.start()
        app.state.container = container

        coordinator = container.subconscious
        await coordinator.start()
        app.state.coordinator = coordinator

    yield

    if owns_container:
        coordinator = getattr(app.state, "coordinator", None)
        if coordinator:
            try:
                await coordinator.stop()
            except Exception:
                pass
        await container.shutdown()


def create_app(config: Config | None = None) -> FastAPI:
    app = FastAPI(
        title="NEXUS",
        description="A new kind of AI brain - conscious loop, subconscious synthesis, and dreaming.",
        version="0.1.0",
        lifespan=lifespan,
    )

    cfg = config or Config()
    cors_origins = list(cfg.cors_origins) if cfg.cors_origins else ["*"]
    # Per CORS standard and security best practices: reject wildcard CORS when credentials are enabled
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        started = time.perf_counter()

        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"

            container = getattr(request.app.state, "container", None)
            metrics = getattr(container, "metrics", None) if container else None
            if metrics is not None:
                labels = {"route": request.url.path, "method": request.method}
                metrics.counter("http_requests_total", labels=labels)
                metrics.histogram("http_request_duration_seconds", elapsed_ms / 1000.0, labels=labels)

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
    app.include_router(goals.autonomy_router)
    app.include_router(memory.router)
    app.include_router(swarm.router)
    app.include_router(tools.router)
    app.include_router(system.router)
    app.include_router(coding.router)
    app.include_router(graph.router)
    app.include_router(analyze.router)
    app.include_router(nim.router)
    app.include_router(integrations.router)
    app.include_router(research.router)
    app.include_router(workflows.router)
    app.include_router(audio.router)
    app.include_router(telemetry.router)
    app.include_router(coding_assistant.router)
    app.include_router(multimodal.router)
    app.include_router(mcp.router)

    @app.api_route("/healthz", methods=["GET", "HEAD"], tags=["meta"], include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok", "service": "NEXUS Cortex", "timestamp": time.time()}

    @app.api_route("/readyz", methods=["GET", "HEAD"], tags=["meta"], include_in_schema=False)
    async def readyz(request: Request) -> Response:
        container = getattr(request.app.state, "container", None)
        if container is None:
            return JSONResponse(status_code=503, content={"status": "initializing", "healthy": False})

        checks = {"container": True}
        try:
            tools = await container.tool_registry.list_all()
            checks["tools"] = len(tools) > 0
        except Exception:
            checks["tools"] = False

        nim = getattr(container, "nim_provider", None)
        checks["nim_configured"] = nim is not None
        checks["backend"] = os.getenv("NEXUS_INFRA_BACKEND", "memory")

        all_ready = checks["container"] and checks["tools"]
        status_code = 200 if all_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if all_ready else "degraded", "checks": checks},
        )

    # Resolve frontend directory for static serving and root HTML
    from pathlib import Path as _FrontendPath

    _frontend_dir = _FrontendPath(__file__).resolve().parents[4] / "frontend"
    if not _frontend_dir.exists():
        _frontend_dir = _FrontendPath("frontend")
    _target_dir = _frontend_dir

    @app.get("/", tags=["meta"], include_in_schema=False)
    async def root(request: Request) -> Response:
        accept = request.headers.get("accept", "")
        index_file = _target_dir / "index.html"
        if index_file.exists() and ("text/html" in accept or "application/json" not in accept):
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return JSONResponse(
            {
                "name": "NEXUS",
                "tagline": "a new kind of brain",
                "version": "0.1.0",
                "conscious_loop": "/v1/chat",
                "subconscious": "/v1/system/dream",
            }
        )

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        metrics_adapter = getattr(get_container(request), "metrics", None)
        if metrics_adapter is not None:
            rendered = metrics_adapter.render()
            if rendered:
                return Response(content=rendered, media_type="text/plain; version=0.0.4")
        from nexus.infrastructure.api.routes.telemetry import generate_prometheus_metrics

        text = await generate_prometheus_metrics(get_container(request))
        return Response(content=text, media_type="text/plain; version=0.0.4")

    @app.get("/dashboard", tags=["meta"], include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        from pathlib import Path

        dashboard_path = Path(__file__).parent / "static" / "dashboard.html"
        content = dashboard_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)

    # Serve the frontend (Second Brain OS / HOLO) — mounted last so /v1/* API routes take precedence
    if _target_dir.exists():
        app.mount("/", StaticFiles(directory=str(_target_dir), html=True), name="frontend")

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
