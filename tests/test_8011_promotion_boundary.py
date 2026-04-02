import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from api.apps.live import app as live_app
from api.main import app as main_app
from api.questdb_repository import QuestDBRepository
from datetime import datetime, timezone

@pytest.fixture
def mock_questdb_repo():
    mock = MagicMock(spec=QuestDBRepository)
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    mock.get_latest_price_analysis = AsyncMock(
        return_value={
            "ts": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            "utxoracle_price": 85000.0,
            "exchange_price": 85100.0,
            "confidence": 0.92,
            "tx_count": 1800,
            "price_difference": -100.0,
            "avg_pct_diff": -0.12,
            "is_valid": True,
        }
    )
    mock.get_latest_metrics = AsyncMock(
        return_value={
            "ts": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            "signal_mean": 0.15,
            "signal_std": 0.05,
            "ci_lower": 0.05,
            "ci_upper": 0.25,
            "action": "BUY",
            "action_confidence": 0.85,
            "n_samples": 1000,
            "distribution_type": "unimodal",
            "block_height": 840000,
            "active_addresses_block": 15000,
            "active_addresses_24h": 850000,
            "unique_senders": 8000,
            "unique_receivers": 7000,
            "is_anomaly": False,
            "tx_count": 450000,
            "tx_volume_btc": 12000.5,
            "tx_volume_usd": 1020042500.0,
            "utxoracle_price_used": 85000.0,
            "low_confidence": False,
        }
    )
    mock.get_address_cohorts_latest = AsyncMock(
        return_value=[
            {
                "ts": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
                "cohort": "whale",
                "cost_basis": 45000.0,
                "supply_btc": 5000000.0,
                "supply_pct": 25.0,
                "mvrv": 1.8,
                "address_count": 2500,
                "block_height": 840000,
                "current_price_usd": 85000.0,
                "whale_retail_spread": -5000.0,
                "whale_retail_mvrv_ratio": 1.2,
                "total_supply_btc": 19700000.0,
                "total_addresses": 50000000,
            }
        ]
    )
    mock.get_wallet_waves_latest = AsyncMock(
        return_value=[
            {
                "ts": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
                "band": "shrimp",
                "supply_btc": 1000000.0,
                "supply_pct": 5.0,
                "address_count": 40000000,
                "avg_balance": 0.025,
                "block_height": 840000,
                "total_supply_btc": 19700000.0,
                "retail_supply_pct": 15.0,
                "institutional_supply_pct": 85.0,
                "address_count_total": 50000000,
                "null_address_btc": 500.0,
                "confidence": 0.95,
            }
        ]
    )
    mock.get_absorption_rates_latest = AsyncMock(
        return_value=[
            {
                "ts": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
                "band": "crab",
                "absorption_rate": 0.45,
                "supply_delta_btc": 500.0,
                "supply_start_btc": 150000.0,
                "supply_end_btc": 150500.0,
                "block_height": 840000,
                "window_days": 30,
                "mined_supply_btc": 13500.0,
                "dominant_absorber": "whale",
                "retail_absorption": 0.15,
                "institutional_absorption": 0.85,
                "confidence": 0.9,
                "has_historical_data": True,
            }
        ]
    )
    return mock

def test_prices_promotion_8011(mock_questdb_repo):
    """TEST: /api/prices/latest should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/prices/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["utxoracle_price"] == 85000.0

def test_metrics_latest_promotion_8011(mock_questdb_repo):
    """TEST: /api/metrics/latest should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["monte_carlo"]["action"] == "BUY"

def test_wave1_address_cohorts_promotion_8011(mock_questdb_repo):
    """TEST: Wave 1 /api/metrics/address-cohorts should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/address-cohorts")
    assert response.status_code == 200
    payload = response.json()
    assert "whale" in payload["cohorts"]
    assert payload["cohorts"]["whale"]["cost_basis"] == 45000.0

def test_wave1_wallet_waves_promotion_8011(mock_questdb_repo):
    """TEST: Wave 1 /api/metrics/wallet-waves should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/wallet-waves")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["bands"]) > 0
    assert payload["bands"][0]["band"] == "shrimp"

def test_wave1_absorption_rates_promotion_8011(mock_questdb_repo):
    """TEST: Wave 1 /api/metrics/absorption-rates should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/absorption-rates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["window_days"] == 30
    assert payload["dominant_absorber"] == "whale"

def test_whale_promotion_8011(mock_questdb_repo):
    """TEST: /api/whale/summary should be available on 8011."""
    # Note: whale routes don't strictly use questdb_repo in the same way but 
    # the endpoint requires the app to be set up.
    client = TestClient(live_app)
    response = client.get("/api/whale/summary")
    # If it's registered, it will try to hit DuckDB or QuestDB
    # We just want to see it's NOT a 404. 
    # Since we didn't mock the internal whale logic, it might 500, but not 404.
    assert response.status_code != 404

def test_duckdb_metrics_stay_off_8011(mock_questdb_repo):
    """GUARDRAIL: DuckDB-backed metrics like NUPL must stay off 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/nupl")
    assert response.status_code == 404

def test_8001_migration_headers_wave1(mock_questdb_repo):
    """TEST: Wave 1 routes on 8001 should have migration headers."""
    main_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(main_app)
    
    for route in ["/api/metrics/address-cohorts", "/api/metrics/wallet-waves", "/api/metrics/absorption-rates"]:
        response = client.get(route)
        assert response.status_code != 404
        assert response.headers.get("X-UTXOracle-Migration-Hint") == "Canonical production host is :8011"
        assert response.headers.get("Deprecation") == "true"
