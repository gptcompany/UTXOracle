"""Revocation in WebSocketAuthenticator (F-277): a revoked token must stop validating."""

from datetime import datetime, timedelta, timezone

from scripts.auth.websocket_auth import AuthConfig, WebSocketAuthenticator

# Fixture key, not a credential: tokens never leave the test.
KEY = "test-only-key-for-revocation"


def _auth(hours: int = 24) -> WebSocketAuthenticator:
    return WebSocketAuthenticator(AuthConfig(secret_key=KEY, token_expiry_hours=hours))


def test_revoked_token_no_longer_validates():
    auth = _auth()
    token = auth.generate_token("dashboard-1")
    assert auth.validate_token(token) is not None

    assert auth.revoke_token("dashboard-1") is True
    assert auth.validate_token(token) is None
    # A revoked token cannot be traded for a fresh one either.
    assert auth.refresh_token(token) is None


def test_revocation_covers_tokens_issued_by_another_instance():
    # api/auth_middleware.generate_token issues tokens from a separate
    # authenticator (CLI, any lifetime): the validating instance never saw them.
    issuer, server = _auth(hours=168), _auth()
    token = issuer.generate_token("monitoring-service")
    assert server.validate_token(token) is not None

    assert server.revoke_token("monitoring-service") is False  # not in this instance's active set
    assert server.validate_token(token) is None


def test_token_issued_after_revocation_is_valid():
    auth = _auth()
    old = auth.generate_token("dashboard-1")
    auth.revoke_token("dashboard-1")
    new = auth.generate_token("dashboard-1")

    assert auth.validate_token(old) is None
    assert auth.validate_token(new) is not None


def test_revocation_is_per_client():
    auth = _auth()
    kept = auth.generate_token("dashboard-2")
    auth.generate_token("dashboard-1")
    auth.revoke_token("dashboard-1")

    assert auth.validate_token(kept) is not None


def test_cleanup_keeps_revocations_for_tokens_still_alive():
    # Expired active tokens are pruned, the revocation cutoff is not: an
    # out-of-process token with a longer lifetime would otherwise come back.
    auth = _auth()
    token = _auth(hours=168).generate_token("monitoring-service")
    auth.revoke_token("monitoring-service")
    auth.generate_token("other")
    auth.active_tokens["other"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    auth.cleanup_expired_tokens()

    assert "other" not in auth.active_tokens
    assert auth.validate_token(token) is None
