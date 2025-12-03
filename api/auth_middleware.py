#!/usr/bin/env python3
"""
FastAPI JWT Authentication Middleware
Task T036a-b: REST API Authentication

Provides JWT authentication for FastAPI endpoints using the same
authentication system as WebSocket connections.

Security features:
- Bearer token validation
- Permission-based access control
- Rate limiting per client
- Development mode bypass
- Exception handling
"""

import logging
from typing import Optional, Set, Callable
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sys
from pathlib import Path

# Add scripts to path for WebSocketAuthenticator import
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.auth.websocket_auth import WebSocketAuthenticator, AuthToken, AuthConfig
from scripts.config.mempool_config import get_config

logger = logging.getLogger(__name__)

# Initialize security scheme
security = HTTPBearer(auto_error=False)


class RestApiAuth:
    """
    REST API authentication using JWT tokens

    Reuses WebSocketAuthenticator for consistency across the system.

    Example:
        from api.auth_middleware import require_auth, require_permission

        @app.get("/api/protected")
        async def protected_endpoint(auth: AuthToken = Depends(require_auth)):
            return {"client_id": auth.client_id}

        @app.post("/api/admin")
        async def admin_endpoint(auth: AuthToken = Depends(require_permission("write"))):
            return {"message": "Admin action performed"}
    """

    def __init__(self):
        """Initialize REST API auth with WebSocketAuthenticator"""
        mempool_config = get_config()

        # Create AuthConfig from MempoolConfig
        auth_config = AuthConfig(
            secret_key=mempool_config.websocket_secret_key
            or "dev-secret-key-change-me",
            enabled=mempool_config.auth_enabled,
        )

        self.authenticator = WebSocketAuthenticator(auth_config)
        self.development_mode = not auth_config.enabled

        if self.development_mode:
            logger.warning("⚠️  REST API authentication DISABLED (development mode)")
        else:
            logger.info("✅ REST API authentication ENABLED (JWT required)")

    def validate_token(self, token: str) -> Optional[AuthToken]:
        """
        Validate JWT token

        Args:
            token: JWT token string

        Returns:
            AuthToken if valid, None otherwise
        """
        return self.authenticator.validate_token(token)

    def check_rate_limit(self, client_id: str) -> bool:
        """
        Check if client is within rate limit

        Args:
            client_id: Client identifier

        Returns:
            True if within limit, False if exceeded
        """
        return self.authenticator.check_rate_limit(client_id)


# Global auth instance
_auth_instance: Optional[RestApiAuth] = None


def get_auth_instance() -> RestApiAuth:
    """Get or create global auth instance (singleton)"""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = RestApiAuth()
    return _auth_instance


# =============================================================================
# FastAPI Dependencies
# =============================================================================


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthToken:
    """
    Require valid JWT authentication

    Use as FastAPI dependency to protect endpoints.

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        AuthToken with client_id and permissions

    Raises:
        HTTPException: 401 if auth fails, 429 if rate limited

    Example:
        @app.get("/api/protected")
        async def endpoint(auth: AuthToken = Depends(require_auth)):
            return {"client": auth.client_id}
    """
    auth = get_auth_instance()

    # Development mode bypass
    if auth.development_mode:
        logger.debug("Auth bypass (development mode)")
        return AuthToken(
            client_id="dev-client",
            expires_at=None,
            permissions={"read", "write"},
            issued_at=None,
        )

    # Check if credentials provided
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token
    token = auth.validate_token(credentials.credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check rate limit
    if not auth.check_rate_limit(token.client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )

    logger.debug(f"Authenticated: {token.client_id} ({token.permissions})")
    return token


def require_permission(required_permission: str) -> Callable:
    """
    Require specific permission

    Factory function that returns a dependency for permission checking.

    Args:
        required_permission: Permission required (e.g., "read", "write")

    Returns:
        Dependency function for FastAPI

    Example:
        @app.post("/api/admin")
        async def admin_endpoint(auth: AuthToken = Depends(require_permission("write"))):
            return {"message": "Admin action"}
    """

    async def permission_checker(auth: AuthToken = Depends(require_auth)) -> AuthToken:
        """Check if client has required permission"""
        if required_permission not in auth.permissions:
            logger.warning(
                f"Permission denied: {auth.client_id} lacks '{required_permission}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: '{required_permission}'",
            )
        return auth

    return permission_checker


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthToken]:
    """
    Optional authentication (doesn't require token)

    Use for endpoints that work differently for authenticated/unauthenticated users.

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        AuthToken if provided and valid, None otherwise

    Example:
        @app.get("/api/data")
        async def endpoint(auth: Optional[AuthToken] = Depends(optional_auth)):
            if auth:
                # Authenticated - return more data
                return {"data": "full", "client": auth.client_id}
            else:
                # Unauthenticated - return limited data
                return {"data": "limited"}
    """
    auth = get_auth_instance()

    # Development mode
    if auth.development_mode:
        return AuthToken(
            client_id="dev-client",
            expires_at=None,
            permissions={"read", "write"},
            issued_at=None,
        )

    # No credentials provided - this is OK for optional auth
    if not credentials:
        return None

    # Validate token
    token = auth.validate_token(credentials.credentials)
    if not token:
        # Invalid token - log warning but don't fail
        logger.warning("Invalid token in optional_auth (ignored)")
        return None

    # Check rate limit
    if not auth.check_rate_limit(token.client_id):
        logger.warning(f"Rate limit exceeded: {token.client_id} (optional_auth)")
        return None

    return token


# =============================================================================
# Token Generation Helper
# =============================================================================


def generate_token(
    client_id: str,
    permissions: Optional[Set[str]] = None,
    expires_in_hours: int = 24,
) -> str:
    """
    Generate JWT token for client

    Helper function for creating tokens (e.g., for CLI tools, tests).

    Args:
        client_id: Client identifier
        permissions: Set of permissions (default: {"read"})
        expires_in_hours: Token validity in hours (default: 24)

    Returns:
        JWT token string

    Example:
        token = generate_token("monitoring-service", {"read"}, expires_in_hours=168)
        # Use this token in Authorization: Bearer <token> header
    """
    # Create custom auth config with desired expiry
    mempool_config = get_config()
    auth_config = AuthConfig(
        secret_key=mempool_config.websocket_secret_key or "dev-secret-key-change-me",
        token_expiry_hours=expires_in_hours,
        enabled=mempool_config.auth_enabled,
    )

    authenticator = WebSocketAuthenticator(auth_config)
    return authenticator.generate_token(
        client_id=client_id, permissions=permissions or {"read"}
    )


# =============================================================================
# Testing and CLI Utilities
# =============================================================================

if __name__ == "__main__":
    """CLI for generating tokens"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate JWT tokens for REST API")
    parser.add_argument("client_id", help="Client identifier (e.g., 'dashboard-1')")
    parser.add_argument(
        "--permissions",
        nargs="+",
        default=["read"],
        choices=["read", "write"],
        help="Permissions to grant (default: read)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Token validity in hours (default: 24)",
    )

    args = parser.parse_args()

    # Generate token
    token = generate_token(
        client_id=args.client_id,
        permissions=set(args.permissions),
        expires_in_hours=args.hours,
    )

    print("\n" + "=" * 80)
    print("✅ JWT Token Generated")
    print("=" * 80)
    print(f"\nClient ID: {args.client_id}")
    print(f"Permissions: {', '.join(args.permissions)}")
    print(f"Expires in: {args.hours} hours")
    print("\nToken:")
    print(f"\n{token}\n")
    print("=" * 80)
    print("\nUsage in HTTP requests:")
    print(
        f'  curl -H "Authorization: Bearer {token}" http://localhost:8000/api/prices/latest'
    )
    print("\nUsage in Python:")
    print(f'  headers = {{"Authorization": "Bearer {token}"}}')
    print(
        '  response = requests.get("http://localhost:8000/api/prices/latest", headers=headers)'
    )
    print("=" * 80 + "\n")
