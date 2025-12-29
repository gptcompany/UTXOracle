"""
Simple Rate Limiter for FastAPI - Task T052
In-memory rate limiting without external dependencies

Features:
- Per-IP rate limiting
- Configurable limits (requests per time window)
- Token bucket algorithm
- Automatic cleanup of expired entries
- KISS principle: No Redis, no external dependencies

Usage:
    from api.rate_limiter import RateLimiter, rate_limit

    limiter = RateLimiter(max_requests=100, window_seconds=60)
    app = FastAPI()

    @app.get("/api/endpoint")
    async def endpoint(request: Request, _=Depends(rate_limit(limiter))):
        return {"status": "ok"}
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status, Depends
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""

    max_tokens: int
    tokens: float
    last_update: float = field(default_factory=time.time)
    refill_rate: float = 1.0  # tokens per second

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens from bucket

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            bool: True if tokens were consumed, False if insufficient
        """
        # Refill tokens based on time elapsed
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.max_tokens, self.tokens + (elapsed * self.refill_rate))
        self.last_update = now

        # Try to consume
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def get_retry_after(self) -> int:
        """
        Get number of seconds to wait before retry

        Returns:
            int: Seconds until next token available
        """
        if self.tokens >= 1:
            return 0
        tokens_needed = 1 - self.tokens
        return int(tokens_needed / self.refill_rate) + 1


class RateLimiter:
    """
    Simple in-memory rate limiter using token bucket algorithm

    Example:
        # 100 requests per minute
        limiter = RateLimiter(max_requests=100, window_seconds=60)

        # 10 requests per second
        limiter = RateLimiter(max_requests=10, window_seconds=1)
    """

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        cleanup_interval: int = 300,  # 5 minutes
    ):
        """
        Initialize rate limiter

        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Time window in seconds
            cleanup_interval: How often to clean up expired entries (seconds)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval

        # Calculate refill rate (tokens per second)
        self.refill_rate = max_requests / window_seconds

        # Token buckets per IP
        self.buckets: Dict[str, TokenBucket] = {}
        self.lock = Lock()

        # Cleanup tracking
        self.last_cleanup = time.time()

        # Statistics
        self.total_requests = 0
        self.total_limited = 0

        logger.info(
            f"Rate limiter initialized: {max_requests} requests per {window_seconds}s "
            f"({self.refill_rate:.2f} req/s)"
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP from request

        Handles X-Forwarded-For and X-Real-IP headers (reverse proxy support)
        """
        # Check X-Forwarded-For (proxy header)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP in chain
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP (nginx proxy header)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct connection IP
        return request.client.host if request.client else "unknown"

    def _cleanup_expired(self):
        """Remove expired/inactive token buckets to prevent memory leak"""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        with self.lock:
            expired_ips = [
                ip
                for ip, bucket in self.buckets.items()
                if now - bucket.last_update > self.window_seconds * 2
            ]

            for ip in expired_ips:
                del self.buckets[ip]

            if expired_ips:
                logger.debug(
                    f"Cleaned up {len(expired_ips)} expired rate limit entries"
                )

            self.last_cleanup = now

    def check_rate_limit(self, request: Request) -> Tuple[bool, int]:
        """
        Check if request is within rate limit

        Args:
            request: FastAPI request object

        Returns:
            Tuple[bool, int]: (is_allowed, retry_after_seconds)
        """
        client_ip = self._get_client_ip(request)

        # Periodic cleanup
        self._cleanup_expired()

        with self.lock:
            self.total_requests += 1

            # Get or create bucket for this IP
            if client_ip not in self.buckets:
                self.buckets[client_ip] = TokenBucket(
                    max_tokens=self.max_requests,
                    tokens=self.max_requests,  # Start with full bucket
                    refill_rate=self.refill_rate,
                )

            bucket = self.buckets[client_ip]

            # Try to consume token
            if bucket.consume():
                return (True, 0)
            else:
                self.total_limited += 1
                retry_after = bucket.get_retry_after()
                logger.warning(
                    f"Rate limit exceeded for {client_ip} (retry after {retry_after}s)"
                )
                return (False, retry_after)

    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        with self.lock:
            active_ips = len(self.buckets)
            limit_rate = (
                (self.total_limited / self.total_requests * 100)
                if self.total_requests > 0
                else 0
            )

            return {
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "refill_rate": round(self.refill_rate, 2),
                "active_ips": active_ips,
                "total_requests": self.total_requests,
                "total_limited": self.total_limited,
                "limit_rate_percent": round(limit_rate, 2),
            }

    def reset_stats(self):
        """Reset statistics counters"""
        with self.lock:
            self.total_requests = 0
            self.total_limited = 0


def rate_limit(limiter: RateLimiter):
    """
    FastAPI dependency for rate limiting

    Usage:
        from api.rate_limiter import RateLimiter, rate_limit

        limiter = RateLimiter(max_requests=100, window_seconds=60)

        @app.get("/api/endpoint")
        async def endpoint(request: Request, _=Depends(rate_limit(limiter))):
            return {"status": "ok"}
    """

    async def check_limit(request: Request):
        allowed, retry_after = limiter.check_rate_limit(request)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please retry after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    return check_limit


# Example usage
if __name__ == "__main__":
    from fastapi import FastAPI, Request
    import uvicorn

    # Create limiter: 5 requests per 10 seconds
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(request: Request, _=Depends(rate_limit(limiter))):
        return {
            "status": "ok",
            "message": "Request successful",
            "stats": limiter.get_stats(),
        }

    @app.get("/stats")
    async def stats_endpoint():
        return limiter.get_stats()

    print("Starting test server on http://localhost:8080/test")
    print("Try making multiple requests to see rate limiting in action")
    print("Stats available at http://localhost:8080/stats")

    uvicorn.run(app, host="127.0.0.1", port=8080)
