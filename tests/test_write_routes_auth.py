"""Write routes of the legacy API require a token with the write permission (F-266)."""

from __future__ import annotations

import inspect
import sys

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Request body per write route for the 401/403 checks; the inventory test keeps this list complete.
WRITE_ROUTES = [
    ("post", "/api/v1/models/power-law/recalibrate", None),
    ("post", "/api/v1/models/ensemble", {"models": ["power_law"], "weights": [1.0]}),
    ("delete", "/api/v1/validation/rbn/cache", None),
]


def _requires_write(dependant) -> bool:
    """True when the dependency tree contains require_permission("write")."""
    for dep in dependant.dependencies:
        call = dep.call
        if getattr(call, "__name__", "") == "permission_checker":
            if inspect.getclosurevars(call).nonlocals.get("required_permission") == "write":
                return True
        if _requires_write(dep):
            return True
    return False


def _write_routes(app) -> dict[tuple[str, str], bool]:
    """Every registered (method, path) that writes, mapped to whether it requires write."""
    found = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods & WRITE_METHODS:
                found[(method, route.path)] = _requires_write(route.dependant)
    return found


@pytest.fixture
def client(monkeypatch, questdb_repo_mock):
    from scripts.config import mempool_config

    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSOCKET_SECRET_KEY", "test-write-secret")
    monkeypatch.setattr(mempool_config, "_config", None)
    # api.main imports the middleware as the top-level module; routers use api.auth_middleware.
    for name in ("auth_middleware", "api.auth_middleware"):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, "_auth_instance", None)

    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


def _token(permissions: set[str]) -> str:
    from api import auth_middleware

    return auth_middleware.generate_token("write-auth-test", permissions, expires_in_hours=1)


def _call(client, method, path, body, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))


def test_every_registered_write_route_requires_write():
    from api.main import app

    routes = _write_routes(app)
    assert [route for route, protected in routes.items() if not protected] == []
    assert set(routes) == {(method.upper(), path) for method, path, _ in WRITE_ROUTES}


def test_inventory_flags_an_unprotected_write_route():
    # Counterproof: a write route without the write dependency must be reported.
    from api.auth_middleware import require_permission

    app = FastAPI()

    @app.post("/protected")
    async def protected(_auth=Depends(require_permission("write"))):
        return {}

    @app.post("/read-only")
    async def read_only(_auth=Depends(require_permission("read"))):
        return {}

    @app.delete("/open")
    async def open_route():
        return {}

    assert _write_routes(app) == {
        ("POST", "/protected"): True,
        ("POST", "/read-only"): False,
        ("DELETE", "/open"): False,
    }


@pytest.mark.parametrize("method,path,body", WRITE_ROUTES)
def test_write_route_rejects_missing_token(client, method, path, body):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", WRITE_ROUTES)
def test_write_route_rejects_read_only_token(client, method, path, body):
    assert _call(client, method, path, body, _token({"read"})).status_code == 403


def test_write_token_reaches_the_handler(client, monkeypatch):
    cleared = []

    class FakeFetcher:
        def clear_cache(self, metric_id=None):
            cleared.append(metric_id)
            return 0

        async def close(self):
            return None

    import scripts.integrations.rbn_fetcher as rbn_fetcher

    monkeypatch.setattr(rbn_fetcher, "RBNFetcher", lambda: FakeFetcher())
    response = _call(
        client, "delete", "/api/v1/validation/rbn/cache", None, _token({"read", "write"})
    )
    assert response.status_code == 200
    assert cleared == [None]
