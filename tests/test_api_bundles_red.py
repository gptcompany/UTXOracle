import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from api.apps.live import app as live_app

# These tests establish the RED baseline for the bundle serving routes
# as defined in spec-052 Phase 6. They will fail until the routes are implemented.

BUNDLE_CONTRACTS = {
    "core": {
        "bundle_id": "btc_core_live.v1",
        "payload_keys": {"live_snapshot", "metrics_latest"},
    },
    "flow": {
        "bundle_id": "btc_flow.v1",
        "payload_keys": {"whale_summary", "recent_whale_window", "absorption_rates"},
    },
    "macro": {
        "bundle_id": "btc_macro.v1",
        "payload_keys": {"macro_metrics", "source_metadata"},
    },
    "cohort": {
        "bundle_id": "btc_cohort.v1",
        "payload_keys": {
            "address_cohorts",
            "wallet_waves",
            "absorption_rates",
            "cost_basis",
        },
    },
}


@pytest.fixture
def api_client():
    return TestClient(live_app, raise_server_exceptions=False)


def _bundle_row(bundle_type: str, sequence_id: int):
    produced_at = datetime(2026, 4, 7, 12, sequence_id, tzinfo=timezone.utc)
    metadata = {
        "schema_version": "v1",
        "bundle_id": BUNDLE_CONTRACTS[bundle_type]["bundle_id"],
        "sequence_id": sequence_id,
        "produced_at": produced_at.isoformat(),
        "bundle_status": "healthy",
        "degraded_reasons": [],
    }
    payload = {"metadata": metadata}
    for key in BUNDLE_CONTRACTS[bundle_type]["payload_keys"]:
        payload[key] = {}
    return {
        "payload_json": json.dumps(payload),
        "sequence_id": sequence_id,
        "produced_at": produced_at,
        "bundle_status": "healthy",
    }


class FakeBundleHistoryRepo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def get_feature_bundle_history(self, bundle_id, limit, after_sequence_id=None):
        self.calls.append((bundle_id, limit, after_sequence_id))
        return self.rows


@pytest.mark.parametrize("bundle_type", BUNDLE_CONTRACTS)
def test_bundle_latest_route_exists_and_returns_correct_shape(api_client, bundle_type):
    """T031: Expected response shape for latest routes."""
    response = api_client.get(f"/api/features/btc/{bundle_type}/latest")
    
    assert response.status_code == 200, f"Route /api/features/btc/{bundle_type}/latest is missing or failing"
    
    payload = response.json()
    assert "metadata" in payload
    expected_payload_keys = BUNDLE_CONTRACTS[bundle_type]["payload_keys"]
    assert expected_payload_keys.issubset(payload.keys())
    
    meta = payload["metadata"]
    assert meta["schema_version"] == "v1"
    assert meta["bundle_id"] == BUNDLE_CONTRACTS[bundle_type]["bundle_id"]
    assert "sequence_id" in meta
    assert "produced_at" in meta
    assert meta["bundle_status"] in ["healthy", "degraded", "stale", "empty", "misconfigured"]
    assert "degraded_reasons" in meta


@pytest.mark.parametrize("bundle_type", BUNDLE_CONTRACTS)
def test_bundle_history_route_exists_and_orders_by_sequence_id(api_client, bundle_type):
    """T032: Ordering by sequence_id and pagination for history routes."""
    response = api_client.get(f"/api/features/btc/{bundle_type}/history?limit=5")
    
    assert response.status_code == 200, f"Route /api/features/btc/{bundle_type}/history is missing or failing"
    
    payload = response.json()
    assert "items" in payload
    assert "pagination" in payload
    
    items = payload["items"]
    if len(items) > 1:
        # History should be oldest-to-newest by default per spec.md#10
        for i in range(len(items) - 1):
            assert items[i]["metadata"]["sequence_id"] <= items[i+1]["metadata"]["sequence_id"]


@pytest.mark.parametrize("bundle_type", BUNDLE_CONTRACTS)
def test_bundle_routes_handle_empty_state_gracefully(api_client, bundle_type):
    """T031/T032: Empty state behavior."""
    response = api_client.get(f"/api/features/btc/{bundle_type}/latest")
    
    assert response.status_code == 200
    assert response.json()["metadata"]["bundle_status"] == "empty"


def test_bundle_history_paginates_from_oldest_rows(api_client):
    repo = FakeBundleHistoryRepo(
        [
            _bundle_row("core", 1),
            _bundle_row("core", 2),
            _bundle_row("core", 3),
        ]
    )
    previous_repo = getattr(api_client.app.state, "questdb_repo", None)
    api_client.app.state.questdb_repo = repo
    try:
        response = api_client.get("/api/features/btc/core/history?limit=2")
    finally:
        if previous_repo is None and hasattr(api_client.app.state, "questdb_repo"):
            delattr(api_client.app.state, "questdb_repo")
        elif previous_repo is not None:
            api_client.app.state.questdb_repo = previous_repo

    assert response.status_code == 200
    payload = response.json()
    assert [item["metadata"]["sequence_id"] for item in payload["items"]] == [1, 2]
    assert payload["pagination"] == {"next_page_token": "2", "has_more": True}
    assert repo.calls == [("btc_core_live.v1", 3, None)]
