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
            "signal_std": 0.02,
            "ci_lower": 0.11,
            "ci_upper": 0.19,
            "action": "HOLD",
            "action_confidence": 0.66,
            "n_samples": 1000,
            "distribution_type": "normal",
            "block_height": 890000,
            "active_addresses_block": 1200,
            "active_addresses_24h": 650000,
            "unique_senders": 700,
            "unique_receivers": 800,
            "is_anomaly": False,
            "tx_count": 250000,
            "tx_volume_btc": 12345.67,
            "tx_volume_usd": 1049381950.0,
            "utxoracle_price_used": 85000.0,
            "low_confidence": False,
        }
    )
    mock.fetchrow = AsyncMock(
        return_value={
            "total_transactions": 12,
            "total_btc_volume": 3456.78,
            "avg_urgency_score": 0.812,
            "high_urgency_count": 5,
            "rbf_enabled_count": 3,
        }
    )
    return mock

def test_prices_promotion_8011(mock_questdb_repo):
    """TEST: /api/prices/latest should be served successfully on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/prices/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["utxoracle_price"] == 85000.0
    assert payload["mempool_price"] == 85100.0
    assert payload["is_valid"] is True

def test_metrics_latest_promotion_8011(mock_questdb_repo):
    """TEST: /api/metrics/latest should be served successfully on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["monte_carlo"]["action"] == "HOLD"
    assert payload["active_addresses"]["block_height"] == 890000
    assert payload["tx_volume"]["tx_count"] == 250000

def test_whale_promotion_8011(mock_questdb_repo):
    """TEST: /api/whale/summary should be served successfully on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/whale/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_transactions"] == 12
    assert payload["high_urgency_count"] == 5
    assert payload["entity_enrichment_mode"] == "best_effort_optional"

def test_duckdb_metrics_stay_off_8011(mock_questdb_repo):
    """GUARDRAIL: DuckDB-backed metrics must stay off 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/nupl")
    assert response.status_code == 404

def test_8001_migration_headers(mock_questdb_repo):
    """TEST: /api/prices/latest on 8001 should have migration headers."""
    main_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(main_app)
    response = client.get("/api/prices/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["utxoracle_price"] == 85000.0
    assert response.headers.get("X-UTXOracle-Migration-Hint") == "Canonical production host is :8011"
    assert response.headers.get("Deprecation") == "true"
