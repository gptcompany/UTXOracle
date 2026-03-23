from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.live import build_live_health_summary, get_live_snapshot_store, router
from scripts.live.models import LiveComparison, LiveFeatureSet, LiveSnapshot, SourceHealth, utc_now
from scripts.live.storage import LiveSnapshotStore


def _build_snapshot(*, timestamp: datetime, block_height: int, price: float) -> LiveSnapshot:
    return LiveSnapshot(
        timestamp=timestamp,
        block_height=block_height,
        utxoracle_price=price,
        utxoracle_confidence=0.82,
        mempool_exchange_price=price + 25.0,
        hyperliquid_oracle_price=price + 10.0,
        hyperliquid_mark_price=price + 15.0,
        comparison=LiveComparison(
            utxo_vs_mempool_bps=-2.97,
            utxo_vs_hl_oracle_bps=-1.18,
            utxo_vs_hl_mark_bps=-1.77,
        ),
        features=LiveFeatureSet(
            brk_realized_price=54311.39,
            brk_liveliness=0.6380666186,
            brk_reserve_risk=4.100239e-06,
        ),
        source_health={
            "electrs": SourceHealth(
                status="healthy",
                last_success=timestamp,
                observed_height=block_height,
            )
        },
        source_timestamps={"electrs": timestamp},
    )


def _build_test_client(store: LiveSnapshotStore) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    return TestClient(app)


def test_live_snapshot_endpoint_returns_latest_snapshot(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )
    client = _build_test_client(store)

    response = client.get("/api/v1/live/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["block_height"] == 941456
    assert body["utxoracle_price"] == 84211.52


def test_live_history_endpoint_returns_recent_snapshots(tmp_path):
    now = datetime.now(timezone.utc)
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    store.write_snapshot(_build_snapshot(timestamp=now - timedelta(minutes=10), block_height=941450, price=84100.0))
    store.write_snapshot(_build_snapshot(timestamp=now - timedelta(minutes=4), block_height=941451, price=84200.0))
    store.write_snapshot(_build_snapshot(timestamp=now - timedelta(minutes=1), block_height=941452, price=84300.0))
    client = _build_test_client(store)

    response = client.get("/api/v1/live/history", params={"minutes": 1440})

    assert response.status_code == 200
    body = response.json()
    assert [item["block_height"] for item in body] == [941450, 941451, 941452]


def test_live_comparison_latest_endpoint_returns_compact_payload(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )
    client = _build_test_client(store)

    response = client.get("/api/v1/live/comparison/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["comparison"]["utxo_vs_mempool_bps"] == -2.97
    assert body["hyperliquid_mark_price"] == 84226.52


def test_live_ready_returns_503_when_snapshot_missing(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    client = _build_test_client(store)

    response = client.get("/api/v1/live/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "live snapshot unavailable"


def test_live_ready_returns_503_when_snapshot_is_stale(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    stale_timestamp = utc_now() - timedelta(seconds=61)
    store.write_snapshot(_build_snapshot(timestamp=stale_timestamp, block_height=941456, price=84211.52))
    client = _build_test_client(store)

    response = client.get("/api/v1/live/ready")

    assert response.status_code == 503
    assert "live data is stale" in response.json()["detail"]


def test_build_live_health_summary_reports_unavailable_when_store_empty(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")

    summary = build_live_health_summary(store)

    assert summary["status"] == "unavailable"
    assert summary["sources"] == {}


def test_build_live_health_summary_reports_degraded_sources(tmp_path):
    timestamp = utc_now()
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    snapshot = _build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)
    snapshot.source_health["hyperliquid"] = SourceHealth(status="stale", last_success=timestamp)
    store.write_snapshot(snapshot)

    summary = build_live_health_summary(store)

    assert summary["status"] == "degraded"
    assert summary["block_height"] == 941456
    assert summary["sources"] == {"electrs": "healthy", "hyperliquid": "stale"}


def test_build_live_health_summary_reports_stale_snapshot_age(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize(for_write=True)
    stale_timestamp = utc_now() - timedelta(seconds=61)
    store.write_snapshot(_build_snapshot(timestamp=stale_timestamp, block_height=941456, price=84211.52))

    summary = build_live_health_summary(store)

    assert summary["status"] == "stale"
    assert summary["block_height"] == 941456
