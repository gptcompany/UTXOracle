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


class FakeSnapshotStore:
    def __init__(self, snapshots: list[LiveSnapshot] | None = None, *, retention_hours: int = 24) -> None:
        self.snapshots = list(snapshots or [])
        self.retention_hours = retention_hours

    async def aget_latest(self) -> LiveSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    async def aget_history(self, query=None, *, now=None) -> list[LiveSnapshot]:
        if query is None:
            return list(self.snapshots)
        minutes = getattr(query, "minutes", query)
        cutoff = (now or utc_now()) - timedelta(minutes=minutes)
        return [snapshot for snapshot in self.snapshots if snapshot.timestamp >= cutoff]

    def get_latest(self) -> LiveSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


def test_get_live_snapshot_store_uses_questdb_only_retention_from_env(monkeypatch):
    monkeypatch.delenv("LIVE_DB_PATH", raising=False)
    monkeypatch.setenv("LIVE_RETENTION_HOURS", "12")
    get_live_snapshot_store.cache_clear()

    store = get_live_snapshot_store()

    assert isinstance(store, LiveSnapshotStore)
    assert store.retention_hours == 12
    get_live_snapshot_store.cache_clear()


def _build_test_client(store) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    return TestClient(app)


def test_live_snapshot_endpoint_returns_latest_snapshot():
    store = FakeSnapshotStore(
        [_build_snapshot(timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc), block_height=941456, price=84211.52)]
    )
    client = _build_test_client(store)

    response = client.get("/api/v1/live/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["block_height"] == 941456
    assert body["utxoracle_price"] == 84211.52


def test_live_history_endpoint_returns_recent_snapshots():
    now = datetime.now(timezone.utc)
    store = FakeSnapshotStore(
        [
            _build_snapshot(timestamp=now - timedelta(minutes=10), block_height=941450, price=84100.0),
            _build_snapshot(timestamp=now - timedelta(minutes=4), block_height=941451, price=84200.0),
            _build_snapshot(timestamp=now - timedelta(minutes=1), block_height=941452, price=84300.0),
        ]
    )
    client = _build_test_client(store)

    response = client.get("/api/v1/live/history", params={"minutes": 1440})

    assert response.status_code == 200
    body = response.json()
    assert [item["block_height"] for item in body] == [941450, 941451, 941452]


def test_live_comparison_latest_endpoint_returns_compact_payload():
    store = FakeSnapshotStore(
        [_build_snapshot(timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc), block_height=941456, price=84211.52)]
    )
    client = _build_test_client(store)

    response = client.get("/api/v1/live/comparison/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["comparison"]["utxo_vs_mempool_bps"] == -2.97
    assert body["hyperliquid_mark_price"] == 84226.52


def test_live_ready_returns_503_when_snapshot_missing():
    client = _build_test_client(FakeSnapshotStore())

    response = client.get("/api/v1/live/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "live snapshot unavailable"


def test_live_ready_returns_503_when_snapshot_is_stale():
    stale_timestamp = utc_now() - timedelta(seconds=61)
    client = _build_test_client(
        FakeSnapshotStore([_build_snapshot(timestamp=stale_timestamp, block_height=941456, price=84211.52)])
    )

    response = client.get("/api/v1/live/ready")

    assert response.status_code == 503
    assert "live data is stale" in response.json()["detail"]


def test_build_live_health_summary_reports_unavailable_when_store_empty():
    summary = build_live_health_summary(FakeSnapshotStore())

    assert summary["status"] == "unavailable"
    assert summary["sources"] == {}


def test_build_live_health_summary_reports_degraded_sources():
    timestamp = utc_now()
    snapshot = _build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)
    snapshot.source_health["hyperliquid"] = SourceHealth(status="stale", last_success=timestamp)

    summary = build_live_health_summary(FakeSnapshotStore([snapshot]))

    assert summary["status"] == "degraded"
    assert summary["block_height"] == 941456
    assert summary["sources"] == {"electrs": "healthy", "hyperliquid": "stale"}


def test_build_live_health_summary_reports_stale_snapshot_age():
    stale_timestamp = utc_now() - timedelta(seconds=61)
    summary = build_live_health_summary(
        FakeSnapshotStore([_build_snapshot(timestamp=stale_timestamp, block_height=941456, price=84211.52)])
    )

    assert summary["status"] == "stale"
    assert summary["block_height"] == 941456
