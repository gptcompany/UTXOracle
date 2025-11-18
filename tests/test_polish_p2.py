#!/usr/bin/env python3
"""
Tests for Polish P2 Enhancements (Tasks 1-2)

Coverage areas:
- Enhanced /health endpoint with service connectivity checks
- Structured logging with correlation_id middleware
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid


# =============================================================================
# Task 1: Enhanced /health Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_health_endpoint_all_services_healthy(client):
    """
    Test /health endpoint when all services are healthy.

    Expected:
    - overall status: "healthy"
    - checks.database.status: "ok"
    - checks.electrs.status: "ok"
    - checks.mempool_backend.status: "ok"
    """
    with (
        patch("api.main.check_electrs_connectivity") as mock_electrs,
        patch("api.main.check_mempool_backend") as mock_mempool,
        patch("api.main.get_db_connection") as mock_db,
    ):
        # Mock all services as healthy
        mock_electrs.return_value = AsyncMock(
            status="ok", latency_ms=15.2, last_success="2025-11-18T10:00:00"
        )
        mock_mempool.return_value = AsyncMock(
            status="ok", latency_ms=22.5, last_success="2025-11-18T10:00:00"
        )
        mock_db_conn = MagicMock()
        mock_db_conn.execute.return_value.fetchone.return_value = (1,)
        mock_db_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value = mock_db_conn

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Check overall status
        assert data["status"] == "healthy"

        # Check service checks exist
        assert "checks" in data
        assert "database" in data["checks"]
        assert "electrs" in data["checks"]
        assert "mempool_backend" in data["checks"]

        # Verify all services are OK
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["electrs"]["status"] == "ok"
        assert data["checks"]["mempool_backend"]["status"] == "ok"

        # Verify backward compatibility
        assert "database" in data  # Legacy field
        assert "uptime_seconds" in data
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_endpoint_database_offline(client):
    """
    Test /health endpoint when database is offline (critical service).

    Expected:
    - overall status: "unhealthy"
    - checks.database.status: "error"
    """
    with (
        patch("api.main.check_electrs_connectivity") as mock_electrs,
        patch("api.main.check_mempool_backend") as mock_mempool,
        patch("api.main.get_db_connection") as mock_db,
    ):
        # Mock healthy external services
        mock_electrs.return_value = AsyncMock(status="ok", latency_ms=15.2)
        mock_mempool.return_value = AsyncMock(status="ok", latency_ms=22.5)

        # Mock database offline
        mock_db.side_effect = Exception("Database connection failed")

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Database offline is critical
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "error"
        assert "Database connection failed" in data["checks"]["database"]["error"]


@pytest.mark.asyncio
async def test_health_endpoint_electrs_timeout(client):
    """
    Test /health endpoint when electrs is timing out (non-critical).

    Expected:
    - overall status: "degraded" (not unhealthy)
    - checks.electrs.status: "error" or "timeout"
    """
    with (
        patch("api.main.check_electrs_connectivity") as mock_electrs,
        patch("api.main.check_mempool_backend") as mock_mempool,
        patch("api.main.get_db_connection") as mock_db,
    ):
        # Mock database healthy
        mock_db_conn = MagicMock()
        mock_db_conn.execute.return_value.fetchone.return_value = (1,)
        mock_db_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value = mock_db_conn

        # Mock mempool backend healthy
        mock_mempool.return_value = AsyncMock(status="ok", latency_ms=22.5)

        # Mock electrs timing out
        mock_electrs.return_value = AsyncMock(
            status="timeout", error="Request timeout (>2s)"
        )

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Non-critical service down = degraded
        assert data["status"] == "degraded"
        assert data["checks"]["electrs"]["status"] in ["error", "timeout"]
        assert data["checks"]["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint_latency_tracking(client):
    """
    Test that health endpoint tracks service latency correctly.

    Expected:
    - latency_ms present for successful checks
    - latency_ms is a positive float
    """
    with (
        patch("api.main.check_electrs_connectivity") as mock_electrs,
        patch("api.main.check_mempool_backend") as mock_mempool,
        patch("api.main.get_db_connection") as mock_db,
    ):
        # Mock all services with latency
        mock_electrs.return_value = AsyncMock(
            status="ok", latency_ms=12.34, last_success="2025-11-18T10:00:00"
        )
        mock_mempool.return_value = AsyncMock(
            status="ok", latency_ms=45.67, last_success="2025-11-18T10:00:00"
        )
        mock_db_conn = MagicMock()
        mock_db_conn.execute.return_value.fetchone.return_value = (1,)
        mock_db_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value = mock_db_conn

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Verify latency tracking
        assert data["checks"]["electrs"]["latency_ms"] == 12.34
        assert data["checks"]["mempool_backend"]["latency_ms"] == 45.67
        assert data["checks"]["database"]["latency_ms"] is not None
        assert data["checks"]["database"]["latency_ms"] > 0


# =============================================================================
# Task 2: Correlation ID Middleware Tests
# =============================================================================


def test_correlation_id_auto_generated(client):
    """
    Test that correlation_id is auto-generated when not provided.

    Expected:
    - X-Correlation-ID header in response
    - Header value is a valid UUID
    """
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers

    # Verify it's a valid UUID
    correlation_id = response.headers["X-Correlation-ID"]
    try:
        uuid_obj = uuid.UUID(correlation_id)
        assert str(uuid_obj) == correlation_id  # Valid UUID format
    except ValueError:
        pytest.fail(f"Invalid UUID format: {correlation_id}")


def test_correlation_id_preserved_from_request(client):
    """
    Test that correlation_id from request header is preserved.

    Expected:
    - X-Correlation-ID in response matches request
    """
    test_correlation_id = "test-correlation-123-abc"

    response = client.get("/health", headers={"X-Correlation-ID": test_correlation_id})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == test_correlation_id


def test_correlation_id_different_across_requests(client):
    """
    Test that different requests get different auto-generated correlation_ids.

    Expected:
    - correlation_id1 != correlation_id2
    """
    response1 = client.get("/health")
    response2 = client.get("/health")

    correlation_id1 = response1.headers["X-Correlation-ID"]
    correlation_id2 = response2.headers["X-Correlation-ID"]

    assert correlation_id1 != correlation_id2


# =============================================================================
# Error Path Tests (Critical for Coverage)
# =============================================================================


@pytest.mark.asyncio
async def test_health_endpoint_handles_malformed_db_response(client):
    """
    Test /health endpoint handles malformed database responses gracefully.

    Expected:
    - Does not crash
    - Returns error status for database
    """
    with (
        patch("api.main.check_electrs_connectivity") as mock_electrs,
        patch("api.main.check_mempool_backend") as mock_mempool,
        patch("api.main.get_db_connection") as mock_db,
    ):
        # Mock healthy external services
        mock_electrs.return_value = AsyncMock(status="ok", latency_ms=15.2)
        mock_mempool.return_value = AsyncMock(status="ok", latency_ms=22.5)

        # Mock database returning unexpected data
        mock_db_conn = MagicMock()
        mock_db_conn.execute.return_value.fetchone.side_effect = TypeError(
            "Unexpected type"
        )
        mock_db.return_value = mock_db_conn

        response = client.get("/health")

        # Should not crash, but report error
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["degraded", "unhealthy"]
        assert data["checks"]["database"]["status"] == "error"


def test_health_endpoint_concurrent_requests(client):
    """
    Test that multiple concurrent requests to /health work correctly.

    Expected:
    - All requests succeed
    - Each gets unique correlation_id
    """
    import concurrent.futures

    def make_request():
        response = client.get("/health")
        return response.status_code, response.headers.get("X-Correlation-ID")

    # Make 10 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(10)]
        results = [f.result() for f in futures]

    # All requests should succeed
    assert all(status == 200 for status, _ in results)

    # All correlation IDs should be unique
    correlation_ids = [cid for _, cid in results]
    assert len(correlation_ids) == len(set(correlation_ids))  # No duplicates


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


def test_health_endpoint_backward_compatibility(client):
    """
    Test that enhanced /health endpoint maintains backward compatibility.

    Expected:
    - Legacy fields still present: database, uptime_seconds
    - New fields added: checks, timestamp
    """
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Legacy fields
    assert "database" in data  # Old format
    assert "uptime_seconds" in data
    assert "started_at" in data

    # New fields
    assert "checks" in data
    assert "timestamp" in data

    # Verify data types
    assert isinstance(data["uptime_seconds"], (int, float))
    assert isinstance(data["checks"], dict)
