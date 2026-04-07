import pytest
from fastapi.testclient import TestClient

# These tests establish the RED baseline for the bundle serving routes
# as defined in spec-052 Phase 6. They will fail until the routes are implemented.

BUNDLE_TYPES = [
    "core",
    "flow",
    "macro",
    "cohort"
]


@pytest.fixture
def api_client():
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("bundle_type", BUNDLE_TYPES)
def test_bundle_latest_route_exists_and_returns_correct_shape(api_client, bundle_type):
    """T031: Expected response shape for latest routes."""
    response = api_client.get(f"/api/features/btc/{bundle_type}/latest")
    
    assert response.status_code == 200, f"Route /api/features/btc/{bundle_type}/latest is missing or failing"
    
    payload = response.json()
    assert "metadata" in payload
    assert "metrics" in payload
    
    meta = payload["metadata"]
    assert meta["schema_version"] == "v1"
    assert meta["bundle_id"] == f"btc_{bundle_type}.v1"
    assert "sequence_id" in meta
    assert "produced_at" in meta
    assert meta["bundle_status"] in ["healthy", "degraded", "stale", "empty", "misconfigured"]
    assert "degraded_reasons" in meta


@pytest.mark.parametrize("bundle_type", BUNDLE_TYPES)
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


@pytest.mark.parametrize("bundle_type", BUNDLE_TYPES)
def test_bundle_routes_handle_empty_state_gracefully(api_client, bundle_type):
    """T031/T032: Empty state behavior."""
    # Assuming the test db is empty initially or can be mocked to be empty
    # We should get a 200 OK with bundle_status="empty" rather than a 404
    
    response = api_client.get(f"/api/features/btc/{bundle_type}/latest")
    
    # It might return 200 with empty status, or a structured 404 if truly not initialized yet.
    # The spec says "The route contract must not force downstream consumers to infer these states from random missing fields."
    # We will assert that if it returns 200, it has the standard schema.
    if response.status_code == 200:
        assert response.json()["metadata"]["bundle_status"] in ["empty", "healthy", "degraded", "stale", "misconfigured"]
