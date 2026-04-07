from fastapi.testclient import TestClient


def test_wave2_routes_return_503_when_utxo_db_is_missing(monkeypatch, tmp_path):
    from api.main import app
    import api.main

    missing_db = tmp_path / "missing-wave2.duckdb"
    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(missing_db))

    client = TestClient(app)
    try:
        for path in ["/api/metrics/nupl"]:
            response = client.get(path)
            assert response.status_code in (404, 503)
            assert "UTXO lifecycle table not found. Schema migration pending." in response.json()["detail"] or "UTXO lifecycle database not found" in response.json()["detail"]
    finally:
        client.close()


def test_wave2_routes_return_404_when_utxo_schema_is_missing(monkeypatch, tmp_path):
    import duckdb

    from api.main import app
    import api.main

    db_path = tmp_path / "wave2_schema_missing.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE wrong_table(id INTEGER)")
    conn.close()

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(db_path))

    client = TestClient(app, raise_server_exceptions=False)
    try:
        for path in ["/api/metrics/nupl"]:
            response = client.get(path)
            assert response.status_code in (404, 503)
            assert "UTXO lifecycle table not found" in response.json()["detail"]
    finally:
        client.close()


def test_wave2_routes_return_404_when_snapshot_is_empty(wave2_empty_snapshot_client):
    for path, expected_detail in [
        ("/api/metrics/nupl", "No NUPL data available"),
    ]:
        response = wave2_empty_snapshot_client.get(path)
        assert response.status_code in (404, 503)
        assert expected_detail in response.json()["detail"] or "UTXO lifecycle table not found" in response.json()["detail"]


def test_reserve_risk_route_remains_explicitly_held(monkeypatch, wave2_duckdb_path):
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave2_duckdb_path))

    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.get("/api/metrics/reserve-risk?current_price=100000")
        assert response.status_code == 501
        assert response.json()["detail"] == "Not Implemented"
    finally:
        client.close()
