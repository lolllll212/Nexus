from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from nexus.infrastructure.api.main import create_app
from tests.fakes.container import FakeContainer


def _dependency_names(dependant: object) -> set[str]:
    names: set[str] = set()
    for child in getattr(dependant, "dependencies", []):
        call = getattr(child, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", ""))
        names.update(_dependency_names(child))
    return names


def _route_operations(app: object) -> Iterator[tuple[APIRoute, str, str]]:
    def walk(routes: list[object]) -> Iterator[APIRoute]:
        for item in routes:
            if isinstance(item, APIRoute):
                yield item
            elif hasattr(item, "original_router"):
                yield from walk(item.original_router.routes)
            elif hasattr(item, "routes"):
                yield from walk(item.routes)

    for route in walk(getattr(app, "routes", [])):
        if not route.endpoint.__module__.startswith("nexus.infrastructure.api.routes."):
            continue
        for method in sorted(route.methods or set()):
            if method in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                path = route.path
                for parameter in route.param_convertors:
                    path = path.replace("{" + parameter + "}", "integration-test-id")
                yield route, method, path


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.state.container = FakeContainer()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_registered_api_routes_enforce_auth_or_document_public_status(client: TestClient) -> None:
    app = client.app
    operations = list(_route_operations(app))
    assert operations, "No routes registered from infrastructure.api.routes"

    for route, method, path in operations:
        response = client.request(method, path, json={} if method in {"POST", "PUT", "PATCH"} else None)
        dependencies = _dependency_names(route.dependant)
        requires_identity = bool({"require_identity", "require_admin"} & dependencies)

        if requires_identity:
            assert response.status_code == 401, (
                f"{method} {route.path} must reject unauthenticated requests; "
                f"got {response.status_code}: {response.text[:200]}"
            )
            continue

        declared_statuses = {int(code) for code in route.responses if str(code).isdigit()}
        declared_statuses.add(route.status_code or 200)
        assert response.status_code in declared_statuses, (
            f"Public route {method} {route.path} returned undocumented status "
            f"{response.status_code}; documented statuses: {sorted(declared_statuses)}"
        )
