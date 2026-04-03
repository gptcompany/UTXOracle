from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.apps.live import app as live_app
from api.main import app as main_app


def _ts() -> datetime:
    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_prices_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/prices/latest")
        assert response.status_code == 200
        payload = response.json()
        assert payload["utxoracle_price"] == 85000.0


def test_metrics_latest_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/latest")
        assert response.status_code == 200
        assert response.json()["monte_carlo"]["action"] == "BUY"


def test_wave1_address_cohorts_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/address-cohorts")
        assert response.status_code == 200
        payload = response.json()
        assert "whale" in payload["cohorts"]
        assert payload["cohorts"]["whale"]["cost_basis"] == 45000.0


def test_wave1_wallet_waves_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/wallet-waves")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["bands"]) == 6
        assert any(band["band"] == "shrimp" for band in payload["bands"])


def test_wave1_absorption_rates_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/absorption-rates")
        assert response.status_code == 200
        payload = response.json()
        assert payload["window_days"] == 30
        assert payload["dominant_absorber"] == "whale"


def test_whale_promotion_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/whale/summary")
        assert response.status_code != 404


def test_duckdb_metrics_stay_off_8011(questdb_repo_mock):
    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/nupl")
        assert response.status_code == 404


def test_8001_migration_headers_wave1(questdb_repo_mock):
    main_app.state.questdb_repo = questdb_repo_mock
    with TestClient(main_app) as client:
        for route in [
            "/api/metrics/address-cohorts",
            "/api/metrics/wallet-waves",
            "/api/metrics/absorption-rates",
        ]:
            response = client.get(route)
            assert response.status_code != 404
            assert response.headers["X-UTXOracle-Migration-Hint"] == "Canonical production host is :8011"
            assert response.headers["Deprecation"] == "true"


def test_8011_inconsistent_snapshot_fail(questdb_repo_mock):
    questdb_repo_mock.get_address_cohorts_latest = AsyncMock(
        return_value=[
            {
                "block_height": 840000,
                "cohort": "whale",
                "ts": _ts(),
                "cost_basis": 1.0,
                "supply_btc": 1.0,
                "supply_pct": 1.0,
                "mvrv": 1.0,
                "address_count": 1,
                "current_price_usd": 1.0,
                "whale_retail_spread": 1.0,
                "whale_retail_mvrv_ratio": 1.0,
                "total_supply_btc": 1.0,
                "total_addresses": 1,
            },
            {
                "block_height": 840000,
                "cohort": "mid_tier",
                "ts": _ts(),
                "cost_basis": 1.0,
                "supply_btc": 1.0,
                "supply_pct": 1.0,
                "mvrv": 1.0,
                "address_count": 1,
                "current_price_usd": 1.0,
                "whale_retail_spread": 1.0,
                "whale_retail_mvrv_ratio": 1.0,
                "total_supply_btc": 1.0,
                "total_addresses": 1,
            },
            {
                "block_height": 839999,
                "cohort": "retail",
                "ts": _ts(),
                "cost_basis": 1.0,
                "supply_btc": 1.0,
                "supply_pct": 1.0,
                "mvrv": 1.0,
                "address_count": 1,
                "current_price_usd": 1.0,
                "whale_retail_spread": 1.0,
                "whale_retail_mvrv_ratio": 1.0,
                "total_supply_btc": 1.0,
                "total_addresses": 1,
            },
        ]
    )

    live_app.state.questdb_repo = questdb_repo_mock
    with TestClient(live_app) as client:
        response = client.get("/api/metrics/address-cohorts")
        assert response.status_code == 503
        assert "Inconsistent snapshot detected" in response.json()["detail"]
