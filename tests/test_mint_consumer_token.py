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


# The project root is redirected to a temporary directory before anything reads the environment;
# the external secrets provider is disabled so the host cannot change the outcome.
_PREAMBLE = (
    "import sys, pathlib\n"
    "sys.modules['secrets_loader'] = None\n"
    "import api.project_env as p\n"
    "p._PROJECT_ROOT = pathlib.Path(sys.argv[1])\n"
)
_CLI_DRIVER = (
    _PREAMBLE
    + "sys.argv = ['mint', '--client-id', 'cli-test', '--ttl-hours', '1']\n"
    + "from scripts.auth.mint_consumer_token import main\n"
    + "raise SystemExit(main())\n"
)
_API_DRIVER = (
    _PREAMBLE
    + "import api.config\n"
    + "from scripts.config.mempool_config import get_config\n"
    + "print(get_config().auth_enabled)\n"
)
PLAIN_KEY = "synthetic-rest-key"


def _run_driver(code, tmp_path, dotenv: str | None, auth_enabled: str | None):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    if dotenv is not None:
        (root / ".env").write_text(f"AUTH_ENABLED={dotenv}\n")
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("JWT_SECRET", "WEBSOCKET_SECRET_KEY", "AUTH_ENABLED")
    }
    env.update(
        {
            "WEBSOCKET_SECRET_KEY": PLAIN_KEY,
            "JWT_SECRET": "synthetic-jwt-secret",
            "HOME": str(tmp_path),
        }
    )
    if auth_enabled is not None:
        env["AUTH_ENABLED"] = auth_enabled
    return subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_mint_honours_auth_disabled_only_in_dotenv(tmp_path):
    # The API reads .env (api/config.py); a CLI that skipped it would mint while the API is open.
    result = _run_driver(_CLI_DRIVER, tmp_path, dotenv="false", auth_enabled=None)
    assert result.returncode == 2, result.stderr[-500:]
    assert result.stdout == ""
    assert PLAIN_KEY not in result.stderr
    assert "NO_AUTH" not in result.stderr


@pytest.mark.parametrize(
    ("dotenv", "auth_enabled"),
    [
        ("false", None),
        ("true", None),
        (None, "false"),
        (None, "true"),
        ("true", "false"),
        ("false", "true"),
    ],
)
def test_api_and_cli_resolve_the_same_auth_flag(tmp_path, dotenv, auth_enabled):
    api = _run_driver(_API_DRIVER, tmp_path, dotenv, auth_enabled)
    assert api.returncode == 0, api.stderr[-500:]
    cli = _run_driver(_CLI_DRIVER, tmp_path, dotenv, auth_enabled)
    api_enabled = api.stdout.strip() == "True"
    # The CLI mints (rc 0, a JWT) exactly when the API has auth on, and refuses otherwise.
    assert cli.returncode == (0 if api_enabled else 2), cli.stderr[-500:]
    assert (cli.stdout.strip() != "") == api_enabled
