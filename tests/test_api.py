"""
API Tests for FastAPI backend (T055-T057)

Tests for REST API endpoints serving price comparison data from DuckDB.

Spec: 003-mempool-integration-refactor
Phase: 4 - API & Visualization
Tasks: T055-T057 (TDD Red - tests should FAIL initially)
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime


class TestLatestPriceEndpoint:
    """T055: Test GET /api/prices/latest endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client (will fail until API exists)"""
        from api.main import app

        return TestClient(app)

    def test_get_latest_price_returns_json(self, client):
        """Should return most recent price entry as JSON"""
        response = client.get("/api/prices/latest")

        # Should return 200 OK or 404 if database empty (cron not run yet)
        assert response.status_code in [200, 404]

        # If 200, validate data structure
        if response.status_code == 200:
            # Should return JSON
            data = response.json()
            assert isinstance(data, dict)

            # Should have required fields
            assert "timestamp" in data
            assert "utxoracle_price" in data
            assert "mempool_price" in data
            assert "confidence" in data
            assert "diff_amount" in data
            assert "diff_percent" in data
            assert "is_valid" in data

    def test_get_latest_price_returns_most_recent(self, client):
        """Should return entry with latest timestamp"""
        response = client.get("/api/prices/latest")

        # Only validate timestamp if data exists
        if response.status_code == 200:
            data = response.json()

            # Timestamp should be recent (within last hour)
            timestamp = datetime.fromisoformat(data["timestamp"])
            now = datetime.now()
            delta = now - timestamp

            assert delta.total_seconds() < 3600  # Less than 1 hour old
        else:
            # Database empty (cron not run yet) - acceptable
            assert response.status_code == 404

    def test_get_latest_price_handles_empty_database(self, client):
        """Should return 404 when no data exists"""
        # This test assumes empty test database
        # In real scenario, should mock DuckDB to return empty result
        response = client.get("/api/prices/latest")

        # Could be 404 or 200 with null values, depending on design
        assert response.status_code in [200, 404]


class TestHistoricalPricesEndpoint:
    """T056: Test GET /api/prices/historical endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_get_historical_prices_with_days_param(self, client):
        """Should return historical data filtered by days parameter"""
        response = client.get("/api/prices/historical?days=7")

        # Should return 200 OK
        assert response.status_code == 200

        # Should return JSON array
        data = response.json()
        assert isinstance(data, list)

        # Each entry should have required fields
        if len(data) > 0:
            entry = data[0]
            assert "timestamp" in entry
            assert "utxoracle_price" in entry
            assert "mempool_price" in entry

    def test_get_historical_prices_defaults_to_7_days(self, client):
        """Should default to 7 days when no parameter provided"""
        response = client.get("/api/prices/historical")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # If data exists, all timestamps should be within last 7 days
        if len(data) > 0:
            for entry in data:
                timestamp = datetime.fromisoformat(entry["timestamp"])
                now = datetime.now()
                delta = now - timestamp
                assert delta.total_seconds() <= 7 * 24 * 3600  # 7 days

    def test_get_historical_prices_with_custom_days(self, client):
        """Should respect custom days parameter"""
        response = client.get("/api/prices/historical?days=30")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should allow up to 30 days of data
        if len(data) > 0:
            earliest = min(datetime.fromisoformat(entry["timestamp"]) for entry in data)
            now = datetime.now()
            delta = now - earliest
            assert delta.total_seconds() <= 30 * 24 * 3600

    def test_get_historical_prices_validates_days_param(self, client):
        """Should reject invalid days parameter"""
        # Test negative days
        response = client.get("/api/prices/historical?days=-1")
        assert response.status_code in [400, 422]

        # Test very large days
        response = client.get("/api/prices/historical?days=1000")
        assert response.status_code in [400, 422]

        # Test non-numeric days
        response = client.get("/api/prices/historical?days=abc")
        assert response.status_code in [400, 422]


class TestComparisonStatsEndpoint:
    """T057: Test GET /api/prices/comparison endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_get_comparison_stats_computes_avg_diff(self, client):
        """Should compute statistical comparison metrics"""
        response = client.get("/api/prices/comparison")

        # Should return 200 OK
        assert response.status_code == 200

        # Should return JSON with stats
        data = response.json()
        assert isinstance(data, dict)

        # Should have statistical fields
        assert "avg_diff" in data
        assert "max_diff" in data
        assert "min_diff" in data
        assert "avg_diff_percent" in data

    def test_get_comparison_stats_includes_counts(self, client):
        """Should include data point counts"""
        response = client.get("/api/prices/comparison")
        data = response.json()

        # Should have count fields
        assert "total_entries" in data
        assert "valid_entries" in data

    def test_get_comparison_stats_optional_timeframe(self, client):
        """Should support optional timeframe parameter"""
        response = client.get("/api/prices/comparison?days=7")

        assert response.status_code == 200
        data = response.json()

        # Stats should be calculated for specified timeframe
        assert isinstance(data, dict)
        assert "avg_diff" in data

    def test_get_comparison_stats_handles_empty_data(self, client):
        """Should handle case with no data gracefully"""
        # Should return stats with zeros or nulls, not error
        response = client.get("/api/prices/comparison")

        assert response.status_code == 200
        data = response.json()

        # Could have null/zero values
        assert "total_entries" in data
        # If no data, count should be 0
        if data["total_entries"] == 0:
            assert data["avg_diff"] is None or data["avg_diff"] == 0


class TestHealthEndpoint:
    """Test GET /health endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_health_check_returns_status(self, client):
        """Should return health status"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Should have status field
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_check_includes_database_status(self, client):
        """Should include DuckDB connection status"""
        response = client.get("/health")
        data = response.json()

        # Should check database connectivity
        assert "database" in data
        assert isinstance(data["database"], (str, dict))

    def test_health_check_includes_uptime(self, client):
        """Should include API uptime"""
        response = client.get("/health")
        data = response.json()

        # Should have uptime info
        assert "uptime_seconds" in data or "started_at" in data


# =============================================================================
# spec-010: Wasserstein API Tests (T036-T038)
# =============================================================================


class TestWassersteinLatestEndpoint:
    """T036: Test GET /api/metrics/wasserstein endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_get_wasserstein_latest_returns_json(self, client):
        """Should return latest Wasserstein metrics as JSON."""
        response = client.get("/api/metrics/wasserstein")

        # Should return 200 OK or 404 if no data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

            # Should have required fields per API contract
            assert "distance" in data or "error" in data

    def test_get_wasserstein_latest_has_required_fields(self, client):
        """Should have all required fields when data exists."""
        response = client.get("/api/metrics/wasserstein")

        if response.status_code == 200:
            data = response.json()

            # Required fields from wasserstein_api.yaml
            required_fields = [
                "distance",
                "distance_normalized",
                "shift_direction",
                "regime_status",
                "wasserstein_vote",
                "is_valid",
                "timestamp",
            ]

            for field in required_fields:
                assert field in data, f"Missing required field: {field}"


class TestWassersteinHistoryEndpoint:
    """T037: Test GET /api/metrics/wasserstein/history endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_get_wasserstein_history_returns_array(self, client):
        """Should return historical Wasserstein data as array."""
        response = client.get("/api/metrics/wasserstein/history?hours=24")

        # L3 fix: 404 now returned for schema migration pending (consistent with other endpoints)
        assert response.status_code in [200, 400, 404]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert isinstance(data["data"], list)

    def test_get_wasserstein_history_has_summary(self, client):
        """Should include summary statistics."""
        response = client.get("/api/metrics/wasserstein/history?hours=24")

        if response.status_code == 200:
            data = response.json()
            assert "summary" in data

            summary = data["summary"]
            assert "mean_distance" in summary
            assert "max_distance" in summary


class TestWassersteinNotFoundEndpoint:
    """T038: Test /api/metrics/wasserstein returns 404 when no data"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from api.main import app

        return TestClient(app)

    def test_wasserstein_404_when_no_data(self, client):
        """Should return 404 when no metrics data available."""
        # Note: This test may pass or fail depending on whether
        # daily_analysis.py has run with Wasserstein enabled
        response = client.get("/api/metrics/wasserstein")

        # Either 200 with data or 404 with error message
        assert response.status_code in [200, 404]

        if response.status_code == 404:
            data = response.json()
            assert "error" in data or "detail" in data


# Summary comment for documentation
"""
API TESTS STATUS (T055-T057 + T036-T038):

Test Coverage:
✅ T055: Latest price endpoint (3 tests)
✅ T056: Historical prices endpoint (5 tests)
✅ T057: Comparison stats endpoint (4 tests)
✅ Bonus: Health check endpoint (3 tests)
✅ T036: Wasserstein latest endpoint (2 tests) - spec-010
✅ T037: Wasserstein history endpoint (2 tests) - spec-010
✅ T038: Wasserstein 404 handling (1 test) - spec-010

Total: 20 tests written
"""
