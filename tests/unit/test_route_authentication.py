"""Comprehensive test asserting that all sensitive API routes enforce authentication (401 without key)."""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from nexus.infrastructure.api.main import create_app
from tests.fakes.container import TEST_API_KEY_1, TEST_API_KEY_2, FakeContainer

EXEMPT_PUBLIC_ROUTES = {
    "/healthz",
    "/readyz",
    "/",
    "/metrics",
    "/dashboard",
    "/v1/system/health",
    "/api/integrations/github/webhook",
    "/api/integrations/gmail/webhook",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/docs/oauth2-redirect",
}


def _collect_all_routes(router_or_routes):
    routes = []
    items = (
        router_or_routes if isinstance(router_or_routes, list) else getattr(router_or_routes, "routes", [])
    )
    for r in items:
        if isinstance(r, APIRoute):
            routes.append(r)
        elif hasattr(r, "original_router"):
            routes.extend(_collect_all_routes(r.original_router))
        elif hasattr(r, "routes"):
            routes.extend(_collect_all_routes(r.routes))
    return routes


@pytest.fixture
def auth_test_client():
    app = create_app()
    fake = FakeContainer()
    app.state.container = fake
    client = TestClient(app)
    return client, app


def test_public_probes_do_not_require_auth(auth_test_client):
    """Verify health, ready, and metric probes are accessible without authentication."""
    client, _ = auth_test_client
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code in (200, 503)
    assert client.get("/v1/system/health").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_every_sensitive_route_returns_401_without_key(auth_test_client):
    """Assert every protected API route in the application rejects unauthenticated requests with 401."""
    client, app = auth_test_client
    all_routes = _collect_all_routes(app)

    tested_count = 0
    for route in all_routes:
        path = route.path
        if path in EXEMPT_PUBLIC_ROUTES:
            continue

        # Replace standard path parameters with dummy placeholders
        resolved_path = (
            path.replace("{goal_id}", "g-test-1")
            .replace("{concept_id}", "c-test-1")
            .replace("{agent_id}", "a-test-1")
            .replace("{swarm_id}", "s-test-1")
            .replace("{example_id}", "e-test-1")
            .replace("{workflow_id}", "w-test-1")
        )

        methods = [m for m in route.methods if m in ("GET", "POST", "PUT", "DELETE")]
        for method in methods:
            client_fn = getattr(client, method.lower())
            call_kwargs = {"json": {}} if method in ("POST", "PUT") else {}

            # Request with NO Authorization header
            res_unauth = client_fn(resolved_path, **call_kwargs)
            assert res_unauth.status_code == 401, (
                f"Security regression: {method} {path} returned {res_unauth.status_code} "
                f"instead of 401 Unauthorized without bearer token"
            )

            # Request WITH valid Authorization header should not be 401
            res_auth = client_fn(
                resolved_path,
                headers={"Authorization": f"Bearer {TEST_API_KEY_1}"},
                **call_kwargs,
            )
            assert (
                res_auth.status_code != 401
            ), f"Authentication failed: {method} {path} returned 401 with valid key"

            tested_count += 1

    # Ensure a significant number of endpoints were verified
    assert tested_count >= 50, f"Expected to verify at least 50 endpoints, verified {tested_count}"


def test_admin_routes_reject_non_admin_role_with_403(auth_test_client):
    """Assert admin-only routes reject standard user identities with 403 Forbidden."""
    client, _ = auth_test_client

    admin_endpoints = [
        ("POST", "/v1/system/dream", {}),
        ("POST", "/v1/system/self-heal", {}),
        ("POST", "/api/nim/configure", {"model": "test-model"}),
        ("POST", "/v1/goals/approvals/grant", {"action": "test_action"}),
        ("POST", "/api/autonomy/approvals/grant", {"action": "test_action"}),
    ]

    for method, path, body in admin_endpoints:
        fn = getattr(client, method.lower())
        res = fn(
            path,
            json=body,
            headers={"Authorization": f"Bearer {TEST_API_KEY_2}"},  # Role: user
        )
        assert res.status_code == 403, (
            f"Expected {method} {path} to return 403 Forbidden for non-admin, "
            f"got {res.status_code}: {res.text}"
        )

