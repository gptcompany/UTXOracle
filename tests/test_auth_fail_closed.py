"""REST authentication fails closed when its signing key is missing (F-238): no literal fallback, no silent start."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "valore-finto-di-test"


@pytest.fixture
def fresh_auth(monkeypatch):
    """Reset the config and auth singletons around each test."""
    from api import auth_middleware
    from scripts.config import mempool_config

    monkeypatch.setattr(auth_middleware, "_auth_instance", None)
    monkeypatch.setattr(mempool_config, "_config", None)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    return auth_middleware


@pytest.mark.parametrize("value", [None, "", "   "])
def test_startup_fails_when_the_key_is_missing_or_blank(fresh_auth, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("WEBSOCKET_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("WEBSOCKET_SECRET_KEY", value)

    with pytest.raises(fresh_auth.AuthConfigurationError) as raised:
        fresh_auth.get_auth_instance()

    assert "WEBSOCKET_SECRET_KEY" in str(raised.value)


def test_startup_succeeds_with_a_configured_key(fresh_auth, monkeypatch):
    monkeypatch.setenv("WEBSOCKET_SECRET_KEY", FAKE_KEY)

    auth = fresh_auth.get_auth_instance()

    assert auth.development_mode is False


def test_token_generation_also_refuses_a_missing_key(fresh_auth, monkeypatch):
    monkeypatch.delenv("WEBSOCKET_SECRET_KEY", raising=False)

    with pytest.raises(fresh_auth.AuthConfigurationError):
        fresh_auth.generate_token("monitoring-service", {"read"})


def test_development_mode_does_not_need_a_key_and_never_invents_one(
    fresh_auth, monkeypatch
):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("WEBSOCKET_SECRET_KEY", raising=False)

    auth = fresh_auth.get_auth_instance()

    assert auth.development_mode is True
    key_is_empty = (
        auth.authenticator.config.secret_key == ""
    )  # boolean: a failure must never echo the key
    assert key_is_empty


@pytest.mark.asyncio
async def test_api_lifespan_refuses_to_start_without_the_key(fresh_auth, monkeypatch):
    from api import main

    monkeypatch.delenv("WEBSOCKET_SECRET_KEY", raising=False)

    class _QuestDBMustNotBeReached:
        def __init__(self):
            raise AssertionError(
                "QuestDB was initialised before the authentication check"
            )

    monkeypatch.setattr(main, "QuestDBRepository", _QuestDBMustNotBeReached)

    with pytest.raises(fresh_auth.AuthConfigurationError):
        async with main.lifespan(main.app):
            pass


def test_no_python_file_falls_back_to_a_literal_secret():
    names = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    offenders = []
    for name in names.split():
        try:
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                literal = any(
                    isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value
                    for v in node.values
                )
                if literal and "secret" in ast.unparse(node.values[0]).lower():
                    offenders.append(f"{name}:{node.lineno}")
    assert offenders == []
