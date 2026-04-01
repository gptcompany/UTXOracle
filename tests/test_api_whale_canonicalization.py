from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


class _FakeWhaleRepo:
    def __init__(self) -> None:
        self.row = {
            "prediction_id": "pred-001",
            "transaction_id": "tx-001",
            "flow_type": "distribution",
            "btc_value": 245.5,
            "fee_rate": 32.1,
            "urgency_score": 0.91,
            "rbf_enabled": True,
            "detection_timestamp": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
            "predicted_confirmation_block": 941500,
            "confidence_score": 0.84,
        }

    async def fetch(self, query, *args):
        assert "FROM mempool_predictions" in query
        return [self.row]

    async def fetchrow(self, query, *args):
        assert "FROM mempool_predictions" in query
        if "COUNT(*) as total_transactions" in query:
            return {
                "total_transactions": 1,
                "total_btc_volume": 245.5,
                "avg_urgency_score": 0.91,
                "high_urgency_count": 1,
                "rbf_enabled_count": 1,
            }
        if args and args[0] == "tx-001":
            return self.row
        return None


@pytest.fixture
def whale_client(monkeypatch):
    from api.main import app

    monkeypatch.setattr(app.state, "questdb_repo", _FakeWhaleRepo(), raising=False)
    client = TestClient(app)
    yield client
    client.close()


def test_canonical_whale_query_routes_return_data(whale_client):
    transactions = whale_client.get("/api/whale/transactions")
    summary = whale_client.get("/api/whale/summary")
    tx = whale_client.get("/api/whale/transaction/tx-001")

    assert transactions.status_code == 200
    txs = transactions.json()
    assert len(txs) == 1
    assert txs[0]["transaction_id"] == "tx-001"
    assert txs[0]["prediction_id"] == "pred-001"

    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_transactions"] == 1
    assert summary_body["high_urgency_count"] == 1

    assert tx.status_code == 200
    tx_body = tx.json()
    assert tx_body["transaction_id"] == "tx-001"
    assert tx_body["confidence_score"] == 0.84


def test_unknown_canonical_whale_transaction_returns_404(whale_client):
    response = whale_client.get("/api/whale/transaction/missing-tx")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_legacy_whale_routes_return_explicit_deprecation_metadata(whale_client):
    for path in [
        "/api/whale/latest",
        "/api/whale/historical?timeframe=24h",
        "/api/whale/history?timeframe=24h",
    ]:
        response = whale_client.get(path)

        assert response.status_code == 410
        assert response.headers["Deprecation"] == "true"
        assert "successor-version" in response.headers["Link"]

        body = response.json()
        assert body["status"] == "deprecated"
        assert body["canonical_surface_id"] == "whale_query_surface"
        assert "/api/whale/transactions" in body["canonical_routes"]
