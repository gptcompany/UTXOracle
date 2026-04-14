from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import pytest
from fastapi.testclient import TestClient

from api.routes.live import get_live_snapshot_store
from api.apps.live import _reload_registry_if_changed
from scripts.live.models import LiveComparison, LiveFeatureSet, LiveSnapshot, SourceHealth


class InMemorySnapshotStore:
    def __init__(self, snapshots: list[LiveSnapshot] | None = None) -> None:
        self.snapshots = list(snapshots or [])
        self.closed = False

    async def get_latest(self, *, now: datetime | None = None) -> LiveSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    async def get_history(self, query=None, *, now: datetime | None = None) -> list[LiveSnapshot]:
        return list(self.snapshots)

    async def close(self) -> None:
        self.closed = True


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
            "electrs": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "mempool_api": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "utxoracle": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
        },
        source_timestamps={"electrs": timestamp, "mempool_api": timestamp, "utxoracle": timestamp},
    )


def _build_client(store: InMemorySnapshotStore) -> TestClient:
    from api.apps.live import create_app

    app = create_app()
    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    return TestClient(app)


def test_live_production_app_exposes_live_and_derived_routes_with_fallbacks():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/live/snapshot").status_code == 200
        assert client.get("/api/v1/live/history", params={"minutes": 60}).status_code == 200
        assert client.get("/charts/live-price-comparison").status_code == 200

        assert client.get("/api/prices/latest").status_code == 503
        assert client.get("/api/metrics/latest").status_code == 503
        assert client.get("/api/whale/latest").status_code == 404


def test_live_production_health_reports_live_summary():
    timestamp = datetime.now(timezone.utc)
    store = InMemorySnapshotStore([_build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)])

    with _build_client(store) as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["utxoracle_live"]["status"] == "ok"
    assert data["live"]["block_height"] == 941456
    assert data["live"]["status"] == "healthy"


def test_live_production_health_degrades_when_snapshot_is_stale():
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=61)
    store = InMemorySnapshotStore([_build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)])

    with _build_client(store) as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["utxoracle_live"]["status"] == "error"
    assert data["live"]["status"] == "stale"


def test_live_production_app_closes_snapshot_store_on_shutdown():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store):
        pass

    assert store.closed is True


def test_live_production_chart_page_is_html():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/charts/live-price-comparison")
        realized_response = client.get("/charts/realized-price-reference")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "live-price-comparison" in response.text
    assert "realized-price-reference" in response.text
    assert "compare-toggle" in response.text
    assert realized_response.status_code == 200
    assert realized_response.headers["content-type"].startswith("text/html")


def test_live_production_chart_page_rejects_unknown_chart_id():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/charts/unknown")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reload_registry_if_changed_only_reloads_on_mtime_change(tmp_path):
    registry_path = tmp_path / "exchange_addresses.csv"
    registry_path.write_text("exchange_name,address,type\n", encoding="utf-8")

    class FakeMonitor:
        def __init__(self) -> None:
            self.reloads = 0

        async def reload_exchange_registry(self) -> None:
            self.reloads += 1

    monitor = FakeMonitor()
    first_mtime = registry_path.stat().st_mtime

    same_mtime = await _reload_registry_if_changed(monitor, registry_path, first_mtime)
    assert same_mtime == first_mtime
    assert monitor.reloads == 0

    registry_path.write_text("exchange_name,address,type\nBinance,addr,wallet\n", encoding="utf-8")
    os.utime(registry_path, (first_mtime + 5, first_mtime + 5))
    changed_mtime = await _reload_registry_if_changed(monitor, registry_path, first_mtime)

    assert changed_mtime is not None
    assert changed_mtime != first_mtime
    assert monitor.reloads == 1
