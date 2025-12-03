"""
JWT Authentication module for Whale Detection Dashboard.
Tasks T009-T012: JWT token generation, validation, refresh mechanism.
"""

import jwt
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.config import (
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRY_HOURS,
    JWT_REFRESH_MINUTES,
    setup_logging,
)

# Set up module logger
logger = setup_logging(__name__)

# Bearer token security scheme
security = HTTPBearer()


class JWTAuthManager:
    """JWT authentication manager for whale dashboard."""

    def __init__(self):
        self.secret = JWT_SECRET
        self.algorithm = JWT_ALGORITHM
        self.expiry_hours = JWT_EXPIRY_HOURS
        self.refresh_minutes = JWT_REFRESH_MINUTES
        logger.info("JWT auth manager initialized")

    def generate_token(self, user_id: str, permissions: list = None) -> Dict[str, Any]:
        """
        Generate JWT token with 1-hour expiry.
        Task T009: Create JWT token generator.

        Args:
            user_id: Unique user identifier
            permissions: List of user permissions

        Returns:
            Dictionary with token and metadata
        """
        permissions = permissions or ["whale_view"]
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=self.expiry_hours)

        payload = {
            "user_id": user_id,
            "exp": expiry.timestamp(),
            "iat": now.timestamp(),
            "permissions": permissions,
            "jti": f"{user_id}-{int(now.timestamp())}",  # JWT ID for tracking
        }

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)

        logger.info(f"Generated token for user: {user_id}")

        return {
            "token": token,
            "expires_at": expiry.isoformat(),
            "expires_in": self.expiry_hours * 3600,
            "token_type": "Bearer",
        }

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token.
        Task T010: Implement token validation middleware.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])

            # Check if token is expired (redundant but explicit)
            exp_timestamp = payload.get("exp", 0)
            if time.time() > exp_timestamp:
                raise HTTPException(status_code=401, detail="Token has expired")

            logger.debug(f"Token validated for user: {payload.get('user_id')}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid token")

    def should_refresh(self, token: str) -> bool:
        """
        Check if token should be refreshed (5 minutes before expiry).
        Task T012: Add token refresh mechanism.

        Args:
            token: JWT token string

        Returns:
            True if token should be refreshed
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # Don't fail if expired
            )

            exp_timestamp = payload.get("exp", 0)
            refresh_threshold = exp_timestamp - (self.refresh_minutes * 60)

            return time.time() > refresh_threshold

        except jwt.InvalidTokenError:
            return False

    def refresh_token(self, old_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh token if it's within refresh window.
        Task T012: Token refresh mechanism.

        Args:
            old_token: Current JWT token

        Returns:
            New token if refresh successful, None otherwise
        """
        try:
            # Decode without verification to get user info
            payload = jwt.decode(
                old_token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_exp": False},
            )

            # Check if token is within refresh window
            exp_timestamp = payload.get("exp", 0)
            now = time.time()

            # Only refresh if within 5 minutes of expiry but not yet expired
            refresh_start = exp_timestamp - (self.refresh_minutes * 60)

            if refresh_start <= now <= exp_timestamp:
                # Generate new token with same permissions
                return self.generate_token(
                    user_id=payload.get("user_id"),
                    permissions=payload.get("permissions", ["whale_view"]),
                )

            return None

        except jwt.InvalidTokenError as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return None


# Global auth manager instance
auth_manager = JWTAuthManager()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = None,
) -> Dict[str, Any]:
    """
    FastAPI dependency for extracting current user from JWT.
    Task T010: Token validation middleware.

    Args:
        credentials: Bearer token from request header

    Returns:
        User information from token
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    return auth_manager.validate_token(token)


async def validate_websocket_token(
    websocket: WebSocket, token: str
) -> Tuple[bool, Optional[Dict]]:
    """
    Validate token for WebSocket connection.
    Task T010: WebSocket token validation.

    Args:
        websocket: WebSocket connection
        token: JWT token from query parameter

    Returns:
        Tuple of (is_valid, user_data)
    """
    try:
        user_data = auth_manager.validate_token(token)
        return True, user_data
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return False, None


# Task T011: Create /api/auth/token endpoint (will be in main.py)
def create_auth_endpoint():
    """
    Returns FastAPI route for token generation.
    This will be imported and used in the main FastAPI app.
    """
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/auth", tags=["Authentication"])

    @router.post("/token")
    async def generate_token(user_id: str = "default_user"):
        """
        Generate JWT token for authentication.
        Task T011: /api/auth/token endpoint.

        In production, this would validate credentials.
        For MVP, we're using a simple user_id.
        """
        return auth_manager.generate_token(user_id)

    @router.post("/refresh")
    async def refresh_token(credentials: HTTPAuthorizationCredentials = security):
        """
        Refresh JWT token if within refresh window.
        Task T012: Token refresh endpoint.
        """
        new_token = auth_manager.refresh_token(credentials.credentials)

        if new_token:
            return new_token
        else:
            raise HTTPException(status_code=401, detail="Token cannot be refreshed")

    return router
