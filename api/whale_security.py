"""
Rate limiting and security module for Whale Detection Dashboard.
Tasks T013-T016: Token bucket rate limiter, rate limit headers, connection limiting.
"""

import time
import asyncio
from typing import Dict, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException
from api.config import (
    RATE_LIMIT_HTTP_PER_MINUTE,
    RATE_LIMIT_WS_PER_SECOND,
    RATE_LIMIT_BURST_CAPACITY,
    RATE_LIMIT_CONNECTION_ATTEMPTS,
    setup_logging,
)

# Set up module logger
logger = setup_logging(__name__)


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.
    Task T013: Implement token bucket rate limiter.
    """

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens (burst capacity)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            Tuple of (success, tokens_remaining)
        """
        async with self.lock:
            # Refill tokens based on time passed
            now = time.time()
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * self.refill_rate

            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now

            # Try to consume requested tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, self.tokens
            else:
                return False, self.tokens


class RateLimiter:
    """
    Rate limiting manager for HTTP and WebSocket connections.
    Tasks T013-T016: Complete rate limiting implementation.
    """

    def __init__(self):
        # HTTP rate limiters per IP
        self.http_buckets: Dict[str, TokenBucket] = {}

        # WebSocket rate limiters per connection
        self.ws_buckets: Dict[str, TokenBucket] = {}

        # Connection attempt tracking (T016)
        self.connection_attempts: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10)
        )

        # Cleanup task
        self.cleanup_task = None

        logger.info("Rate limiter initialized")
        logger.info(
            f"HTTP: {RATE_LIMIT_HTTP_PER_MINUTE}/min, WS: {RATE_LIMIT_WS_PER_SECOND}/sec"
        )

    def get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for proxy headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    def get_http_bucket(self, ip: str) -> TokenBucket:
        """
        Get or create HTTP token bucket for IP.
        Task T014: Configure rate limits.
        """
        if ip not in self.http_buckets:
            # 100 requests/minute = 1.67 requests/second
            refill_rate = RATE_LIMIT_HTTP_PER_MINUTE / 60.0
            self.http_buckets[ip] = TokenBucket(
                capacity=RATE_LIMIT_BURST_CAPACITY, refill_rate=refill_rate
            )
        return self.http_buckets[ip]

    def get_ws_bucket(self, connection_id: str) -> TokenBucket:
        """
        Get or create WebSocket token bucket for connection.
        Task T014: Configure WebSocket rate limits.
        """
        if connection_id not in self.ws_buckets:
            # 20 messages/second
            self.ws_buckets[connection_id] = TokenBucket(
                capacity=RATE_LIMIT_BURST_CAPACITY, refill_rate=RATE_LIMIT_WS_PER_SECOND
            )
        return self.ws_buckets[connection_id]

    async def check_http_limit(self, request: Request) -> Tuple[bool, Dict[str, str]]:
        """
        Check HTTP rate limit for request.
        Task T015: Add rate limit headers.

        Returns:
            Tuple of (allowed, headers_dict)
        """
        ip = self.get_client_ip(request)
        bucket = self.get_http_bucket(ip)

        allowed, remaining = await bucket.consume()

        # Calculate rate limit headers (T015)
        headers = {
            "X-RateLimit-Limit": str(RATE_LIMIT_HTTP_PER_MINUTE),
            "X-RateLimit-Remaining": str(int(remaining)),
            "X-RateLimit-Reset": str(int(time.time() + 60)),
        }

        if not allowed:
            # Add retry-after header when rate limited
            headers["Retry-After"] = "60"
            logger.warning(f"Rate limit exceeded for IP: {ip}")

        return allowed, headers

    async def check_ws_limit(self, connection_id: str) -> bool:
        """
        Check WebSocket message rate limit.
        Task T014: WebSocket rate limiting.
        """
        bucket = self.get_ws_bucket(connection_id)
        allowed, _ = await bucket.consume()

        if not allowed:
            logger.warning(f"WebSocket rate limit exceeded: {connection_id}")

        return allowed

    def check_connection_attempt(self, ip: str) -> bool:
        """
        Check if connection attempt is allowed.
        Task T016: Connection attempt limiting (5/minute per IP).

        Args:
            ip: Client IP address

        Returns:
            True if connection allowed, False if rate limited
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)

        # Get attempts for this IP
        attempts = self.connection_attempts[ip]

        # Remove old attempts
        while attempts and attempts[0] < minute_ago:
            attempts.popleft()

        # Check if under limit
        if len(attempts) >= RATE_LIMIT_CONNECTION_ATTEMPTS:
            logger.warning(f"Connection attempt limit exceeded for IP: {ip}")
            return False

        # Record this attempt
        attempts.append(now)
        return True

    async def cleanup_old_buckets(self):
        """
        Periodically clean up old token buckets.
        Runs every 5 minutes to remove inactive IPs.
        """
        while True:
            await asyncio.sleep(300)  # 5 minutes

            # Clean HTTP buckets (remove if not used for 10 minutes)
            cutoff_time = time.time() - 600
            http_to_remove = [
                ip
                for ip, bucket in self.http_buckets.items()
                if bucket.last_refill < cutoff_time
            ]

            for ip in http_to_remove:
                del self.http_buckets[ip]

            if http_to_remove:
                logger.info(f"Cleaned up {len(http_to_remove)} HTTP rate limit buckets")

            # Clean WebSocket buckets similarly
            ws_to_remove = [
                conn_id
                for conn_id, bucket in self.ws_buckets.items()
                if bucket.last_refill < cutoff_time
            ]

            for conn_id in ws_to_remove:
                del self.ws_buckets[conn_id]

            if ws_to_remove:
                logger.info(
                    f"Cleaned up {len(ws_to_remove)} WebSocket rate limit buckets"
                )

    def start_cleanup_task(self):
        """Start the cleanup background task."""
        if not self.cleanup_task:
            self.cleanup_task = asyncio.create_task(self.cleanup_old_buckets())
            logger.info("Started rate limiter cleanup task")


# Global rate limiter instance
rate_limiter = RateLimiter()


# FastAPI middleware for rate limiting
async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware to apply rate limiting to all HTTP requests.
    Tasks T014-T015: HTTP rate limiting with headers.
    """
    # Skip rate limiting for health check endpoint
    if request.url.path == "/health":
        return await call_next(request)

    # Check rate limit
    allowed, headers = await rate_limiter.check_http_limit(request)

    if not allowed:
        # Return 429 Too Many Requests
        response = Response(
            content='{"detail": "Rate limit exceeded"}',
            status_code=429,
            media_type="application/json",
        )
        # Add rate limit headers
        for key, value in headers.items():
            response.headers[key] = value
        return response

    # Process request
    response = await call_next(request)

    # Add rate limit headers to successful responses
    for key, value in headers.items():
        response.headers[key] = value

    return response


# WebSocket rate limiting decorator
def ws_rate_limited(connection_id: str):
    """
    Decorator for WebSocket message handlers to apply rate limiting.
    Task T014: WebSocket rate limiting.
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            if await rate_limiter.check_ws_limit(connection_id):
                return await func(*args, **kwargs)
            else:
                raise HTTPException(
                    status_code=429, detail="WebSocket message rate limit exceeded"
                )

        return wrapper

    return decorator
