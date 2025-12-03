#!/usr/bin/env python3
"""
WebSocket Authentication Module for Mempool Whale Detection
Implements JWT-based authentication for WebSocket connections

Part of Task T018a: Security implementation for Constitution Principle V
"""

import jwt
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
import secrets

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_SECRET_KEY = None  # Must be set via environment or config
TOKEN_EXPIRY_HOURS = 24
TOKEN_REFRESH_HOURS = 1  # Refresh if token expires in less than this
RATE_LIMIT_REQUESTS = 100  # Max requests per minute
RATE_LIMIT_WINDOW = 60  # Window in seconds


@dataclass
class AuthConfig:
    """Authentication configuration"""

    secret_key: str
    algorithm: str = "HS256"
    token_expiry_hours: int = TOKEN_EXPIRY_HOURS
    token_refresh_hours: int = TOKEN_REFRESH_HOURS
    rate_limit_requests: int = RATE_LIMIT_REQUESTS
    rate_limit_window: int = RATE_LIMIT_WINDOW
    enabled: bool = True  # Can disable for development


@dataclass
class AuthToken:
    """Represents an authenticated JWT token"""

    token: str
    client_id: str
    issued_at: datetime
    expires_at: datetime
    permissions: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def needs_refresh(self) -> bool:
        """Check if token should be refreshed"""
        time_until_expiry = self.expires_at - datetime.now(timezone.utc)
        return time_until_expiry.total_seconds() < (TOKEN_REFRESH_HOURS * 3600)


class WebSocketAuthenticator:
    """JWT authentication handler for WebSocket connections"""

    def __init__(self, config: Optional[AuthConfig] = None):
        """Initialize authenticator with configuration"""
        self.config = config or self._load_default_config()
        self.active_tokens: Dict[str, AuthToken] = {}
        self.rate_limiter = RateLimiter(
            self.config.rate_limit_requests, self.config.rate_limit_window
        )

        if not self.config.secret_key:
            logger.warning("No secret key configured - authentication disabled")
            self.config.enabled = False

    def _load_default_config(self) -> AuthConfig:
        """Load configuration from environment or config file"""
        import os

        # Try environment variables first
        secret_key = os.environ.get("WEBSOCKET_SECRET_KEY")

        # Try config file
        if not secret_key:
            config_path = Path(__file__).parent.parent.parent / ".env"
            if config_path.exists():
                with open(config_path) as f:
                    for line in f:
                        if line.startswith("WEBSOCKET_SECRET_KEY="):
                            secret_key = line.split("=", 1)[1].strip()
                            break

        # Generate a random key for development (with warning)
        if not secret_key:
            secret_key = secrets.token_urlsafe(32)
            logger.warning(
                "Generated temporary secret key - SET WEBSOCKET_SECRET_KEY in production!"
            )

        return AuthConfig(secret_key=secret_key)

    def generate_token(
        self, client_id: str, permissions: Optional[Set[str]] = None
    ) -> str:
        """Generate a new JWT token for a client"""
        if not self.config.enabled:
            return "NO_AUTH_DEVELOPMENT_MODE"

        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.config.token_expiry_hours)

        payload = {
            "client_id": client_id,
            "iat": now.timestamp(),
            "exp": expires.timestamp(),
            "permissions": list(permissions or {"read"}),
            "version": "1.0",
        }

        token_str = jwt.encode(
            payload, self.config.secret_key, algorithm=self.config.algorithm
        )

        # Store active token
        token = AuthToken(
            token=token_str,
            client_id=client_id,
            issued_at=now,
            expires_at=expires,
            permissions=permissions or {"read"},
        )
        self.active_tokens[client_id] = token

        logger.info(f"Generated token for client {client_id}, expires at {expires}")
        return token_str

    def validate_token(self, token_str: str) -> Optional[AuthToken]:
        """Validate a JWT token and return AuthToken if valid"""
        if not self.config.enabled:
            # Authentication disabled - return mock token
            return AuthToken(
                token="NO_AUTH",
                client_id="dev_client",
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                permissions={"read", "write"},
            )

        try:
            # Decode and verify token
            payload = jwt.decode(
                token_str, self.config.secret_key, algorithms=[self.config.algorithm]
            )

            # Extract token data
            client_id = payload.get("client_id")
            if not client_id:
                logger.error("Token missing client_id")
                return None

            # Create AuthToken object
            token = AuthToken(
                token=token_str,
                client_id=client_id,
                issued_at=datetime.fromtimestamp(payload["iat"], timezone.utc),
                expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
                permissions=set(payload.get("permissions", ["read"])),
            )

            # Check if token is expired
            if token.is_expired:
                logger.warning(f"Token expired for client {client_id}")
                return None

            return token

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            return None

    def refresh_token(self, old_token: str) -> Optional[str]:
        """Refresh an existing token if it's still valid"""
        token = self.validate_token(old_token)
        if not token:
            return None

        # Generate new token with same permissions
        return self.generate_token(token.client_id, token.permissions)

    async def authenticate_websocket(
        self, websocket, path: str = None
    ) -> Optional[AuthToken]:
        """Authenticate a WebSocket connection

        Args:
            websocket: WebSocket connection
            path: Optional URL path (unused, for compatibility with old websockets versions)

        Returns:
            AuthToken if authentication succeeds, None otherwise
        """
        if not self.config.enabled:
            # Authentication disabled
            return AuthToken(
                token="NO_AUTH",
                client_id=f"dev_{websocket.remote_address[0]}",
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                permissions={"read", "write"},
            )

        try:
            # Wait for authentication message
            auth_message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            auth_data = json.loads(auth_message)

            if auth_data.get("type") != "auth":
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "First message must be authentication",
                        }
                    )
                )
                return None

            token_str = auth_data.get("token")
            if not token_str:
                await websocket.send(
                    json.dumps({"type": "error", "message": "Token required"})
                )
                return None

            # Validate token
            token = self.validate_token(token_str)
            if not token:
                await websocket.send(
                    json.dumps({"type": "error", "message": "Invalid or expired token"})
                )
                return None

            # Check rate limit
            if not self.rate_limiter.check_rate_limit(token.client_id):
                await websocket.send(
                    json.dumps({"type": "error", "message": "Rate limit exceeded"})
                )
                return None

            # Send success response
            await websocket.send(
                json.dumps(
                    {
                        "type": "auth_success",
                        "client_id": token.client_id,
                        "permissions": list(token.permissions),
                        "expires_at": token.expires_at.isoformat(),
                    }
                )
            )

            logger.info(f"Authenticated WebSocket for client {token.client_id}")
            return token

        except asyncio.TimeoutError:
            await websocket.send(
                json.dumps({"type": "error", "message": "Authentication timeout"})
            )
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await websocket.send(
                json.dumps({"type": "error", "message": "Authentication failed"})
            )
            return None

    def revoke_token(self, client_id: str) -> bool:
        """Revoke a client's token"""
        if client_id in self.active_tokens:
            del self.active_tokens[client_id]
            logger.info(f"Revoked token for client {client_id}")
            return True
        return False

    def cleanup_expired_tokens(self):
        """Remove expired tokens from active set"""
        now = datetime.now(timezone.utc)
        expired = [
            client_id
            for client_id, token in self.active_tokens.items()
            if token.is_expired
        ]
        for client_id in expired:
            del self.active_tokens[client_id]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired tokens")


class RateLimiter:
    """Simple rate limiter for API protection"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}

    def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limit"""
        now = datetime.now(timezone.utc)

        if client_id not in self.requests:
            self.requests[client_id] = []

        # Clean old requests
        cutoff = now - timedelta(seconds=self.window_seconds)
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id] if req_time > cutoff
        ]

        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for client {client_id}")
            return False

        # Record request
        self.requests[client_id].append(now)
        return True

    def cleanup_old_entries(self):
        """Remove old rate limit entries"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds * 2)

        for client_id in list(self.requests.keys()):
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id] if req_time > cutoff
            ]
            if not self.requests[client_id]:
                del self.requests[client_id]


# Middleware decorator for WebSocket handlers
def require_auth(handler):
    """Decorator to require authentication for WebSocket handlers"""

    async def wrapped(websocket, path, *args, **kwargs):
        # Create authenticator
        auth = WebSocketAuthenticator()

        # Authenticate connection
        token = await auth.authenticate_websocket(websocket, path)
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return

        # Add token to handler context
        kwargs["auth_token"] = token
        kwargs["authenticator"] = auth

        # Call original handler
        return await handler(websocket, path, *args, **kwargs)

    return wrapped


# Example usage for testing
async def _example_protected_handler(websocket, path, auth_token=None, **kwargs):
    """Example WebSocket handler with authentication"""
    logger.info(
        f"Client {auth_token.client_id} connected with permissions: {auth_token.permissions}"
    )

    try:
        async for message in websocket:
            data = json.loads(message)

            # Check permissions
            if "write" not in auth_token.permissions and data.get("type") == "write":
                await websocket.send(
                    json.dumps(
                        {"type": "error", "message": "Write permission required"}
                    )
                )
                continue

            # Process message
            await websocket.send(
                json.dumps({"type": "response", "data": f"Processed: {data}"})
            )

    except Exception as e:
        logger.error(f"Handler error: {e}")


if __name__ == "__main__":
    # Test token generation and validation
    auth = WebSocketAuthenticator()

    # Generate token
    token = auth.generate_token("test_client", {"read", "write"})
    print(f"Generated token: {token[:50]}...")

    # Validate token
    validated = auth.validate_token(token)
    if validated:
        print(f"Token valid for client: {validated.client_id}")
        print(f"Permissions: {validated.permissions}")
        print(f"Expires at: {validated.expires_at}")

    # Test with protected handler
    import websockets

    async def start_test_server():
        protected_handler = require_auth(_example_protected_handler)
        async with websockets.serve(protected_handler, "localhost", 8766):
            print("Test auth server running on ws://localhost:8766")
            await asyncio.Future()  # Run forever

    # Run test server
    # asyncio.run(start_test_server())
