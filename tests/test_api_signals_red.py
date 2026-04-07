import pytest
from fastapi.testclient import TestClient

from api.main import app

# These tests establish the RED baseline for the signal snapshot serving routes
# as defined in spec-052 Phase 7. They will fail until the routes are implemented.

@pytest.fixture
def api_client():
    return TestClient(app, raise_server_exceptions=False)


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


def test_signal_routes_handle_empty_state_gracefully(api_client):
    """T045: Degraded/empty state behavior for signals."""
    response = api_client.get("/api/signals/btc/latest")
    
    assert response.status_code == 200
    payload = response.json()
    
    # If the DB is completely empty before background workers write to it,
    # the signal service_status should be empty.
    # The bias/conviction/scores should have neutral/zero defaults to satisfy schemas.
    if payload["service_status"] == "empty":
        assert payload["bias"] == "neutral"
        assert payload["conviction"] == 0.0
        assert payload["quality_score"] == 0.0
        assert payload["regime_score"] == 0.0
        assert payload["flow_score"] == 0.0
        assert payload["valuation_score"] == 0.0
