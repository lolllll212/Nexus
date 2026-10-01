"""FastAPI dependencies - shared request-scoped services.

Auth and rate limiting are enforced here as reusable dependencies. The API
layer derives Identity from the bearer token; a client-supplied user_id is
never trusted again.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from nexus.domain.exceptions import QuotaExceededError, RateLimitExceededError, UnauthorizedError
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.di.container import Container


def get_container(request: Request) -> Container:
    """Return the application-lifetime Container from app.state, creating lazily if needed."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        container = Container()
        request.app.state.container = container
    return container


async def require_identity(conn: HTTPConnection) -> Identity:
    """Verify the bearer token or X-API-Key and expose the caller's Identity.

    Works for both HTTP Requests and WebSockets.
    """
    auth = conn.headers.get("Authorization", "")
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    elif "x-api-key" in conn.headers:
        token = conn.headers["x-api-key"].strip()

    if not token:
        # GitHub sends its HMAC in a header and does not support bearer auth.
        # Keep this exception exact so arbitrary WebSocket or webhook paths do
        # not become unauthenticated service endpoints.
        if conn.url.path == "/api/integrations/github/webhook" and conn.headers.get("x-hub-signature-256"):
            from nexus.domain.value_objects.identity import Role

            identity = Identity(
                user_id="service",
                tenant_id="default",
                role=Role.SERVICE,
                display_name="Service Connection",
            )
            conn.state.identity = identity
            return identity
        raise HTTPException(status_code=401, detail="Missing bearer token")

    container = getattr(conn.app.state, "container", None)
    if container is None:
        container = Container()
        conn.app.state.container = container
    try:
        identity = await container.authenticator.authenticate(token)
    except UnauthorizedError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    conn.state.identity = identity
    return identity


async def require_admin(conn: HTTPConnection) -> Identity:
    """Enforce that the caller has ADMIN role."""
    from nexus.domain.value_objects.identity import Role

    identity = await require_identity(conn)
    role_val = getattr(identity.role, "value", identity.role)
    is_admin = identity.role == Role.ADMIN or str(role_val).lower() == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: Admin privileges required")
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
