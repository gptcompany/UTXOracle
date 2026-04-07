import pytest
from fastapi.testclient import TestClient

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
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


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
