"""Write routes of the legacy API require a token with the write permission (F-266)."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

WRITE_ROUTES = [
    ("post", "/api/v1/models/power-law/recalibrate", None),
    ("post", "/api/v1/models/ensemble", {"models": ["power_law"], "weights": [1.0]}),
    ("delete", "/api/v1/validation/rbn/cache", None),
]


@pytest.fixture
def client(monkeypatch):
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
