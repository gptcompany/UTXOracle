#!/usr/bin/env python3
"""Mint a consumer JWT for /v1/streams/health and other /v1/* surfaces.

Uses the same JWT_SECRET load path as api/config.py so tokens emitted here
validate against the running utxoracle-api.service.

Usage:
    uv run python -m scripts.auth.mint_consumer_token \\
        --client-id nautilus-dev-prod \\
        --permissions read \\
        --ttl-hours 8760    # 1 year

    uv run python -m scripts.auth.mint_consumer_token --client-id smoke --ttl-hours 1

Exit code 0 on success; the token is printed to stdout (single line, no prefix).
JWT_SECRET decryption errors fail with exit code 2 and a descriptive message
on stderr — no token is ever printed in an error path.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def mint(client_id: str, permissions: list[str], ttl_hours: int) -> str:
    """Mint via the same WebSocketAuthenticator the running API uses.

    The authenticator resolves the secret via this chain:
      1. $WEBSOCKET_SECRET_KEY env (preferred — production)
      2. WEBSOCKET_SECRET_KEY= line in <project>/.env
      3. fallback to "dev-secret-key-change-me" if neither found

    Whatever the running API resolved at startup is what we resolve here.
    The token's `expiry_hours` is read from MempoolConfig (env-driven), so we
    monkeypatch it to honour the operator-provided --ttl-hours.
    """
    from api.auth_middleware import RestApiAuth

    auth = RestApiAuth()
    # The authenticator carries its own AuthConfig; override expiry for this mint only.
    auth.authenticator.config.token_expiry_hours = ttl_hours
    token = auth.authenticator.generate_token(
        client_id=client_id,
        permissions=set(permissions),
    )
    # generate_token returns AuthToken (with .token attr) on newer paths,
    # or raw JWT string on older paths. Normalise.
    return getattr(token, "token", token)


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
        default=["read"],
        help="Permission scopes (default: read).",
    )
    parser.add_argument(
        "--ttl-hours",
        type=int,
        default=24 * 365,
        help="Token validity window in hours (default: 8760 = 1 year).",
    )
    args = parser.parse_args()

    try:
        token = mint(args.client_id, list(args.permissions), args.ttl_hours)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(token + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
