#!/usr/bin/env python3
"""
Tests for PRO Risk API endpoints after spec-048 hardening.

Test Coverage:
    - `/api/risk/pro` is runtime-demoted
    - `/api/risk/pro/history` is runtime-demoted
    - `/api/risk/pro/zones` remains available as static metadata
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client():
    """Create FastAPI test client."""
    from api.main import app

    return TestClient(app)


class TestGetProRisk:
    """Tests for the runtime-demoted `/api/risk/pro` endpoint."""

    def test_returns_501_for_current_route(self, api_client):
        response = api_client.get("/api/risk/pro")

        assert response.status_code == 501
        assert "runtime-demoted" in response.json()["detail"]

    def test_accepts_valid_date_but_still_returns_501(self, api_client):
        response = api_client.get("/api/risk/pro?date=2025-12-25")

        assert response.status_code == 501
        assert "component metric wiring" in response.json()["detail"]

    def test_invalid_date_format_still_returns_422(self, api_client):
        response = api_client.get("/api/risk/pro?date=not-a-date")

        assert response.status_code == 422


class TestGetProRiskZones:
    """Tests for the static `/api/risk/pro/zones` endpoint."""

    def test_returns_200(self, api_client):
        response = api_client.get("/api/risk/pro/zones")

        assert response.status_code == 200

    def test_returns_zones_list(self, api_client):
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        assert "zones" in data
        assert isinstance(data["zones"], list)
        assert len(data["zones"]) == 5

    def test_zones_have_expected_names(self, api_client):
        response = api_client.get("/api/risk/pro/zones")
        data = response.json()

        actual_names = {zone["name"] for zone in data["zones"]}
        assert actual_names == {
            "extreme_fear",
            "fear",
            "neutral",
            "greed",
            "extreme_greed",
        }


class TestGetProRiskHistory:
    """Tests for the runtime-demoted `/api/risk/pro/history` endpoint."""

    def test_returns_501_for_valid_request(self, api_client):
        response = api_client.get(
            "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25"
        )

        assert response.status_code == 501
        assert "runtime-demoted" in response.json()["detail"]

    def test_requires_start_date(self, api_client):
        response = api_client.get("/api/risk/pro/history?end_date=2025-12-25")

        assert response.status_code == 422

    def test_requires_end_date(self, api_client):
        response = api_client.get("/api/risk/pro/history?start_date=2025-01-01")

        assert response.status_code == 422

    def test_rejects_invalid_granularity(self, api_client):
        response = api_client.get(
            "/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25&granularity=hourly"
        )

        assert response.status_code == 422

    def test_validates_date_range_before_demotion(self, api_client):
        response = api_client.get(
            "/api/risk/pro/history?start_date=2025-12-25&end_date=2025-01-01"
        )

        assert response.status_code == 400
