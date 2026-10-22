"""Secrets loading must never leave ciphertext in the environment nor fall back to a public key."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import auth_middleware
from api.config import is_encrypted, load_project_environment

ROOT = Path(__file__).resolve().parent.parent
# Real shapes, anonymised: SOPS dotenv values and dotenvx values.
SOPS_VALUE = "ENC[AES256_GCM,data:AAAAAAAA,iv:BBBBBBBB,tag:CCCCCCCC==,type:str]"
DOTENVX_VALUE = "encrypted:QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"


def _loader(values: dict[str, str]):
    def load(_path):
        os.environ.update(values)

    return load


def test_environment_wins_over_env_file(monkeypatch):
    monkeypatch.setenv("UTX_TEST_KEY", "from-environment")
    load_project_environment(_loader({"UTX_TEST_KEY": SOPS_VALUE}), None)
    assert os.environ["UTX_TEST_KEY"] == "from-environment"


def test_ciphertext_written_by_loader_is_dropped(monkeypatch, caplog):
    monkeypatch.delenv("UTX_TEST_WS", raising=False)
    monkeypatch.delenv("UTX_TEST_PLAIN", raising=False)
    dropped = load_project_environment(
        _loader({"UTX_TEST_WS": SOPS_VALUE, "UTX_TEST_PLAIN": "plain"}), None
    )
    assert "UTX_TEST_WS" in dropped
    assert "UTX_TEST_WS" not in os.environ
    assert os.environ["UTX_TEST_PLAIN"] == "plain"
    monkeypatch.delenv("UTX_TEST_PLAIN")
    # The log names the key and never carries the value.
    assert "UTX_TEST_WS" in caplog.text
    assert SOPS_VALUE not in caplog.text


def test_ciphertext_from_environment_is_dropped(monkeypatch):
    monkeypatch.setenv("UTX_TEST_JWT", DOTENVX_VALUE)
    dropped = load_project_environment(_loader({}), None)
    assert "UTX_TEST_JWT" in dropped
    assert "UTX_TEST_JWT" not in os.environ


@pytest.mark.parametrize("value", [SOPS_VALUE, DOTENVX_VALUE])
def test_is_encrypted_recognises_both_forms(value):
    assert is_encrypted(value)
    assert not is_encrypted("plain-secret")
    assert not is_encrypted(None)


def test_config_import_fails_closed_on_encrypted_jwt_secret():
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
    env["JWT_SECRET"] = DOTENVX_VALUE
    result = subprocess.run(
        [sys.executable, "-c", "import api.config"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr
    assert "still encrypted" in result.stderr
    assert DOTENVX_VALUE not in result.stderr


@pytest.mark.parametrize("key", [None, "", SOPS_VALUE, DOTENVX_VALUE])
def test_signing_key_fails_closed_when_auth_enabled(key):
    config = SimpleNamespace(websocket_secret_key=key, auth_enabled=True)
    with pytest.raises(ValueError, match="WEBSOCKET_SECRET_KEY"):
        auth_middleware._signing_key(config)


def test_signing_key_is_not_required_in_development_mode():
    config = SimpleNamespace(websocket_secret_key=None, auth_enabled=False)
    assert auth_middleware._signing_key(config) == ""


def test_signing_key_returns_plaintext_key():
    config = SimpleNamespace(websocket_secret_key="plain-key", auth_enabled=True)
    assert auth_middleware._signing_key(config) == "plain-key"


def test_app_startup_fails_closed_without_signing_key():
    env = {k: v for k, v in os.environ.items() if k != "WEBSOCKET_SECRET_KEY"}
    env["AUTH_ENABLED"] = "true"
    code = (
        "from fastapi.testclient import TestClient\n"
        "from api.main import app\n"
        "with TestClient(app):\n"
        "    pass\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "WEBSOCKET_SECRET_KEY" in result.stderr
