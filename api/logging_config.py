#!/usr/bin/env python3
"""
Structured Logging Configuration with Correlation ID

Implements:
- structlog JSON output for production
- Correlation ID middleware for request tracing
- Context enrichment for all log messages

Spec: P2 Polish - Task 2
"""

import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


# =============================================================================
# Structlog Configuration
# =============================================================================


def configure_structured_logging():
    """
    Configure structlog for production-grade JSON logging.

    Processors:
    - Filter by level
    - Add logger name and log level
    - ISO timestamp
    - Stack traces and exception info
    - JSON output (machine-readable)
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),  # JSON for production
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# =============================================================================
# Correlation ID Middleware
# =============================================================================


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Injects correlation_id into all logs and responses.

    Flow:
    1. Extract correlation_id from X-Correlation-ID header (or generate new)
    2. Bind to structlog context (available in all subsequent logs)
    3. Add to response headers
    4. Clear context after request completes

    Usage:
        app.add_middleware(CorrelationIDMiddleware)
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and inject correlation_id.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            Response with X-Correlation-ID header
        """
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Add to request state (accessible in endpoints)
        request.state.correlation_id = correlation_id

        # Bind to structlog context (available in all logs)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response
        finally:
            # Clean up context after request completes
            structlog.contextvars.clear_contextvars()


# =============================================================================
# Helper Functions
# =============================================================================


def get_logger(name: str):
    """
    Get structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger

    Example:
        logger = get_logger(__name__)
        logger.info("user_login", user_id=123, correlation_id=request.state.correlation_id)
    """
    return structlog.get_logger(name)
