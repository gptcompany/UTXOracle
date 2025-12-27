"""
API integration tests for price models framework (spec-036 US6).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_api_models.py -v
"""


import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client for API."""
    from api.main import app

    return TestClient(app)


class TestListModels:
    """Tests for GET /api/v1/models endpoint."""

    def test_list_models_returns_list(self, client):
        """GET /models returns list of available models."""
        response = client.get("/api/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4  # At least 4 built-in models

    def test_list_models_includes_builtin_models(self, client):
        """GET /models includes Power Law, Stock-to-Flow, Thermocap, UTXOracle."""
        response = client.get("/api/v1/models")

        data = response.json()
        names = [m["name"] for m in data]

        assert "Power Law" in names
        assert "Stock-to-Flow" in names
        assert "Thermocap" in names
        assert "UTXOracle" in names

    def test_list_models_model_info_format(self, client):
        """GET /models returns proper ModelInfo format."""
        response = client.get("/api/v1/models")

        data = response.json()
        for model in data:
            assert "name" in model
            assert "description" in model
            assert "required_data" in model
            assert "is_fitted" in model


class TestGetModelPrediction:
    """Tests for GET /api/v1/models/{name}/predict endpoint."""

    def test_get_prediction_power_law(self, client):
        """GET /models/power-law/predict returns prediction."""
        response = client.get("/api/v1/models/power-law/predict")

        assert response.status_code == 200
        data = response.json()
        assert data["model_name"] == "Power Law"
        assert data["predicted_price"] > 0
        assert "confidence_interval" in data

    def test_get_prediction_with_date(self, client):
        """GET /models/power-law/predict?date= returns prediction for specific date."""
        response = client.get(
            "/api/v1/models/power-law/predict",
            params={"date": "2025-12-27"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2025-12-27"

    def test_get_prediction_unknown_model(self, client):
        """GET /models/unknown/predict returns 404."""
        response = client.get("/api/v1/models/unknown-model/predict")

        assert response.status_code == 404

    def test_get_prediction_stock_to_flow(self, client):
        """GET /models/stock-to-flow/predict returns prediction."""
        response = client.get("/api/v1/models/stock-to-flow/predict")

        assert response.status_code == 200
        data = response.json()
        assert data["model_name"] == "Stock-to-Flow"


class TestCreateEnsemble:
    """Tests for POST /api/v1/models/ensemble endpoint."""

    def test_create_ensemble_prediction(self, client):
        """POST /models/ensemble returns ensemble prediction."""
        response = client.post(
            "/api/v1/models/ensemble",
            json={
                "models": ["Power Law", "Stock-to-Flow"],
                "weights": [0.5, 0.5],
                "aggregation": "weighted_avg",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["model_name"] == "Ensemble"
        assert data["predicted_price"] > 0

    def test_create_ensemble_with_date(self, client):
        """POST /models/ensemble with date parameter."""
        response = client.post(
            "/api/v1/models/ensemble",
            json={
                "models": ["Power Law", "Thermocap"],
                "weights": [0.6, 0.4],
                "aggregation": "median",
                "date": "2025-12-27",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2025-12-27"

    def test_create_ensemble_invalid_weights(self, client):
        """POST /models/ensemble with invalid weights returns 400."""
        response = client.post(
            "/api/v1/models/ensemble",
            json={
                "models": ["Power Law", "Stock-to-Flow"],
                "weights": [0.3, 0.3],  # Sum != 1.0
                "aggregation": "weighted_avg",
            },
        )

        assert response.status_code in [400, 422]


class TestRunBacktest:
    """Tests for GET /api/v1/models/backtest/{name} endpoint."""

    def test_run_backtest(self, client):
        """GET /models/backtest/power-law returns backtest results."""
        response = client.get("/api/v1/models/backtest/power-law")

        assert response.status_code == 200
        data = response.json()
        assert data["model_name"] == "Power Law"
        assert "metrics" in data
        assert "mae" in data["metrics"]
        assert "mape" in data["metrics"]

    def test_run_backtest_with_dates(self, client):
        """GET /models/backtest/power-law with date range."""
        response = client.get(
            "/api/v1/models/backtest/power-law",
            params={
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
            },
        )

        assert response.status_code == 200

    def test_run_backtest_unknown_model(self, client):
        """GET /models/backtest/unknown returns 404."""
        response = client.get("/api/v1/models/backtest/unknown-model")

        assert response.status_code == 404


class TestCompareModels:
    """Tests for GET /api/v1/models/compare endpoint."""

    def test_compare_models(self, client):
        """GET /models/compare returns comparison results."""
        response = client.get(
            "/api/v1/models/compare",
            params={"models": ["Power Law", "Stock-to-Flow"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "ranking" in data
        assert "best_model" in data
        assert "results" in data

    def test_compare_models_ranking_order(self, client):
        """GET /models/compare returns models ranked by MAPE."""
        response = client.get(
            "/api/v1/models/compare",
            params={"models": ["Power Law", "Stock-to-Flow", "Thermocap"]},
        )

        assert response.status_code == 200
        data = response.json()
        # Best model should be first in ranking
        assert data["best_model"] == data["ranking"][0]
