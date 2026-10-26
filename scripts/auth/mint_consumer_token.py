#!/usr/bin/env python3
"""Mint a consumer JWT for /v1/streams/health and other /v1/* surfaces.

Signs with WEBSOCKET_SECRET_KEY, the REST signing key api/auth_middleware.py uses, after loading
the project environment exactly as the API does (api/project_env.py), so tokens emitted here
validate against the running utxoracle-api.service.

Usage (from the repository root):
    uv run python -m scripts.auth.mint_consumer_token \\
        --client-id nautilus-dev-prod --permissions read --ttl-hours 720

--ttl-hours must be between 1 and 8760 (default 720 = 30 days): tokens cannot be revoked
persistently, so the default stays short.

Exit code 0 on success; the token is printed to stdout (single line, no prefix).
Any failure (missing or still-encrypted signing key, AUTH_ENABLED not true, invalid arguments)
exits 2 with a message on stderr and nothing on stdout; no token is ever printed in an error path.
"""

from __future__ import annotations

import argparse
import sys

MAX_TTL_HOURS = 8760
DEFAULT_TTL_HOURS = 720
# The permissions the REST routes check (require_permission) and api/auth_middleware.py's CLI accepts.
PERMISSIONS = ("read", "write")


def mint(client_id: str, permissions: list[str], ttl_hours: int) -> str:
    """Mint through api.auth_middleware.generate_token, which fails closed on the signing key."""
    from api.project_env import load_environment

    # Same environment as the API (.env included), before the config is read: otherwise
    # AUTH_ENABLED=false set only in .env would leave the API open while the CLI mints.
    load_environment()

    from api.auth_middleware import generate_token, get_config

    if not get_config().auth_enabled:
        # With auth disabled the authenticator returns a placeholder instead of a JWT.
        raise RuntimeError("AUTH_ENABLED must be true to mint a token")
    return generate_token(client_id, set(permissions), expires_in_hours=ttl_hours)


def _ttl_hours(value: str) -> int:
    hours = int(value)
    if not 1 <= hours <= MAX_TTL_HOURS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_TTL_HOURS}")
    return hours


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mint a consumer JWT for /v1/* endpoints"
    )
    parser.add_argument(
        "--client-id",
        required=True,
        help="Stable client identifier (e.g. nautilus-dev-prod). Logged on every request.",
    )
    parser.add_argument(
        "--permissions",
        nargs="+",
        choices=PERMISSIONS,
        default=["read"],
        help="Permission scopes (default: read).",
    )
    parser.add_argument(
        "--ttl-hours",
        type=_ttl_hours,
        default=DEFAULT_TTL_HOURS,
        help=f"Token validity in hours, 1..{MAX_TTL_HOURS} (default: {DEFAULT_TTL_HOURS}).",
    )
    args = parser.parse_args()

    try:
        token = mint(args.client_id, args.permissions, args.ttl_hours)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure is rc 2, never a token
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(token + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
