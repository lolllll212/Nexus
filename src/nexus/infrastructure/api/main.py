"""
NEXUS FastAPI application - the conscious engine.

Run with:  uvicorn nexus.infrastructure.api.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus.infrastructure.di.container import Container
from nexus.infrastructure.api.routes import chat, memory, tools, system


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = Container()
    await container.start()
    app.state.container = container
    yield
    await container.shutdown()


app = FastAPI(
    title="NEXUS",
    description="A new kind of AI brain - conscious loop, subconscious synthesis, and dreaming.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
