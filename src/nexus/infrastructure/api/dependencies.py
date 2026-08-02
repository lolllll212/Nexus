"""FastAPI dependencies - shared request-scoped services."""

from __future__ import annotations

from fastapi import Request

from nexus.infrastructure.di.container import Container


def get_container(request: Request) -> Container:
    """Return the single application-lifetime Container from app.state.

    The composition root is built once in the lifespan handler; every request
    reuses it instead of constructing fresh adapter connections.
    """
    return request.app.state.container
