from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


class _FakeWhaleRepo:
    def __init__(
        self,
        *,
        exchange_addresses: str = "",
        cluster_rows: list[dict] | None = None,
        entity_row: dict | None = None,
    ) -> None:
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
            "exchange_addresses": exchange_addresses,
        }
        self.cluster_rows = list(cluster_rows or [])
        self.entity_row = entity_row
        self.raise_entity_lookup = False

    async def fetch(self, query, *args):
        if "FROM mempool_predictions" in query:
            return [self.row]
        if "FROM address_clusters" in query:
            addresses = set(args)
            return [row for row in self.cluster_rows if row["address"] in addresses]
        raise AssertionError(f"Unexpected query: {query}")

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

    async def get_entity_metadata(self, entity_id: str):
        if self.raise_entity_lookup:
            raise RuntimeError("entity registry unavailable")
        return self.entity_row


@pytest.fixture
def whale_client(monkeypatch):
    from api.main import app

    monkeypatch.setattr(app.state, "questdb_repo", _FakeWhaleRepo(), raising=False)
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture
def whale_enriched_client(monkeypatch):
    from api.main import app

    repo = _FakeWhaleRepo(
        exchange_addresses="1Binance,1BinanceHot",
        cluster_rows=[
            {
                "address": "1Binance",
                "cluster_id": "cluster_001",
                "label": "Binance",
            },
            {
                "address": "1BinanceHot",
                "cluster_id": "cluster_001",
                "label": "Binance",
            },
        ],
    )
    monkeypatch.setattr(app.state, "questdb_repo", repo, raising=False)
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture
def whale_ambiguous_client(monkeypatch):
    from api.main import app

    repo = _FakeWhaleRepo(
        exchange_addresses="1Binance,1Kraken",
        cluster_rows=[
            {
                "address": "1Binance",
                "cluster_id": "cluster_001",
                "label": "Binance",
            },
            {
                "address": "1Kraken",
                "cluster_id": "cluster_777",
                "label": "Kraken",
            },
        ],
    )
    monkeypatch.setattr(app.state, "questdb_repo", repo, raising=False)
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
    assert txs[0]["event_id"] == "pred-001"
    assert txs[0]["source"] == "questdb.mempool_predictions"
    assert txs[0]["status"] == "detected"
    assert txs[0]["entity_enrichment_status"] == "unavailable"
    assert txs[0]["entity"] is None

    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["surface_id"] == "whale_query_surface"
    assert summary_body["event_schema_version"] == "whale_event.v1"
    assert summary_body["total_transactions"] == 1
    assert summary_body["high_urgency_count"] == 1
    assert summary_body["entity_enrichment_mode"] == "best_effort_optional"
    assert "transaction_id" in summary_body["entity_policy"]["observed_fields"]
    assert "entity.entity_id" in summary_body["entity_policy"]["inferred_fields"]

    assert tx.status_code == 200
    tx_body = tx.json()
    assert tx_body["transaction_id"] == "tx-001"
    assert tx_body["confidence_score"] == 0.84
    assert tx_body["entity_enrichment_status"] == "unavailable"
    assert tx_body["entity"] is None


def test_whale_event_enrichment_uses_cluster_foundation_when_available(
    whale_enriched_client,
):
    response = whale_enriched_client.get("/api/whale/transaction/tx-001")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_enrichment_status"] == "inferred"
    assert body["entity"]["cluster_id"] == "cluster_001"
    assert body["entity"]["entity_id"] == "cluster:cluster_001"
    assert body["entity"]["entity_label"] == "Binance"
    assert body["entity"]["label_source"] == "questdb.address_clusters.label"
    assert body["entity"]["confidence"] == 0.8
    assert body["entity"]["attribution_kind"] == "inferred"


def test_whale_event_enrichment_preserves_ambiguous_attribution_without_entity(
    whale_ambiguous_client,
):
    response = whale_ambiguous_client.get("/api/whale/transaction/tx-001")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_enrichment_status"] == "ambiguous"
    assert body["entity"] is None


def test_whale_event_enrichment_degrades_gracefully_when_registry_lookup_fails(monkeypatch):
    from api.main import app

    repo = _FakeWhaleRepo(
        exchange_addresses="1Binance,1BinanceHot",
        cluster_rows=[
            {
                "address": "1Binance",
                "cluster_id": "cluster_001",
                "label": "Binance",
            },
            {
                "address": "1BinanceHot",
                "cluster_id": "cluster_001",
                "label": "Binance",
            },
        ],
    )
    repo.raise_entity_lookup = True
    monkeypatch.setattr(app.state, "questdb_repo", repo, raising=False)
    client = TestClient(app)

    response = client.get("/api/whale/transaction/tx-001")

    client.close()
    assert response.status_code == 200
    body = response.json()
    assert body["entity_enrichment_status"] == "inferred"
    assert body["entity"]["entity_id"] == "cluster:cluster_001"
    assert body["entity"]["label_source"] == "questdb.address_clusters.label"


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
