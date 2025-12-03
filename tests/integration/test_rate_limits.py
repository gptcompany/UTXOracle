"""
Integration tests for rate limiting.
Task T018: Write rate limiting tests.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock
from fastapi import Request
from api.whale_security import TokenBucket, RateLimiter


class TestTokenBucket:
    """Test token bucket algorithm."""

    @pytest.mark.asyncio
    async def test_token_consumption(self):
        """Test basic token consumption."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Should allow initial consumption
        allowed, remaining = await bucket.consume(5)
        assert allowed is True
        assert remaining == 5

        # Should allow more consumption
        allowed, remaining = await bucket.consume(3)
        assert allowed is True
        assert remaining == 2

        # Should deny when not enough tokens
        allowed, remaining = await bucket.consume(5)
        assert allowed is False
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test token refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 10 tokens/second

        # Consume all tokens
        await bucket.consume(10)

        # Wait for refill
        await asyncio.sleep(0.5)  # Should refill ~5 tokens

        # Should allow consumption after refill
        allowed, remaining = await bucket.consume(4)
        assert allowed is True
        assert remaining >= 0

    @pytest.mark.asyncio
    async def test_burst_capacity(self):
        """Test burst capacity limiting."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Consume all tokens
        await bucket.consume(10)

        # Wait for refill beyond capacity
        await asyncio.sleep(15)  # Would refill 15 tokens, but capped at 10

        # Should only have capacity tokens
        allowed, remaining = await bucket.consume(1)
        assert allowed is True
        assert remaining <= 9  # Max capacity minus consumed


class TestRateLimiter:
    """Test rate limiter functionality."""

    def test_get_client_ip(self):
        """Test IP extraction from request."""
        limiter = RateLimiter()

        # Test direct client IP
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock(host="192.168.1.1")

        ip = limiter.get_client_ip(request)
        assert ip == "192.168.1.1"

        # Test X-Forwarded-For header
        request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        ip = limiter.get_client_ip(request)
        assert ip == "10.0.0.1"

        # Test X-Real-IP header
        request.headers = {"X-Real-IP": "10.0.0.2"}
        ip = limiter.get_client_ip(request)
        assert ip == "10.0.0.2"

    def test_get_http_bucket(self):
        """Test HTTP bucket creation and retrieval."""
        limiter = RateLimiter()

        # Get bucket for IP
        bucket1 = limiter.get_http_bucket("192.168.1.1")
        assert bucket1 is not None

        # Should return same bucket for same IP
        bucket2 = limiter.get_http_bucket("192.168.1.1")
        assert bucket1 is bucket2

        # Different IP should get different bucket
        bucket3 = limiter.get_http_bucket("192.168.1.2")
        assert bucket3 is not bucket1

    def test_get_ws_bucket(self):
        """Test WebSocket bucket creation and retrieval."""
        limiter = RateLimiter()

        # Get bucket for connection
        bucket1 = limiter.get_ws_bucket("conn_123")
        assert bucket1 is not None

        # Should return same bucket for same connection
        bucket2 = limiter.get_ws_bucket("conn_123")
        assert bucket1 is bucket2

        # Different connection should get different bucket
        bucket3 = limiter.get_ws_bucket("conn_456")
        assert bucket3 is not bucket1

    @pytest.mark.asyncio
    async def test_check_http_limit(self):
        """Test HTTP rate limiting."""
        limiter = RateLimiter()

        # Create mock request
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock(host="192.168.1.1")

        # Should allow initial requests
        for _ in range(5):
            allowed, headers = await limiter.check_http_limit(request)
            assert allowed is True
            assert "X-RateLimit-Limit" in headers
            assert "X-RateLimit-Remaining" in headers
            assert "X-RateLimit-Reset" in headers

        # Consume remaining tokens quickly
        bucket = limiter.get_http_bucket("192.168.1.1")
        await bucket.consume(100)  # Exhaust tokens

        # Should now be rate limited
        allowed, headers = await limiter.check_http_limit(request)
        assert allowed is False
        assert "Retry-After" in headers

    @pytest.mark.asyncio
    async def test_check_ws_limit(self):
        """Test WebSocket rate limiting."""
        limiter = RateLimiter()
        conn_id = "test_conn_123"

        # Should allow initial messages
        for _ in range(5):
            allowed = await limiter.check_ws_limit(conn_id)
            assert allowed is True

        # Exhaust tokens
        bucket = limiter.get_ws_bucket(conn_id)
        await bucket.consume(100)

        # Should now be rate limited
        allowed = await limiter.check_ws_limit(conn_id)
        assert allowed is False

    def test_connection_attempt_limiting(self):
        """Test connection attempt rate limiting."""
        limiter = RateLimiter()
        ip = "192.168.1.1"

        # Should allow initial attempts
        for _ in range(5):
            allowed = limiter.check_connection_attempt(ip)
            assert allowed is True

        # 6th attempt should be blocked
        allowed = limiter.check_connection_attempt(ip)
        assert allowed is False

        # Different IP should be allowed
        allowed = limiter.check_connection_attempt("192.168.1.2")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_cleanup_old_buckets(self):
        """Test that old buckets are cleaned up."""
        limiter = RateLimiter()

        # Create some buckets
        bucket1 = limiter.get_http_bucket("192.168.1.1")
        bucket2 = limiter.get_ws_bucket("conn_123")

        # Simulate old last_refill time
        bucket1.last_refill = time.time() - 700  # 11+ minutes ago
        bucket2.last_refill = time.time() - 700

        # Run cleanup
        await limiter.cleanup_old_buckets()

        # Old buckets should be removed
        assert "192.168.1.1" not in limiter.http_buckets
        assert "conn_123" not in limiter.ws_buckets

    @pytest.mark.asyncio
    async def test_rate_limit_headers(self):
        """Test that rate limit headers are properly set."""
        limiter = RateLimiter()

        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock(host="192.168.1.1")

        # Get headers
        allowed, headers = await limiter.check_http_limit(request)

        # Check header format
        assert headers["X-RateLimit-Limit"] == "100"  # From config
        assert int(headers["X-RateLimit-Remaining"]) >= 0
        assert int(headers["X-RateLimit-Reset"]) > time.time()

        # When rate limited
        bucket = limiter.get_http_bucket("192.168.1.1")
        await bucket.consume(100)  # Exhaust

        allowed, headers = await limiter.check_http_limit(request)
        assert not allowed
        assert headers["Retry-After"] == "60"


@pytest.fixture
def clean_rate_limiter():
    """Fixture to provide a clean rate limiter instance."""
    return RateLimiter()


def test_rate_limiter_initialization(clean_rate_limiter):
    """Test rate limiter initializes correctly."""
    assert clean_rate_limiter.http_buckets == {}
    assert clean_rate_limiter.ws_buckets == {}
    assert clean_rate_limiter.cleanup_task is None
