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


class FakeEntityRepo:
    def __init__(self):
        self.metadata_calls: list[str] = []
        self.history_calls: list[tuple[str, int, datetime | None]] = []
        self.flow_calls: list[tuple[float, str | None, str | None, int, datetime | None]] = []

    async def get_entity_metadata(self, entity_id: str):
        self.metadata_calls.append(entity_id)
        if entity_id == "btc:entity:unknown:999":
            return None
        return {
            "entity_id": entity_id,
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

    async def get_entity_provenance(self, entity_id: str):
        return {
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

    async def get_entity_history(self, entity_id: str, limit: int, after_date: datetime | None = None):
        self.history_calls.append((entity_id, limit, after_date))
        rows = [
            {"date": datetime(2026, 4, 1, tzinfo=timezone.utc)},
            {"date": datetime(2026, 4, 2, tzinfo=timezone.utc)},
            {"date": datetime(2026, 4, 3, tzinfo=timezone.utc)},
        ]
        return rows

    async def get_entity_flows(
        self,
        *,
        min_value: float = 0.0,
        classification: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        after_window_start: datetime | None = None,
    ):
        self.flow_calls.append((min_value, classification, entity_id, limit, after_window_start))
        return [
            {
                "window_start": datetime(2026, 4, 1, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 2, tzinfo=timezone.utc),
                "source_entity_id": "btc:entity:cluster:unknown",
                "target_entity_id": entity_id or "btc:entity:curated:binance",
                "movement_classification": classification or "unlabeled_to_entity",
                "btc_amount": 25.0,
                "attribution_confidence": 0.6,
                "is_internal": False,
                "materialization_status": "healthy",
            },
            {
                "window_start": datetime(2026, 4, 2, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 3, tzinfo=timezone.utc),
                "source_entity_id": "btc:entity:cluster:unknown",
                "target_entity_id": entity_id or "btc:entity:curated:binance",
                "movement_classification": classification or "unlabeled_to_entity",
                "btc_amount": 15.0,
                "attribution_confidence": 0.6,
                "is_internal": False,
                "materialization_status": "healthy",
            },
            {
                "window_start": datetime(2026, 4, 3, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 4, tzinfo=timezone.utc),
                "source_entity_id": "btc:entity:cluster:unknown",
                "target_entity_id": entity_id or "btc:entity:curated:binance",
                "movement_classification": classification or "unlabeled_to_entity",
                "btc_amount": 12.0,
                "attribution_confidence": 0.6,
                "is_internal": False,
                "materialization_status": "healthy",
            },
        ]


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


def test_entity_metadata_route_returns_contract_shape(api_client):
    repo = FakeEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/btc:entity:curated:binance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "btc:entity:curated:binance"
    assert payload["display_label"] == "Binance"
    assert payload["entity_kind"] == "exchange"
    assert payload["registry_status"] == "active"
    assert "first_seen" in payload
    assert "last_seen" in payload
    assert payload["confidence"] == {
        "cluster_confidence": 0.8,
        "mapping_confidence": 0.8,
        "label_confidence": 0.8,
        "confidence_overall": 0.8,
    }
    assert isinstance(payload["labels"], list)
    assert isinstance(payload["provenance_summary"], list)
    assert payload["source_status"] == "healthy"


def test_entity_metadata_route_accepts_legacy_cluster_alias(api_client):
    repo = FakeEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/cluster:cluster_001")

    assert response.status_code == 200
    assert response.json()["entity_id"] == "btc:entity:cluster:cluster_001"
    assert repo.metadata_calls == ["btc:entity:cluster:cluster_001"]


def test_entity_history_route_paginates_oldest_to_newest(api_client):
    repo = FakeEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/btc:entity:curated:binance/history?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert [item["as_of"] for item in payload["items"]] == [
        "2026-04-01T00:00:00+00:00",
        "2026-04-02T00:00:00+00:00",
    ]
    assert payload["pagination"] == {
        "next_page_token": "2026-04-02T00:00:00+00:00",
        "has_more": True,
    }
    assert repo.history_calls == [("btc:entity:curated:binance", 3, None)]


def test_entity_flows_route_returns_contract_shape_and_filter(api_client):
    repo = FakeEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get(
            "/api/entities/flows?entity_id=cluster:cluster_001&classification=internal_entity_reshuffle&limit=2"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_status"] == "healthy"
    assert payload["pagination"] == {
        "next_page_token": "2026-04-02T00:00:00+00:00",
        "has_more": True,
    }
    assert payload["items"][0]["movement_classification"] == "internal_entity_reshuffle"
    assert payload["items"][0]["target_entity_id"] == "btc:entity:cluster:cluster_001"
    assert repo.flow_calls == [
        (
            0.0,
            "internal_entity_reshuffle",
            "btc:entity:cluster:cluster_001",
            3,
            None,
        )
    ]


def test_entity_metadata_handles_missing_entity_with_404(api_client):
    repo = FakeEntityRepo()
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/entities/btc:entity:unknown:999")

    assert response.status_code == 404
