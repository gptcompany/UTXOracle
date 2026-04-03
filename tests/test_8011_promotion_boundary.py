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
    
    # Address Cohorts: 3 cohorts required
    mock.get_address_cohorts_latest = AsyncMock(
        return_value=[
            {"block_height": 840000, "cohort": c, "ts": datetime.now(), "cost_basis": 45000.0, "supply_btc": 1.0, "supply_pct": 1.0, "mvrv": 1.0, "address_count": 1, "current_price_usd": 85000.0, "whale_retail_spread": 1.0, "whale_retail_mvrv_ratio": 1.0, "total_supply_btc": 1.0, "total_addresses": 1}
            for c in ["retail", "mid_tier", "whale"]
        ]
    )
    
    # Wallet Waves: 6 bands required
    mock.get_wallet_waves_latest = AsyncMock(
        return_value=[
            {"block_height": 840000, "band": b, "ts": datetime.now(), "supply_btc": 1.0, "supply_pct": 1.0, "address_count": 1, "avg_balance": 1.0, "total_supply_btc": 1.0, "retail_supply_pct": 1.0, "institutional_supply_pct": 1.0, "address_count_total": 1, "null_address_btc": 1.0, "confidence": 1.0}
            for b in ["shrimp", "crab", "fish", "shark", "whale", "humpback"]
        ]
    )
    
    # Absorption Rates: 6 bands required
    mock.get_absorption_rates_latest = AsyncMock(
        return_value=[
            {"block_height": 840000, "band": b, "ts": datetime.now(), "absorption_rate": 0.45, "supply_delta_btc": 1.0, "supply_start_btc": 1.0, "supply_end_btc": 1.0, "window_days": 30, "mined_supply_btc": 1.0, "dominant_absorber": "whale", "retail_absorption": 1.0, "institutional_absorption": 1.0, "confidence": 1.0, "has_historical_data": True}
            for b in ["shrimp", "crab", "fish", "shark", "whale", "humpback"]
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
    assert len(payload["bands"]) == 6
    assert any(b["band"] == "shrimp" for b in payload["bands"])

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
    client = TestClient(live_app)
    response = client.get("/api/whale/summary")
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

def test_8011_inconsistent_snapshot_fail(mock_questdb_repo):
    """TEST: 8011 should return 503 if the snapshot is inconsistent (Frankenstein)."""
    # Mock returns inconsistent heights for address cohorts (2 rows at H1, 1 at H2)
    mock_questdb_repo.get_address_cohorts_latest = AsyncMock(
        return_value=[
            {"block_height": 840000, "cohort": "whale", "ts": datetime.now(), "cost_basis": 1.0, "supply_btc": 1.0, "supply_pct": 1.0, "mvrv": 1.0, "address_count": 1, "current_price_usd": 1.0, "whale_retail_spread": 1.0, "whale_retail_mvrv_ratio": 1.0, "total_supply_btc": 1.0, "total_addresses": 1},
            {"block_height": 840000, "cohort": "mid_tier", "ts": datetime.now(), "cost_basis": 1.0, "supply_btc": 1.0, "supply_pct": 1.0, "mvrv": 1.0, "address_count": 1, "current_price_usd": 1.0, "whale_retail_spread": 1.0, "whale_retail_mvrv_ratio": 1.0, "total_supply_btc": 1.0, "total_addresses": 1},
            {"block_height": 839999, "cohort": "retail", "ts": datetime.now(), "cost_basis": 1.0, "supply_btc": 1.0, "supply_pct": 1.0, "mvrv": 1.0, "address_count": 1, "current_price_usd": 1.0, "whale_retail_spread": 1.0, "whale_retail_mvrv_ratio": 1.0, "total_supply_btc": 1.0, "total_addresses": 1},
        ]
    )
    
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/address-cohorts")
    
    # After hardening, it picks max height (840000) which only has 2 cohorts.
    # It fails because 2 < 3.
    assert response.status_code == 503
    assert "Inconsistent snapshot detected" in response.json()["detail"]
