"""Regression tests for REST auth middleware."""

from __future__ import annotations

import pytest
from fastapi.security import HTTPAuthorizationCredentials


@pytest.mark.asyncio
async def test_require_auth_accepts_generated_token(monkeypatch):
    """A valid REST token must not fail inside rate-limit plumbing."""
    from api import auth_middleware
    from scripts.config import mempool_config

    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSOCKET_SECRET_KEY", "test-rest-secret")
    monkeypatch.setattr(auth_middleware, "_auth_instance", None)
    monkeypatch.setattr(mempool_config, "_config", None)

    token = auth_middleware.generate_token("e2e-check", {"read"}, expires_in_hours=1)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    auth = await auth_middleware.require_auth(credentials)

    assert auth.client_id == "e2e-check"
    assert "read" in auth.permissions


@pytest.mark.asyncio
async def test_require_auth_development_mode_returns_complete_token(monkeypatch):
    from api import auth_middleware
    from scripts.config import mempool_config

    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("WEBSOCKET_SECRET_KEY", raising=False)
    monkeypatch.setattr(auth_middleware, "_auth_instance", None)
    monkeypatch.setattr(mempool_config, "_config", None)

    auth = await auth_middleware.require_auth(None)

    assert auth.token == "NO_AUTH_DEVELOPMENT_MODE"
    assert auth.client_id == "dev-client"
    assert "read" in auth.permissions
