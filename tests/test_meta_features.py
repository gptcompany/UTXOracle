from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.apps.live import app

client = TestClient(app)

@pytest.fixture
def valid_manifest_yaml():
    return """
schema_version: "1"
published_at: "2026-04-02"
source_documents:
  - "docs/example.md"
backend_classes:
  questdb: "QuestDB tables"
failure_mode_vocabulary:
  empty: "No data"
entries:
  - surface_id: "test_surface"
    route_family: "/api/test/*"
    backend_class: "questdb"
    primary_tables:
      - "test_table"
    upstreams:
      - "test_upstream"
    required_env:
      - "TEST_ENV"
    writer_owner: "test.worker"
    read_path_owner: "api.routes.test"
    freshness_source: "Newest row"
    failure_mode:
      empty: "503 empty"
      stale: "stale"
      degraded: "degraded"
      misconfigured: "misconfigured"
      placeholder: "none"
    provenance_notes:
      - "Note 1"
"""

def test_get_feature_provenance_success(tmp_path, valid_manifest_yaml):
    manifest_file = tmp_path / "feature_provenance_manifest.yaml"
    manifest_file.write_text(valid_manifest_yaml)
    
    with patch("api.routes.meta.MANIFEST_PATH", manifest_file):
        response = client.get("/api/meta/features")
        assert response.status_code == 200
        
        data = response.json()
        assert data["schema_version"] == "1"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["surface_id"] == "test_surface"
        assert data["entries"][0]["failure_mode"]["empty"] == "503 empty"

def test_get_feature_provenance_missing_file(tmp_path):
    missing_file = tmp_path / "missing.yaml"
    with patch("api.routes.meta.MANIFEST_PATH", missing_file):
        response = client.get("/api/meta/features")
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]

def test_get_feature_provenance_invalid_yaml(tmp_path):
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("invalid: yaml: :")
    
    with patch("api.routes.meta.MANIFEST_PATH", invalid_file):
        response = client.get("/api/meta/features")
        assert response.status_code == 500
        assert "parse" in response.json()["detail"]
