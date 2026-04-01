from fastapi.testclient import TestClient


def test_main_app_does_not_expose_live_snapshot_route():
    from api.main import app

    client = TestClient(app)

    response = client.get("/api/v1/live/snapshot")

    assert response.status_code == 404


def test_puell_multiple_route_is_runtime_demoted():
    from api.main import app

    client = TestClient(app)

    response = client.get("/api/metrics/puell-multiple")

    assert response.status_code == 501
    assert "runtime-demoted" in response.json()["detail"]


def test_power_law_predict_uses_dedicated_handler_shape():
    from api.main import app

    client = TestClient(app)

    response = client.get("/api/v1/models/power-law/predict?date=2025-12-25")

    assert response.status_code == 200
    data = response.json()
    assert "model" in data
    assert "prediction" in data
    assert "model_name" not in data
