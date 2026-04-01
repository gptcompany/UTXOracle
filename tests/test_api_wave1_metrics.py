from fastapi.testclient import TestClient


def test_wallet_waves_endpoint_returns_current_distribution(wave1_client):
    response = wave1_client.get("/api/metrics/wallet-waves")

    assert response.status_code == 200
    data = response.json()
    assert data["block_height"] == 10000
    assert len(data["bands"]) == 6
    assert data["retail_supply_pct"] > 0
    assert data["institutional_supply_pct"] > 0
    assert 0.0 <= data["confidence"] <= 1.0


def test_wallet_waves_history_is_explicitly_unavailable(wave1_client):
    response = wave1_client.get("/api/metrics/wallet-waves/history?days=30")

    assert response.status_code == 503
    assert "not materialized" in response.json()["detail"]


def test_absorption_rates_uses_real_historical_baseline(wave1_client):
    response = wave1_client.get("/api/metrics/absorption-rates?window=30d")

    assert response.status_code == 200
    data = response.json()
    assert data["has_historical_data"] is True
    assert data["window_days"] == 30
    assert len(data["bands"]) == 6
    assert any(band["absorption_rate"] is not None for band in data["bands"])


def test_absorption_rates_reports_insufficient_history_explicitly(
    wave1_low_history_client,
):
    response = wave1_low_history_client.get("/api/metrics/absorption-rates?window=30d")

    assert response.status_code == 200
    data = response.json()
    assert data["has_historical_data"] is False
    assert all(band["absorption_rate"] is None for band in data["bands"])
    assert data["confidence"] < 0.5


def test_wave1_routes_return_503_when_utxo_db_is_missing(monkeypatch, tmp_path):
    from api.main import app
    import api.main

    missing_db = tmp_path / "missing-wave1.duckdb"
    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(missing_db))

    client = TestClient(app)
    try:
        for path in [
            "/api/metrics/address-cohorts",
            "/api/metrics/wallet-waves",
            "/api/metrics/absorption-rates",
        ]:
            response = client.get(path)
            assert response.status_code == 503
            assert "UTXO lifecycle database not found" in response.json()["detail"]
    finally:
        client.close()
