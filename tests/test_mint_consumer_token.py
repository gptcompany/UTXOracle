"""The consumer token CLI must fail closed on a missing or still-encrypted signing key (F-215)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOPS_VALUE = "ENC[AES256_GCM,data:AAAAAAAA,iv:BBBBBBBB,tag:CCCCCCCC==,type:str]"
DOTENVX_VALUE = "encrypted:QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"


def _mint(
    tmp_path, key: str, auth_enabled: str | None = "true"
) -> subprocess.CompletedProcess:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("JWT_SECRET", "WEBSOCKET_SECRET_KEY", "AUTH_ENABLED")
    }
    env.update({"WEBSOCKET_SECRET_KEY": key, "HOME": str(tmp_path)})
    if auth_enabled is not None:
        env["AUTH_ENABLED"] = auth_enabled
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.auth.mint_consumer_token",
            "--client-id",
            "cli-test",
            "--ttl-hours",
            "1",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("key", ["", SOPS_VALUE, DOTENVX_VALUE])
def test_mint_fails_closed_without_plaintext_key(tmp_path, key):
    result = _mint(tmp_path, key)
    assert result.returncode == 2, result.stderr[-500:]
    assert result.stdout == ""
    assert "WEBSOCKET_SECRET_KEY" in result.stderr
    assert key not in result.stderr or key == ""


def test_mint_prints_a_jwt_with_a_plaintext_key(tmp_path):
    result = _mint(tmp_path, "synthetic-rest-key")
    assert result.returncode == 0, result.stderr[-500:]
    assert len(result.stdout.strip().split(".")) == 3


@pytest.mark.parametrize(
    ("key", "auth_enabled"),
    [
        ("", "false"),
        (SOPS_VALUE, "false"),
        (DOTENVX_VALUE, "false"),
        ("synthetic-rest-key", "false"),
        # Absent: the config default is true, so an unusable key must still stop the mint.
        ("", None),
        (SOPS_VALUE, None),
    ],
)
def test_mint_never_prints_a_token_unless_auth_is_enabled(tmp_path, key, auth_enabled):
    # AUTH_ENABLED=false makes the authenticator return a NO_AUTH placeholder with rc 0 (F-215).
    result = _mint(tmp_path, key, auth_enabled)
    assert result.returncode == 2, result.stderr[-500:]
    assert result.stdout == ""
    assert "NO_AUTH" not in result.stderr
    assert key not in result.stderr or key == ""
