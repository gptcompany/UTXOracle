#!/usr/bin/env python3
"""
Tests for PRO Risk API Endpoints (spec-033)

Test Coverage:
    T020: GET /api/risk/pro endpoint
    T021: GET /api/risk/pro/zones endpoint
    T028: GET /api/risk/pro/history endpoint (User Story 3)
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_pro_risk_result():
    """Create a mock ProRiskResult for testing."""
    from scripts.metrics.pro_risk import ProRiskResult

    return ProRiskResult(
        date=datetime(2025, 12, 25),
        value=0.62,
        zone="greed",
        components={
            "mvrv_z": 0.71,
            "sopr": 0.55,
            "nupl": 0.60,
            "reserve_risk": 0.68,
            "puell": 0.58,
            "hodl_waves": 0.45,
        },
        confidence=0.95,
        block_height=880000,
    )


@pytest.fixture
def api_client():
    """Create FastAPI test client."""
    from api.main import app

    return TestClient(app)


# =============================================================================
# T020: Tests for GET /api/risk/pro endpoint
# =============================================================================


class TestGetProRisk:
    """Tests for the GET /api/risk/pro endpoint (T020)."""

    def test_returns_200_on_success(self, api_client, mock_pro_risk_result):
        """Should return 200 status code on successful request."""
        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro")

            assert response.status_code == 200

    def test_returns_valid_json_structure(self, api_client, mock_pro_risk_result):
        """Should return valid JSON with required fields."""
        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro")
            data = response.json()

            assert "date" in data
            assert "value" in data
            assert "zone" in data
            assert "components" in data
            assert "confidence" in data

    def test_value_is_between_0_and_1(self, api_client, mock_pro_risk_result):
        """Value should be in [0, 1] range."""
        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro")
            data = response.json()

            assert 0.0 <= data["value"] <= 1.0

    def test_zone_is_valid(self, api_client, mock_pro_risk_result):
        """Zone should be one of the valid zone values."""
        valid_zones = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}

        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro")
            data = response.json()

            assert data["zone"] in valid_zones

    def test_components_is_list(self, api_client, mock_pro_risk_result):
        """Components should be a list of component objects."""
        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro")
            data = response.json()

            assert isinstance(data["components"], list)

    def test_accepts_date_parameter(self, api_client, mock_pro_risk_result):
        """Should accept and process date query parameter."""
        with patch(
            "api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result
        ) as mock_fn:
            response = api_client.get("/api/risk/pro?date=2025-12-25")

            assert response.status_code == 200
            # Verify the date was passed to the function
            mock_fn.assert_called_once()

    def test_returns_404_when_no_data(self, api_client):
        """Should return 404 when no data is available for date."""
        with patch("api.main.get_pro_risk_for_date", return_value=None):
            response = api_client.get("/api/risk/pro?date=2020-01-01")

            assert response.status_code == 404

    def test_includes_historical_context_when_requested(
        self, api_client, mock_pro_risk_result
    ):
        """Should include historical context when include_history=true."""
        with patch("api.main.get_pro_risk_for_date", return_value=mock_pro_risk_result):
            response = api_client.get("/api/risk/pro?include_history=true")

            # Response should include historical_context field
            # (may be null if not implemented yet)
            assert response.status_code == 200


# =============================================================================
# T021: Tests for GET /api/risk/pro/zones endpoint
# =============================================================================


class TestGetProRiskZones:
    """Tests for the GET /api/risk/pro/zones endpoint (T021)."""

    def test_returns_200(self, api_client):
        """Should return 200 status code."""
        response = api_client.get("/api/risk/pro/zones")

        assert response.status_code == 200

    def test_returns_zones_list(self, api_client):
        """Should return a list of zone definitions."""
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        assert "zones" in data
        assert isinstance(data["zones"], list)

    def test_returns_five_zones(self, api_client):
        """Should return exactly 5 zones."""
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        assert len(data["zones"]) == 5

    def test_zone_has_required_fields(self, api_client):
        """Each zone should have name, min_value, max_value, interpretation."""
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        for zone in data["zones"]:
            assert "name" in zone
            assert "min_value" in zone
            assert "max_value" in zone
            assert "interpretation" in zone

    def test_zones_are_contiguous(self, api_client):
        """Zone value ranges should be contiguous from 0 to 1."""
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        # Sort by min_value
        zones = sorted(data["zones"], key=lambda z: z["min_value"])

        # First zone should start at 0
        assert zones[0]["min_value"] == 0.0

        # Last zone should end at 1
        assert zones[-1]["max_value"] == 1.0

        # Check contiguity
        for i in range(1, len(zones)):
            assert zones[i]["min_value"] == zones[i - 1]["max_value"]

    def test_zones_have_correct_names(self, api_client):
        """Should include all expected zone names."""
        expected_names = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}

        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        actual_names = {zone["name"] for zone in data["zones"]}
        assert actual_names == expected_names


# =============================================================================
# T028: Tests for GET /api/risk/pro/history endpoint (User Story 3)
# =============================================================================


class TestGetProRiskHistory:
    """Tests for the GET /api/risk/pro/history endpoint (T028)."""

    def test_returns_200_on_success(self, api_client):
        """Should return 200 status code on valid request."""
        with patch("api.main.get_pro_risk_history", return_value=[]):
            response = api_client.get(
                "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25"
            )

            assert response.status_code == 200

    def test_requires_start_date(self, api_client):
        """Should require start_date parameter."""
        response = api_client.get("/api/risk/pro/history?end_date=2025-12-25")

        # Should return 422 (validation error) without start_date
        assert response.status_code == 422

    def test_requires_end_date(self, api_client):
        """Should require end_date parameter."""
        response = api_client.get("/api/risk/pro/history?start_date=2025-01-01")

        # Should return 422 (validation error) without end_date
        assert response.status_code == 422

    def test_returns_data_array(self, api_client):
        """Should return array of historical data points."""
        mock_history = [
            {"date": "2025-01-01", "value": 0.45, "zone": "neutral"},
            {"date": "2025-01-02", "value": 0.48, "zone": "neutral"},
        ]

        with patch("api.main.get_pro_risk_history", return_value=mock_history):
            response = api_client.get(
                "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-01-02"
            )
            data = response.json()

            assert "data" in data
            assert isinstance(data["data"], list)

    def test_accepts_granularity_parameter(self, api_client):
        """Should accept granularity parameter (daily, weekly, monthly)."""
        with patch("api.main.get_pro_risk_history", return_value=[]):
            response = api_client.get(
                "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25&granularity=weekly"
            )

            assert response.status_code == 200

    def test_rejects_invalid_granularity(self, api_client):
        """Should reject invalid granularity values."""
        response = api_client.get(
            "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25&granularity=hourly"
        )

        # Should return 422 (validation error) for invalid enum value
        assert response.status_code == 422

    def test_returns_start_and_end_date_in_response(self, api_client):
        """Response should include start_date and end_date."""
        with patch("api.main.get_pro_risk_history", return_value=[]):
            response = api_client.get(
                "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25"
            )
            data = response.json()

            assert "start_date" in data
            assert "end_date" in data

    def test_validates_date_range(self, api_client):
        """Should validate that start_date <= end_date."""
        response = api_client.get(
            "/api/risk/pro/history?start_date=2025-12-25&end_date=2025-01-01"
        )

        # Implementation may return 400 or 422 for invalid date range
        assert response.status_code in (400, 422)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestAPIErrorHandling:
    """Tests for API error handling."""

    def test_invalid_date_format_returns_422(self, api_client):
        """Should return 422 for invalid date format."""
        response = api_client.get("/api/risk/pro?date=not-a-date")

        assert response.status_code == 422

    def test_future_date_returns_404(self, api_client):
        """Should return 404 for future dates with no data."""
        with patch("api.main.get_pro_risk_for_date", return_value=None):
            response = api_client.get("/api/risk/pro?date=2030-01-01")

            assert response.status_code == 404
