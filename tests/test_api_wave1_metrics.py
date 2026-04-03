from fastapi.testclient import TestClient
from unittest.mock import AsyncMock


def test_wallet_waves_endpoint_returns_current_distribution(wave1_client, questdb_repo_mock):
    wave1_client.app.state.questdb_repo = questdb_repo_mock
    response = wave1_client.get("/api/metrics/wallet-waves")

    assert response.status_code == 200
    data = response.json()
    assert data["block_height"] == 10000
    assert len(data["bands"]) == 6
    assert data["retail_supply_pct"] > 0
    assert data["institutional_supply_pct"] > 0
    assert 0.0 <= data["confidence"] <= 1.0


def test_wallet_waves_history_is_explicitly_unavailable(wave1_client, questdb_repo_mock):
    wave1_client.app.state.questdb_repo = questdb_repo_mock
    response = wave1_client.get("/api/metrics/wallet-waves/history?days=30")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_absorption_rates_uses_real_historical_baseline(wave1_client, questdb_repo_mock):
    wave1_client.app.state.questdb_repo = questdb_repo_mock
    response = wave1_client.get("/api/metrics/absorption-rates?window=30d")

    assert response.status_code == 200
    data = response.json()
    assert data["has_historical_data"] is True
    assert data["window_days"] == 30
    assert len(data["bands"]) == 6
    assert any(band["absorption_rate"] is not None for band in data["bands"])


def test_absorption_rates_reports_insufficient_history_explicitly(
    wave1_low_history_client, questdb_repo_mock
):
    wave1_low_history_client.app.state.questdb_repo = questdb_repo_mock

    empty_rows = []
    for row in questdb_repo_mock.get_absorption_rates_latest.return_value:
        empty_rows.append({**row, "absorption_rate": None, "has_historical_data": False, "confidence": 0.4})
    questdb_repo_mock.get_absorption_rates_latest = AsyncMock(return_value=empty_rows)

    response = wave1_low_history_client.get("/api/metrics/absorption-rates?window=30d")

    assert response.status_code == 200
    data = response.json()
    assert data["has_historical_data"] is False
    assert all(band["absorption_rate"] is None for band in data["bands"])
    assert data["confidence"] < 0.5


def test_wave1_routes_return_503_when_questdb_repo_is_missing():
    from api.main import app
    if hasattr(app.state, "questdb_repo"):
        delattr(app.state, "questdb_repo")

    client = TestClient(app)
    try:
        for path in [
            "/api/metrics/address-cohorts",
            "/api/metrics/wallet-waves",
            "/api/metrics/absorption-rates",
        ]:
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["detail"] == "QuestDB repository unavailable. API startup may be incomplete."
    finally:
        client.close()
