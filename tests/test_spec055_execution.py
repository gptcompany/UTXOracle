import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api.apps.live import app
from api.models.execution import ExecutionMode, OperatorStage
from scripts.live.models import LiveSnapshot


@pytest.fixture
def mock_questdb():
    repo = AsyncMock()
    # default happy path
    now = datetime.now(timezone.utc)
    repo.get_latest_feature_bundle.return_value = {
        "produced_at": now,
        "bundle_status": "ok",
        "payload_json": "{}",
    }
    repo.get_latest_signal_snapshot.return_value = {
        "produced_at": now,
        "service_status": "ok",
        "sequence_id": 1,
        "payload_json": "{}",
    }
    app.state.questdb_repo = repo
    yield repo
    app.state.questdb_repo = None


@pytest.fixture
def mock_snapshot_store():
    store = MagicMock()
    now = datetime.now(timezone.utc)
    snap = LiveSnapshot(
        timestamp=now,
        block_height=100000,
        utxoracle_price=100000.0,
        mempool_exchange_price=100000.0,
        hyperliquid_oracle_price=100000.0,
        hyperliquid_mark_price=100000.0,
        source_health={
            "electrs": {"status": "healthy"},
            "mempool": {"status": "healthy"},
        },
    )
    store.get_latest.return_value = snap
    store.aget_latest = None
    # We patch the dependency in the app
    from api.routes.live import get_live_snapshot_store

    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@patch("api.routes.execution._get_operator_stage")
def test_execution_trade_enabled(mock_stage, client, mock_snapshot_store, mock_questdb):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "trade_enabled"
    assert data["operator_stage"] == "full_capital"
    assert data["compatibility_status"] == "STATUS_OK"
    assert data["freshness_summary"]["is_fresh"] is True


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_snapshot_stale(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    # Make snapshot stale by 35 seconds
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=35)
    mock_snapshot_store.get_latest.return_value.timestamp = stale_time

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["compatibility_status"] == "STATUS_HALT"
    assert data["freshness_summary"]["is_fresh"] is False
    assert "live_snapshot" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_feature_stale(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)

    # Make feature bundle stale by 65 seconds
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=65)

    def mock_get_bundle(bundle_id):
        return {"produced_at": stale_time, "bundle_status": "ok", "payload_json": "{}"}

    mock_questdb.get_latest_feature_bundle.side_effect = mock_get_bundle

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["freshness_summary"]["is_fresh"] is False
    # Check that at least one feature is listed as stale
    assert len(data["freshness_summary"]["stale_inputs"]) >= 1


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_missing_signal(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    # Signal is missing
    mock_questdb.get_latest_signal_snapshot.return_value = None

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["freshness_summary"]["is_fresh"] is False
    assert "signal" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_operator_stage_gating(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    # Even if inputs are fresh, shadow mode limits execution to observe_only
    mock_stage.return_value = (OperatorStage.shadow, ExecutionMode.observe_only)

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "observe_only"
    assert data["operator_stage"] == "shadow"
    assert (
        data["compatibility_status"] == "STATUS_HALT"
    )  # observe_only maps to STATUS_HALT
