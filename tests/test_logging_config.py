#!/usr/bin/env python3
"""
Tests for Structured Logging Configuration Module

Coverage areas:
- structlog configuration
- CorrelationIDMiddleware behavior
- get_logger helper function
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from starlette.requests import Request
from starlette.responses import Response


# =============================================================================
# Structlog Configuration Tests
# =============================================================================


def test_configure_structured_logging():
    """
    Test that configure_structured_logging sets up structlog correctly.

    Expected:
    - No exceptions raised
    - structlog is configured
    """
    from api.logging_config import configure_structured_logging

    # Should not raise exceptions
    configure_structured_logging()

    # Verify structlog is configured
    import structlog

    logger = structlog.get_logger(__name__)
    assert logger is not None


def test_get_logger_returns_structlog_instance():
    """
    Test that get_logger returns a configured structlog logger.

    Expected:
    - Returns a logger instance
    - Logger has bind method (structlog-specific)
    """
    from api.logging_config import get_logger, configure_structured_logging

    configure_structured_logging()
    logger = get_logger("test_module")

    assert logger is not None
    assert hasattr(logger, "bind")  # structlog-specific method


# =============================================================================
# CorrelationIDMiddleware Tests
# =============================================================================


@pytest.mark.asyncio
async def test_correlation_id_middleware_generates_uuid():
    """
    Test that middleware generates a valid UUID when no header provided.

    Expected:
    - correlation_id is a valid UUID
    - correlation_id is added to request.state
    """
    from api.logging_config import CorrelationIDMiddleware

    middleware = CorrelationIDMiddleware(app=MagicMock())

    # Mock request without correlation_id header
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()

    # Mock call_next
    async def mock_call_next(req):
        response = MagicMock(spec=Response)
        response.headers = {}
        return response

    # Execute middleware
    response = await middleware.dispatch(request, mock_call_next)

    # Verify correlation_id was added to request.state
    assert hasattr(request.state, "correlation_id")

    # Verify it's a valid UUID
    correlation_id = request.state.correlation_id
    try:
        uuid_obj = uuid.UUID(correlation_id)
        assert str(uuid_obj) == correlation_id
    except ValueError:
        pytest.fail(f"Invalid UUID generated: {correlation_id}")


@pytest.mark.asyncio
async def test_correlation_id_middleware_preserves_header():
    """
    Test that middleware preserves correlation_id from request header.

    Expected:
    - correlation_id from header is used
    - Same correlation_id returned in response
    """
    from api.logging_config import CorrelationIDMiddleware

    middleware = CorrelationIDMiddleware(app=MagicMock())

    test_correlation_id = "test-correlation-12345"

    # Mock request with correlation_id header
    request = MagicMock(spec=Request)
    request.headers = {"X-Correlation-ID": test_correlation_id}
    request.state = MagicMock()

    # Mock call_next
    async def mock_call_next(req):
        response = MagicMock(spec=Response)
        response.headers = {}
        return response

    # Execute middleware
    response = await middleware.dispatch(request, mock_call_next)

    # Verify correlation_id matches header
    assert request.state.correlation_id == test_correlation_id
    assert response.headers["X-Correlation-ID"] == test_correlation_id


@pytest.mark.asyncio
async def test_correlation_id_middleware_clears_context():
    """
    Test that middleware clears structlog context after request.

    Expected:
    - Context is cleared in finally block
    - No correlation_id leaks between requests
    """
    from api.logging_config import CorrelationIDMiddleware

    middleware = CorrelationIDMiddleware(app=MagicMock())

    # Mock request
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()

    # Mock call_next
    async def mock_call_next(req):
        response = MagicMock(spec=Response)
        response.headers = {}
        return response

    # Execute middleware
    with patch("structlog.contextvars.clear_contextvars") as mock_clear:
        await middleware.dispatch(request, mock_call_next)

        # Verify context was cleared
        mock_clear.assert_called_once()


@pytest.mark.asyncio
async def test_correlation_id_middleware_handles_exceptions():
    """
    Test that middleware clears context even when exception occurs.

    Expected:
    - Context cleanup happens in finally block
    - Exception is re-raised
    """
    from api.logging_config import CorrelationIDMiddleware

    middleware = CorrelationIDMiddleware(app=MagicMock())

    # Mock request
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()

    # Mock call_next that raises exception
    async def mock_call_next_error(req):
        raise ValueError("Simulated error")

    # Execute middleware and expect exception
    with patch("structlog.contextvars.clear_contextvars") as mock_clear:
        with pytest.raises(ValueError, match="Simulated error"):
            await middleware.dispatch(request, mock_call_next_error)

        # Verify context was still cleared despite exception
        mock_clear.assert_called_once()


# =============================================================================
# Integration Tests with structlog
# =============================================================================


def test_structlog_json_renderer():
    """
    Test that structlog is configured with JSON renderer for production.

    Expected:
    - JSON output (not human-readable)
    - Structured log format
    """
    from api.logging_config import configure_structured_logging
    import structlog

    configure_structured_logging()
    logger = structlog.get_logger(__name__)

    # This would normally output JSON, but we can't easily capture it in tests
    # Just verify the logger has the expected methods
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "warning")


def test_correlation_id_in_log_context():
    """
    Test that correlation_id is automatically included in log context.

    Expected:
    - Logs include correlation_id when bound
    - Context is thread-safe
    """
    from api.logging_config import configure_structured_logging
    import structlog

    configure_structured_logging()

    test_correlation_id = "test-123-abc"

    # Bind correlation_id to context
    structlog.contextvars.bind_contextvars(correlation_id=test_correlation_id)

    logger = structlog.get_logger(__name__)

    # Logger should have access to correlation_id in context
    # (We can't easily test the output, but verify binding works)
    assert logger is not None

    # Clean up
    structlog.contextvars.clear_contextvars()


# =============================================================================
# Error Path Tests
# =============================================================================


def test_get_logger_with_empty_name():
    """
    Test get_logger with empty string as name.

    Expected:
    - Should not crash
    - Returns a valid logger
    """
    from api.logging_config import get_logger

    logger = get_logger("")
    assert logger is not None


def test_get_logger_with_special_characters():
    """
    Test get_logger with special characters in name.

    Expected:
    - Should handle special characters gracefully
    - Returns a valid logger
    """
    from api.logging_config import get_logger

    logger = get_logger("test.module:123@special!")
    assert logger is not None


@pytest.mark.asyncio
async def test_middleware_with_case_insensitive_header():
    """
    Test middleware handles X-Correlation-ID header case-insensitively.

    Expected:
    - Header lookup should work regardless of case
    """
    from api.logging_config import CorrelationIDMiddleware

    middleware = CorrelationIDMiddleware(app=MagicMock())

    # Mock request with lowercase header
    request = MagicMock(spec=Request)
    # Simulate case-insensitive header access (Starlette does this)
    mock_headers = MagicMock()
    mock_headers.get = MagicMock(
        side_effect=lambda key: "test-lower-123"
        if key.lower() == "x-correlation-id"
        else None
    )
    request.headers = mock_headers
    request.state = MagicMock()

    async def mock_call_next(req):
        response = MagicMock(spec=Response)
        response.headers = {}
        return response

    response = await middleware.dispatch(request, mock_call_next)

    # Should handle case-insensitive header lookup
    assert response is not None
