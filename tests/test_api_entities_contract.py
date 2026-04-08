from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.apps.live import app as live_app


@pytest.fixture
def api_client():
    return TestClient(live_app, raise_server_exceptions=False)


class ContractEntityRepo:
    def __init__(self) -> None:
        self.metadata_row = {
            "entity_id": "btc:entity:curated:binance",
            "display_label": "Binance",
            "entity_kind": "exchange",
            "registry_status": "active",
            "cluster_confidence": 0.8,
            "mapping_confidence": 0.8,
            "label_confidence": 0.8,
            "confidence_overall": 0.8,
            "first_seen": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
            "last_seen": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            "source_status": "healthy",
        }
        self.provenance_row = {
            "provenance_summary_json": json.dumps(
                [
                    {
                        "label": "Binance",
                        "source_kind": "inherited_cluster_label",
                        "source_name": "address_clusters_table",
                        "review_status": "unreviewed",
                    }
                ]
            )
        }
        self.history_rows = [
            {
                "date": datetime(2026, 4, 1, tzinfo=timezone.utc),
                "event_type": "balance_snapshot",
                "registry_status": "active",
                "cluster_ids": ["cluster_001"],
                "confidence_overall": 0.8,
                "provenance_ref": "entity_registry_serving:2026-04-01",
            }
        ]
        self.flow_rows = [
            {
                "window_start": datetime(2026, 4, 1, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 2, tzinfo=timezone.utc),
                "source_entity_id": "btc:entity:cluster:unknown",
                "target_entity_id": "btc:entity:curated:binance",
                "movement_classification": "unlabeled_to_entity",
                "btc_amount": 25.0,
                "attribution_confidence": 0.6,
                "is_internal": False,
                "materialization_status": "healthy",
            }
        ]

    async def get_entity_metadata(self, entity_id: str):
        row = dict(self.metadata_row)
        row["entity_id"] = entity_id
        return row

    async def get_entity_provenance(self, entity_id: str):
        return self.provenance_row

    async def get_entity_history(self, entity_id: str, limit: int, after_date: datetime | None = None):
        return self.history_rows[:limit]

    async def get_entity_flows(
        self,
        *,
        min_value: float = 0.0,
        classification: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        after_window_start: datetime | None = None,
    ):
        rows = list(self.flow_rows)
        if classification is not None:
            rows = [row for row in rows if row["movement_classification"] == classification]
        if min_value:
            rows = [row for row in rows if row["btc_amount"] >= min_value]
        return rows[:limit]


@contextmanager
def _override_repo(app, repo):
    sentinel = object()
    previous_repo = getattr(app.state, "questdb_repo", sentinel)
    app.state.questdb_repo = repo
    try:
        yield
    finally:
        if previous_repo is sentinel and hasattr(app.state, "questdb_repo"):
            delattr(app.state, "questdb_repo")
        elif previous_repo is not sentinel:
            app.state.questdb_repo = previous_repo


def test_entity_metadata_contract_serializes_identity_and_provenance(api_client):
    repo = ContractEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/cluster:cluster_001")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "entity_id",
        "display_label",
        "entity_kind",
        "registry_status",
        "first_seen",
        "last_seen",
        "confidence",
        "labels",
        "provenance_summary",
        "source_status",
    }
    assert payload["entity_id"] == "btc:entity:cluster:cluster_001"
    assert payload["source_status"] == "healthy"
    assert set(payload["confidence"].keys()) == {
        "cluster_confidence",
        "mapping_confidence",
        "label_confidence",
        "confidence_overall",
    }
    assert payload["provenance_summary"] == [
        {
            "label": "Binance",
            "source_kind": "inherited_cluster_label",
            "source_name": "address_clusters_table",
            "review_status": "unreviewed",
        }
    ]


def test_entity_history_contract_serializes_required_fields(api_client):
    repo = ContractEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/btc:entity:curated:binance/history?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"items", "pagination"}
    assert len(payload["items"]) == 1
    assert set(payload["items"][0].keys()) == {
        "entity_id",
        "as_of",
        "event_type",
        "registry_status",
        "cluster_ids",
        "confidence_overall",
        "provenance_ref",
    }


def test_entity_flow_contract_serializes_required_fields(api_client):
    repo = ContractEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/flows?entity_id=btc:entity:curated:binance&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_status"] == "healthy"
    assert set(payload.keys()) == {"items", "pagination", "service_status"}
    assert len(payload["items"]) == 1
    assert set(payload["items"][0].keys()) == {
        "window_start",
        "window_end",
        "source_entity_id",
        "target_entity_id",
        "movement_classification",
        "btc_amount",
        "attribution_confidence",
        "is_internal",
        "materialization_status",
    }


def test_entity_flow_contract_preserves_ambiguous_attribution(api_client):
    repo = ContractEntityRepo()
    repo.flow_rows = [
        {
            "window_start": datetime(2026, 4, 3, tzinfo=timezone.utc),
            "window_end": datetime(2026, 4, 4, tzinfo=timezone.utc),
            "source_entity_id": None,
            "target_entity_id": "btc:entity:curated:binance",
            "movement_classification": "ambiguous",
            "btc_amount": 8.5,
            "attribution_confidence": 0.2,
            "is_internal": False,
            "materialization_status": "healthy",
        }
    ]

    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/flows?classification=ambiguous")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_status"] == "ambiguous"
    assert payload["items"][0]["movement_classification"] == "ambiguous"
    assert payload["items"][0]["source_entity_id"] is None
