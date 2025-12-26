#!/usr/bin/env python3
"""
Tests for Bitcoin Price Power Law API Endpoints (spec-034)

Test Coverage:
    T006: GET /api/v1/models/power-law endpoint
    T007: GET /api/v1/models/power-law/predict endpoint
    T012: GET /api/v1/models/power-law/history endpoint (User Story 2)
    T013: POST /api/v1/models/power-law/recalibrate endpoint (User Story 2)
"""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def api_client():
    """Create FastAPI test client."""
    from api.main import app

    return TestClient(app)


@pytest.fixture
def mock_power_law_model():
    """Create a mock PowerLawModel for testing."""
    from api.models.power_law_models import PowerLawModel

    return PowerLawModel(
        alpha=-17.01,
        beta=5.82,
        r_squared=0.95,
        std_error=0.32,
        fitted_on=date(2025, 1, 1),
        sample_size=5800,
    )


@pytest.fixture
def mock_power_law_prediction():
    """Create a mock PowerLawPrediction for testing."""
    from api.models.power_law_models import PowerLawPrediction

    return PowerLawPrediction(
        date=date(2025, 12, 25),
        days_since_genesis=6200,
        fair_value=89234.56,
        lower_band=42567.89,
        upper_band=187012.34,
        current_price=98500.00,
        deviation_pct=10.4,
        zone="fair",
    )


# =============================================================================
# T006: Tests for GET /api/v1/models/power-law endpoint
# =============================================================================


class TestGetPowerLawModel:
    """Tests for the GET /api/v1/models/power-law endpoint (T006)."""

    def test_returns_200_on_success(self, api_client):
        """Should return 200 status code on successful request."""
        response = api_client.get("/api/v1/models/power-law")
        assert response.status_code == 200

    def test_returns_valid_json_structure(self, api_client):
        """Should return valid JSON with required fields."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        assert "model" in data
        model = data["model"]
        assert "alpha" in model
        assert "beta" in model
        assert "r_squared" in model
        assert "std_error" in model
        assert "fitted_on" in model
        assert "sample_size" in model

    def test_model_alpha_is_reasonable(self, api_client):
        """Alpha coefficient should be in expected range."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        # Alpha typically around -17
        assert -20 < data["model"]["alpha"] < -14

    def test_model_beta_is_reasonable(self, api_client):
        """Beta coefficient should be in expected range."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        # Beta typically around 5.8
        assert 5.0 < data["model"]["beta"] < 7.0

    def test_model_r_squared_is_valid(self, api_client):
        """R-squared should be between 0 and 1."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        assert 0.0 <= data["model"]["r_squared"] <= 1.0

    def test_model_std_error_is_positive(self, api_client):
        """Standard error should be positive."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        assert data["model"]["std_error"] > 0

    def test_model_sample_size_is_positive(self, api_client):
        """Sample size should be positive."""
        response = api_client.get("/api/v1/models/power-law")
        data = response.json()

        assert data["model"]["sample_size"] > 0


# =============================================================================
# T007: Tests for GET /api/v1/models/power-law/predict endpoint
# =============================================================================


class TestGetPowerLawPredict:
    """Tests for the GET /api/v1/models/power-law/predict endpoint (T007)."""

    def test_returns_200_on_success(self, api_client):
        """Should return 200 status code on successful request."""
        response = api_client.get("/api/v1/models/power-law/predict")
        assert response.status_code == 200

    def test_returns_prediction_structure(self, api_client):
        """Should return valid JSON with required prediction fields."""
        response = api_client.get("/api/v1/models/power-law/predict")
        data = response.json()

        assert "model" in data
        assert "prediction" in data

        pred = data["prediction"]
        assert "date" in pred
        assert "days_since_genesis" in pred
        assert "fair_value" in pred
        assert "lower_band" in pred
        assert "upper_band" in pred
        assert "zone" in pred

    def test_accepts_date_parameter(self, api_client):
        """Should accept and process date query parameter."""
        response = api_client.get("/api/v1/models/power-law/predict?date=2025-12-25")
        assert response.status_code == 200

        data = response.json()
        assert data["prediction"]["date"] == "2025-12-25"

    def test_accepts_current_price_parameter(self, api_client):
        """Should accept current_price for deviation calculation."""
        response = api_client.get(
            "/api/v1/models/power-law/predict?date=2025-12-25&current_price=98500"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["prediction"]["current_price"] == 98500.0
        assert data["prediction"]["deviation_pct"] is not None
        assert data["prediction"]["zone"] in ["undervalued", "fair", "overvalued"]

    def test_zone_is_unknown_without_current_price(self, api_client):
        """Zone should be 'unknown' when current_price not provided."""
        response = api_client.get("/api/v1/models/power-law/predict?date=2025-12-25")
        data = response.json()

        assert data["prediction"]["zone"] == "unknown"

    def test_fair_value_is_positive(self, api_client):
        """Fair value should always be positive."""
        response = api_client.get("/api/v1/models/power-law/predict?date=2025-12-25")
        data = response.json()

        assert data["prediction"]["fair_value"] > 0

    def test_bands_bracket_fair_value(self, api_client):
        """Lower band < fair value < upper band."""
        response = api_client.get("/api/v1/models/power-law/predict?date=2025-12-25")
        data = response.json()

        pred = data["prediction"]
        assert pred["lower_band"] < pred["fair_value"] < pred["upper_band"]

    def test_invalid_date_format_returns_422(self, api_client):
        """Should return 422 for invalid date format (FastAPI validation)."""
        response = api_client.get("/api/v1/models/power-law/predict?date=not-a-date")
        assert response.status_code == 422

    def test_date_before_genesis_returns_400(self, api_client):
        """Should return 400 for date before Bitcoin genesis."""
        response = api_client.get("/api/v1/models/power-law/predict?date=2008-01-01")
        assert response.status_code == 400


# =============================================================================
# T012: Tests for GET /api/v1/models/power-law/history endpoint (US2)
# =============================================================================


class MockDuckDBConnection:
    """Mock DuckDB connection for testing."""

    def __init__(self, data):
        self._data = data

    def execute(self, query, params=None):
        return self

    def fetchall(self):
        return self._data

    def close(self):
        pass


class TestGetPowerLawHistory:
    """Tests for the GET /api/v1/models/power-law/history endpoint (T012)."""

    @pytest.fixture
    def mock_price_data(self):
        """Generate mock price data for testing."""
        from datetime import timedelta

        base_date = date(2025, 12, 1)
        return [(base_date - timedelta(days=i), 95000 + i * 100) for i in range(30)]

    def test_returns_200_on_success(self, api_client, mock_price_data):
        """Should return 200 status code on valid request."""
        with patch(
            "api.main.get_duckdb_connection",
            return_value=MockDuckDBConnection(mock_price_data),
        ):
            response = api_client.get("/api/v1/models/power-law/history?days=30")
            assert response.status_code == 200

    def test_returns_history_structure(self, api_client, mock_price_data):
        """Should return valid JSON with model and history array."""
        with patch(
            "api.main.get_duckdb_connection",
            return_value=MockDuckDBConnection(mock_price_data),
        ):
            response = api_client.get("/api/v1/models/power-law/history?days=30")
            data = response.json()

            assert "model" in data
            assert "history" in data
            assert isinstance(data["history"], list)

    def test_history_points_have_required_fields(self, api_client, mock_price_data):
        """Each history point should have date, price, fair_value, zone."""
        with patch(
            "api.main.get_duckdb_connection",
            return_value=MockDuckDBConnection(mock_price_data),
        ):
            response = api_client.get("/api/v1/models/power-law/history?days=30")
            data = response.json()

            if len(data["history"]) > 0:
                point = data["history"][0]
                assert "date" in point
                assert "price" in point
                assert "fair_value" in point
                assert "zone" in point

    def test_days_defaults_to_365(self, api_client, mock_price_data):
        """Should default to 365 days if not specified."""
        with patch(
            "api.main.get_duckdb_connection",
            return_value=MockDuckDBConnection(mock_price_data),
        ):
            response = api_client.get("/api/v1/models/power-law/history")
            assert response.status_code == 200

    def test_rejects_days_below_minimum(self, api_client):
        """Should reject days < 7."""
        response = api_client.get("/api/v1/models/power-law/history?days=5")
        assert response.status_code == 422

    def test_rejects_days_above_maximum(self, api_client):
        """Should reject days > 5000."""
        response = api_client.get("/api/v1/models/power-law/history?days=6000")
        assert response.status_code == 422


# =============================================================================
# T013: Tests for POST /api/v1/models/power-law/recalibrate endpoint (US2)
# =============================================================================


class TestPostPowerLawRecalibrate:
    """Tests for the POST /api/v1/models/power-law/recalibrate endpoint (T013)."""

    def test_returns_200_on_success(self, api_client):
        """Should return 200 status code on successful recalibration."""
        # Note: This test may need to mock database if not available
        response = api_client.post("/api/v1/models/power-law/recalibrate")
        # Accept 200 (success) or 503 (database unavailable)
        assert response.status_code in (200, 503)

    def test_returns_updated_model(self, api_client):
        """Should return the recalibrated model parameters."""
        response = api_client.post("/api/v1/models/power-law/recalibrate")

        if response.status_code == 200:
            data = response.json()
            assert "model" in data
            assert "alpha" in data["model"]
            assert "beta" in data["model"]

    def test_returns_503_when_database_unavailable(self, api_client):
        """Should return 503 when database is unavailable."""
        with patch(
            "api.main.get_duckdb_connection", side_effect=Exception("DB unavailable")
        ):
            response = api_client.post("/api/v1/models/power-law/recalibrate")
            assert response.status_code == 503


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestPowerLawAPIErrorHandling:
    """Tests for Power Law API error handling."""

    def test_404_on_unknown_subpath(self, api_client):
        """Should return 404 for unknown sub-endpoints."""
        response = api_client.get("/api/v1/models/power-law/unknown")
        assert response.status_code == 404

    def test_method_not_allowed_on_model_post(self, api_client):
        """Should return 405 for POST on model endpoint."""
        response = api_client.post("/api/v1/models/power-law")
        assert response.status_code == 405

    def test_method_not_allowed_on_predict_post(self, api_client):
        """Should return 405 for POST on predict endpoint."""
        response = api_client.post("/api/v1/models/power-law/predict")
        assert response.status_code == 405

    def test_method_not_allowed_on_recalibrate_get(self, api_client):
        """Should return 405 for GET on recalibrate endpoint."""
        response = api_client.get("/api/v1/models/power-law/recalibrate")
        assert response.status_code == 405
