import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api.apps.live import app as live_app
from api.main import app as main_app

# These tests establish the RED baseline for the signal snapshot serving routes
# as defined in spec-052 Phase 7. They will fail until the routes are implemented.

@pytest.fixture
def api_client():
    return TestClient(main_app, raise_server_exceptions=False)


def _signal_payload(
    sequence_id: int,
    *,
    service_status: str = "healthy",
    quality_score: float = 1.0,
    degraded_reasons: list[str] | None = None,
    macro_sequence_id: int | None = 30,
) -> dict:
    return {
        "schema_version": "v1",
        "sequence_id": sequence_id,
        "produced_at": datetime(2026, 4, 7, 12, sequence_id, tzinfo=timezone.utc).isoformat(),
        "block_height": 840_000 + sequence_id,
        "service_status": service_status,
        "bias": "neutral",
        "conviction": 0.0 if service_status == "empty" else 0.5,
        "regime_score": 0.0,
        "flow_score": 0.0,
        "valuation_score": 0.0,
        "quality_score": quality_score,
        "degraded_reasons": degraded_reasons or [],
        "input_refs": {
            "core_sequence_id": 10,
            "flow_sequence_id": 20,
            "macro_sequence_id": macro_sequence_id,
            "cohort_sequence_id": 40,
        },
        "component_details": {
            "regime": {"score": 0.0},
            "flow": {"score": 0.0},
            "valuation": {"score": 0.0},
            "quality": {"score": quality_score},
        },
    }


def _signal_row(payload: dict) -> dict:
    return {
        "payload_json": json.dumps(payload),
        "sequence_id": payload["sequence_id"],
        "produced_at": payload["produced_at"],
        "service_status": payload["service_status"],
    }


class FakeSignalRepo:
    def __init__(self, *, latest: dict | None = None, history: list[dict] | None = None):
        self.latest = latest
        self.history = history or []
        self.latest_calls = 0
        self.history_calls = []

    async def get_latest_signal_snapshot(self):
        self.latest_calls += 1
        return self.latest

    async def get_signal_snapshot_history(self, limit, after_sequence_id=None):
        self.history_calls.append((limit, after_sequence_id))
        return self.history


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


def test_signal_latest_route_exists_and_returns_correct_shape(api_client):
    """T045: Expected response shape for latest signal route."""
    response = api_client.get("/api/signals/btc/latest")
    
    assert response.status_code == 200, "Route /api/signals/btc/latest is missing or failing"
    
    payload = response.json()
    assert "schema_version" in payload
    assert payload["schema_version"] == "v1"
    assert "sequence_id" in payload
    assert "produced_at" in payload
    assert "block_height" in payload
    assert "service_status" in payload
    assert payload["service_status"] in ["healthy", "degraded", "stale", "empty", "misconfigured"]
    
    # Core signal fields
    assert "bias" in payload
    assert payload["bias"] in ["bearish", "neutral", "bullish"]
    assert "conviction" in payload
    assert 0.0 <= payload["conviction"] <= 1.0
    
    assert "regime_score" in payload
    assert -1.0 <= payload["regime_score"] <= 1.0
    
    assert "flow_score" in payload
    assert -1.0 <= payload["flow_score"] <= 1.0
    
    assert "valuation_score" in payload
    assert -1.0 <= payload["valuation_score"] <= 1.0
    
    assert "quality_score" in payload
    assert 0.0 <= payload["quality_score"] <= 1.0
    
    assert "degraded_reasons" in payload
    assert isinstance(payload["degraded_reasons"], list)
    
    assert "input_refs" in payload
    refs = payload["input_refs"]
    assert "core_sequence_id" in refs
    assert "flow_sequence_id" in refs
    assert "macro_sequence_id" in refs
    assert "cohort_sequence_id" in refs
    
    assert "component_details" in payload
    assert isinstance(payload["component_details"], dict)


def test_signal_latest_route_is_exposed_on_8011(questdb_repo_mock):
    """T045: Signal routes must be exposed on the canonical :8011 app."""
    questdb_repo_mock.get_latest_signal_snapshot = AsyncMock(return_value=None)
    live_app.state.questdb_repo = questdb_repo_mock

    with TestClient(live_app, raise_server_exceptions=False) as client:
        response = client.get("/api/signals/btc/latest")

    assert response.status_code == 200
    assert response.json()["service_status"] == "empty"


def test_signal_history_route_exists_and_orders_by_sequence_id(api_client):
    """T045: Ordering by sequence_id and pagination for history signal routes."""
    response = api_client.get("/api/signals/btc/history?limit=5")
    
    assert response.status_code == 200, "Route /api/signals/btc/history is missing or failing"
    
    payload = response.json()
    assert "items" in payload
    assert "pagination" in payload
    
    items = payload["items"]
    if len(items) > 1:
        # History should be oldest-to-newest by default per spec.md#10
        for i in range(len(items) - 1):
            assert items[i]["sequence_id"] <= items[i+1]["sequence_id"]


def test_signal_history_paginates_from_oldest_rows(api_client):
    """T045: History must be replayable oldest-to-newest with page tokens."""
    repo = FakeSignalRepo(
        history=[
            _signal_row(_signal_payload(1)),
            _signal_row(_signal_payload(2)),
            _signal_row(_signal_payload(3)),
        ]
    )
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/signals/btc/history?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert [item["sequence_id"] for item in payload["items"]] == [1, 2]
    assert payload["pagination"] == {"next_page_token": "2", "has_more": True}
    assert repo.history_calls == [(3, None)]


def test_signal_routes_handle_empty_state_gracefully(api_client):
    """T045: Degraded/empty state behavior for signals."""
    repo = FakeSignalRepo(latest=None)
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/signals/btc/latest")
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["service_status"] == "empty"
    assert payload["bias"] == "neutral"
    assert payload["conviction"] == 0.0
    assert payload["quality_score"] == 0.0
    assert payload["regime_score"] == 0.0
    assert payload["flow_score"] == 0.0
    assert payload["valuation_score"] == 0.0


def test_signal_routes_propagate_degraded_bundle_inputs(api_client):
    """T045: Degraded bundle inputs must affect signal status and refs."""
    repo = FakeSignalRepo(
        latest=_signal_row(
            _signal_payload(
                7,
                service_status="degraded",
                quality_score=0.75,
                degraded_reasons=["btc_macro.v1 degraded"],
                macro_sequence_id=None,
            )
        )
    )
    with _override_repo(api_client.app, repo):
        response = api_client.get("/api/signals/btc/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_status"] == "degraded"
    assert payload["quality_score"] == 0.75
    assert "btc_macro.v1 degraded" in payload["degraded_reasons"]
    assert payload["input_refs"]["macro_sequence_id"] is None
