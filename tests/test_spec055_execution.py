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
        "bundle_status": "healthy",
        "sequence_id": 1,
        "payload_json": "{}",
    }
    repo.get_recent_feature_bundle_sequence.return_value = [
        {"sequence_id": 1, "produced_at": now, "bundle_status": "healthy"}
    ]
    repo.get_latest_signal_snapshot.return_value = {
        "produced_at": now,
        "service_status": "healthy",
        "sequence_id": 1,
        "payload_json": "{}",
    }
    repo.get_recent_signal_sequence.return_value = [
        {"sequence_id": 1, "produced_at": now, "service_status": "healthy"}
    ]
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
    assert data["sequence_summary"]["is_monotonic"] is True


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
        return {
            "produced_at": stale_time,
            "bundle_status": "healthy",
            "sequence_id": 1,
            "payload_json": "{}",
        }

    mock_questdb.get_latest_feature_bundle.side_effect = mock_get_bundle

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["freshness_summary"]["is_fresh"] is False
    # Check that at least one feature is listed as stale
    assert len(data["freshness_summary"]["stale_inputs"]) >= 1


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_missing_snapshot(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    mock_snapshot_store.get_latest.return_value = None

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert "live_snapshot" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_missing_feature_bundle(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    mock_questdb.get_latest_feature_bundle.return_value = None

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert "core_feature" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_missing_questdb_repo(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    app.state.questdb_repo = None

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["compatibility_status"] == "STATUS_HALT"
    assert "signal" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_feature_sequence_gap(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    now = datetime.now(timezone.utc)
    mock_questdb.get_latest_feature_bundle.return_value = {
        "produced_at": now,
        "bundle_status": "healthy",
        "sequence_id": 3,
        "payload_json": "{}",
    }
    mock_questdb.get_recent_feature_bundle_sequence.return_value = [
        {"sequence_id": 3, "produced_at": now, "bundle_status": "healthy"},
        {
            "sequence_id": 1,
            "produced_at": now - timedelta(seconds=5),
            "bundle_status": "healthy",
        },
    ]

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["sequence_summary"]["is_monotonic"] is False
    assert "core_feature_sequence_gap" in data["sequence_summary"]["gaps_detected"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_signal_sequence_missing(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    now = datetime.now(timezone.utc)
    mock_questdb.get_latest_signal_snapshot.return_value = {
        "produced_at": now,
        "service_status": "healthy",
        "payload_json": "{}",
    }
    mock_questdb.get_recent_signal_sequence.return_value = [
        {"produced_at": now, "service_status": "healthy"}
    ]

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert data["sequence_summary"]["is_monotonic"] is False
    assert "signal_sequence_missing" in data["sequence_summary"]["gaps_detected"]


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
def test_execution_fail_closed_degraded_signal(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    now = datetime.now(timezone.utc)
    mock_questdb.get_latest_signal_snapshot.return_value = {
        "produced_at": now,
        "service_status": "degraded",
        "sequence_id": 1,
        "payload_json": "{}",
    }

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert "signal_status_not_ok" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_fail_closed_signal_stale(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=65)
    mock_questdb.get_latest_signal_snapshot.return_value = {
        "produced_at": stale_time,
        "service_status": "healthy",
        "sequence_id": 1,
        "payload_json": "{}",
    }

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert "signal" in data["freshness_summary"]["stale_inputs"]


@patch("api.routes.execution._get_operator_stage")
def test_execution_derivation_exception_fails_closed(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.full_capital, ExecutionMode.trade_enabled)
    mock_snapshot_store.get_latest.side_effect = RuntimeError("snapshot store failed")

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "halted"
    assert "internal_error" in data["freshness_summary"]["stale_inputs"]


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


@patch("api.routes.execution._get_operator_stage")
def test_execution_manage_only_maps_to_liquidate_only(
    mock_stage, client, mock_snapshot_store, mock_questdb
):
    mock_stage.return_value = (OperatorStage.canary_capital, ExecutionMode.manage_only)

    response = client.get("/api/execution/btc/status")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "manage_only"
    assert data["compatibility_status"] == "STATUS_LIQUIDATE_ONLY"


def test_live_health_and_ready_use_30s_stale_threshold(client, mock_snapshot_store):
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=35)
    mock_snapshot_store.get_latest.return_value.timestamp = stale_time

    health_response = client.get("/health")
    assert health_response.status_code == 200
    health_payload = health_response.json()
    assert health_payload["status"] == "degraded"
    assert health_payload["live"]["status"] == "stale"

    ready_response = client.get("/api/v1/live/ready")
    assert ready_response.status_code == 503


def test_operator_stage_config_failure_defaults_to_safe_mode(monkeypatch):
    from api.routes import execution

    monkeypatch.setattr(execution, "EXECUTION_SAFETY_PATH", "/tmp/missing-execution-safety.yaml")

    stage, mode = execution._get_operator_stage()
    assert stage == OperatorStage.shadow
    assert mode == ExecutionMode.observe_only


def test_operator_stage_config_success(monkeypatch, tmp_path):
    from api.routes import execution

    config = tmp_path / "execution_safety.yaml"
    config.write_text(
        """
operator_stage: canary_capital
operator_stages:
  canary_capital:
    max_execution_mode: manage_only
""".lstrip()
    )
    monkeypatch.setattr(execution, "EXECUTION_SAFETY_PATH", config)

    stage, mode = execution._get_operator_stage()
    assert stage == OperatorStage.canary_capital
    assert mode == ExecutionMode.manage_only


def test_execution_helper_sequence_edges():
    from api.routes import execution

    fallback = datetime(2026, 4, 11, tzinfo=timezone.utc)
    assert execution._coerce_datetime("not-a-date", fallback) is fallback
    parsed = execution._coerce_datetime("2026-04-11T12:00:00", fallback)
    assert parsed.tzinfo is not None

    gaps = []
    assert execution._coerce_sequence_id({"sequence_id": "bad"}, "bundle", gaps) is None
    assert "bundle_sequence_invalid" in gaps

    gaps = []
    assert execution._coerce_sequence_id({"sequence_id": 0}, "bundle", gaps) is None
    assert "bundle_sequence_invalid" in gaps

    gaps = []
    assert not execution._check_recent_sequence_rows("bundle", [], gaps)
    assert "bundle_sequence_missing" in gaps

    gaps = []
    assert not execution._check_recent_sequence_rows(
        "bundle",
        [{"sequence_id": 2}, {}],
        gaps,
    )
    assert "bundle_sequence_missing" in gaps

    gaps = []
    assert not execution._check_recent_sequence_rows(
        "bundle",
        [{"sequence_id": 2}, {"sequence_id": 2}],
        gaps,
    )
    assert "bundle_sequence_non_monotonic" in gaps

    gaps = []
    assert not execution._check_recent_sequence_rows(
        "bundle",
        [{"sequence_id": 4}, {"sequence_id": 2}],
        gaps,
    )
    assert "bundle_sequence_gap" in gaps

    gaps = []
    assert execution._check_recent_sequence_rows(
        "bundle",
        [{"sequence_id": 4}, {"sequence_id": 3}],
        gaps,
    )
    assert gaps == []
