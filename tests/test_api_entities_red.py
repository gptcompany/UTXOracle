import pytest
import re
from fastapi.testclient import TestClient
from api.apps.live import app as live_app

# These tests establish the RED baseline for the entity intelligence plane
# as defined in spec-053 Phase 7. They will fail until the routes are implemented.

@pytest.fixture
def api_client():
    with TestClient(live_app, raise_server_exceptions=False) as client:
        yield client

def test_entity_metadata_route_exists_and_returns_correct_shape(api_client):
    """T048: Expected response shape for entity metadata lookup."""
    entity_id = "btc:entity:curated:binance"
    response = api_client.get(f"/api/entities/{entity_id}")
    
    assert response.status_code == 200, f"Route /api/entities/{entity_id} is missing or failing"
    
    payload = response.json()
    assert payload["entity_id"] == entity_id
    assert "entity_kind" in payload
    assert "registry_status" in payload
    assert "display_label" in payload
    assert "confidence_overall" in payload
    assert isinstance(payload["labels"], list)
    assert "provenance_summary" in payload

def test_entity_history_route_exists_and_paginates(api_client):
    """T049: Ordering and pagination for entity history."""
    entity_id = "btc:entity:curated:binance"
    response = api_client.get(f"/api/entities/{entity_id}/history?limit=5")
    
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "pagination" in payload
    
    pagination = payload["pagination"]
    assert "next_page_token" in pagination
    assert "has_more" in pagination

def test_entity_flows_route_exists_and_filters(api_client):
    """T049: Movement and flow query route."""
    response = api_client.get("/api/entities/flows?min_value=10.0")
    
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "service_status" in payload
    
    if payload["items"]:
        item = payload["items"][0]
        assert "entity_id" in item
        assert "netflow_btc" in item

def test_internal_reshuffle_classification_logic(api_client):
    """T050: Verify internal-reshuffle vs external-flow classification."""
    # This test might require mocked data once implemented, 
    # but for RED state we just verify the route accepts the classification filter
    response = api_client.get("/api/entities/flows?classification=internal_entity_reshuffle")
    assert response.status_code == 200

def test_entity_metadata_handles_missing_gracefully(api_client):
    """T048: Degraded/empty behavior for unknown entities."""
    response = api_client.get("/api/entities/btc:entity:unknown:999")
    # Should return 404 for unknown entities
    assert response.status_code == 404
