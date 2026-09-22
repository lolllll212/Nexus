"""FastAPI dependencies - shared request-scoped services.

Auth and rate limiting are enforced here as reusable dependencies. The API
layer derives Identity from the bearer token; a client-supplied user_id is
never trusted again.
"""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request

from nexus.domain.exceptions import QuotaExceededError, RateLimitExceededError, UnauthorizedError
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.di.container import Container


def get_container(request: Request) -> Container:
    """Return the single application-lifetime Container from app.state.

    The composition root is built once in the lifespan handler; every request
    reuses it instead of constructing fresh adapter connections.
    """
    return request.app.state.container


async def require_identity(request: Request) -> Identity:
    """Verify the bearer token and expose the caller's Identity."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    container = get_container(request)
    try:
        identity = await container.authenticator.authenticate(token)
    except UnauthorizedError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.state.identity = identity
    return identity


def require_rate_limit(kind: str) -> Callable[[Request], None]:
    """Enforce a per-identity sliding-window rate limit.

    Limits come from Container.config so tests (and ops) can tune them.
    """

    async def dependency(request: Request) -> None:
        container = get_container(request)
        cfg = getattr(container, "config", None)
        if kind == "chat":
            limit = getattr(cfg, "chat_rate_limit", 60) if cfg else 60
        else:
            limit = getattr(cfg, "tool_gen_rate_limit", 20) if cfg else 20
        window = getattr(cfg, "rate_limit_window_seconds", 60) if cfg else 60

        identity = getattr(request.state, "identity", None)
        key = identity.scope_key() if identity else "anonymous"
        try:
            await container.rate_limiter.check(key, limit, window)
        except RateLimitExceededError:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return dependency


def require_quota(resource: str) -> Callable[[Request], None]:
    """Enforce a per-tenant daily consumption quota for `resource`.

    Configured via NEXUS_QUOTA_* env vars (0 = unlimited). Fails with 429 once
    the tenant exhausts its allowance for the day.
    """

    async def dependency(request: Request) -> None:
        container = get_container(request)
        identity = getattr(request.state, "identity", None)
        tenant_id = identity.tenant_id if identity else "default"
        quota = getattr(container, "quota", None)
        if quota is None:
            return
        try:
            await quota.check(tenant_id, resource)
        except QuotaExceededError as exc:
            raise HTTPException(status_code=429, detail=str(exc))

    return dependency
