import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from api.apps.live import app as live_app
from api.main import app as main_app
from api.questdb_repository import QuestDBRepository

@pytest.fixture
def mock_questdb_repo():
    mock = MagicMock(spec=QuestDBRepository)
    mock.initialize = AsyncMock()
    return mock

def test_prices_promotion_8011(mock_questdb_repo):
    """TEST: /api/prices/latest should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/prices/latest")
    assert response.status_code != 404

def test_metrics_latest_promotion_8011(mock_questdb_repo):
    """TEST: /api/metrics/latest should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/metrics/latest")
    assert response.status_code != 404

def test_whale_promotion_8011(mock_questdb_repo):
    """TEST: /api/whale/summary should be available on 8011."""
    live_app.state.questdb_repo = mock_questdb_repo
    client = TestClient(live_app)
    response = client.get("/api/whale/summary")
    assert response.status_code != 404

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
    # It should still work (not 404/410)
    assert response.status_code != 404
    # But it must have migration hint
    assert response.headers.get("X-UTXOracle-Migration-Hint") == "Canonical production host is :8011"
    assert response.headers.get("Deprecation") == "true"
