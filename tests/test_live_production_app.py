from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import time

import pytest
from fastapi.testclient import TestClient

from api.routes.live import get_live_snapshot_store
from api.apps.live import _reload_registry_if_changed
from scripts.live.models import (
    LiveComparison,
    LiveFeatureSet,
    LiveSnapshot,
    SourceHealth,
)


class InMemorySnapshotStore:
    def __init__(self, snapshots: list[LiveSnapshot] | None = None) -> None:
        self.snapshots = list(snapshots or [])
        self.closed = False

    async def get_latest(self, *, now: datetime | None = None) -> LiveSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    async def get_history(
        self, query=None, *, now: datetime | None = None
    ) -> list[LiveSnapshot]:
        return list(self.snapshots)

    async def close(self) -> None:
        self.closed = True


def _build_snapshot(
    *, timestamp: datetime, block_height: int, price: float
) -> LiveSnapshot:
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
                status="healthy", last_success=timestamp, observed_height=block_height
            ),
            "mempool_api": SourceHealth(
                status="healthy", last_success=timestamp, observed_height=block_height
            ),
            "utxoracle": SourceHealth(
                status="healthy", last_success=timestamp, observed_height=block_height
            ),
        },
        source_timestamps={
            "electrs": timestamp,
            "mempool_api": timestamp,
            "utxoracle": timestamp,
        },
    )


class _UnavailableQuestDBRepository:
    """QuestDB repository whose startup fails, as when the database is down."""

    async def initialize(self) -> None:
        raise ConnectionError("QuestDB unavailable (test)")

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def questdb_down(monkeypatch):
    """Make the derived routes' degraded state independent of the test host.

    QuestDBRepository.initialize() would otherwise try a real QuestDB: the routes then
    answered 404, 500 or 503 depending on whether one runs on the machine.
    """
    from api.apps import live as live_app

    monkeypatch.setattr(live_app, "QuestDBRepository", _UnavailableQuestDBRepository)


def _build_client(store: InMemorySnapshotStore) -> TestClient:
    from api.apps.live import create_app

    app = create_app()
    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    return TestClient(app)


def test_live_production_app_exposes_live_and_derived_routes_with_fallbacks():
    store = InMemorySnapshotStore(
        [
            _build_snapshot(
                timestamp=datetime.now(timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        ]
    )

    with _build_client(store) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/live/snapshot").status_code == 200
        assert (
            client.get("/api/v1/live/history", params={"minutes": 60}).status_code
            == 200
        )
        assert client.get("/charts/live-price-comparison").status_code == 200

        assert client.get("/api/prices/latest").status_code == 503
        assert client.get("/api/metrics/latest").status_code == 503
        assert client.get("/api/whale/latest").status_code == 404


def test_live_production_health_reports_live_summary():
    timestamp = datetime.now(timezone.utc)
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)]
    )

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
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=timestamp, block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["utxoracle_live"]["status"] == "error"
    assert data["live"]["status"] == "stale"


def test_live_production_app_closes_snapshot_store_on_shutdown():
    store = InMemorySnapshotStore(
        [
            _build_snapshot(
                timestamp=datetime.now(timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        ]
    )

    with _build_client(store):
        pass

    assert store.closed is True


def test_live_production_chart_page_is_html():
    store = InMemorySnapshotStore(
        [
            _build_snapshot(
                timestamp=datetime.now(timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        ]
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
        [
            _build_snapshot(
                timestamp=datetime.now(timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        ]
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

    registry_path.write_text(
        "exchange_name,address,type\nBinance,addr,wallet\n", encoding="utf-8"
    )
    os.utime(registry_path, (first_mtime + 5, first_mtime + 5))
    changed_mtime = await _reload_registry_if_changed(
        monitor, registry_path, first_mtime
    )

    assert changed_mtime is not None
    assert changed_mtime != first_mtime
    assert monitor.reloads == 1


class _FlakyQuestDBRepository:
    """Fails the first `failures` initialize() calls, then succeeds (the startup race of F-399)."""

    failures = 2
    attempts = 0

    async def initialize(self) -> None:
        type(self).attempts += 1
        if type(self).attempts <= type(self).failures:
            raise ConnectionError("Connection refused (test)")

    async def close(self) -> None:
        return None


class _IdleWhaleMonitor:
    """Stands in for MempoolWhaleMonitor, whose default would open a mempool websocket."""

    repo = None
    broadcaster = None

    async def start(self) -> None:
        await asyncio.Event().wait()

    async def stop(self) -> None:
        return None


def _flaky_repository(monkeypatch, failures: int) -> type:
    from api.apps import live as live_app
    from scripts import mempool_whale_monitor

    monkeypatch.setattr(mempool_whale_monitor, "MempoolWhaleMonitor", _IdleWhaleMonitor)

    repository = type(
        "FlakyRepository",
        (_FlakyQuestDBRepository,),
        {"failures": failures, "attempts": 0},
    )
    monkeypatch.setattr(live_app, "QuestDBRepository", repository)
    monkeypatch.setattr(live_app, "QUESTDB_RETRY_INITIAL_SECONDS", 0.01)
    monkeypatch.setattr(live_app, "QUESTDB_RETRY_MAX_SECONDS", 0.02)
    return repository


def _empty_store() -> InMemorySnapshotStore:
    return InMemorySnapshotStore([])


def test_questdb_repository_is_set_after_two_failed_attempts(monkeypatch, caplog):
    repository = _flaky_repository(monkeypatch, failures=2)

    with caplog.at_level("INFO"), _build_client(_empty_store()) as client:
        deadline = time.monotonic() + 5
        while client.app.state.questdb_repo is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert isinstance(client.app.state.questdb_repo, repository)
        retry_task = client.app.state.questdb_retry_task

    assert repository.attempts == 3
    warnings = [r for r in caplog.records if "repository unavailable" in r.getMessage()]
    assert len(warnings) == 2
    assert "Connection refused (test)" in warnings[0].getMessage()
    assert any("repository initialized" in r.getMessage() for r in caplog.records)
    assert retry_task.done()


def test_questdb_repository_stays_unavailable_with_a_logged_reason_and_task_is_cancelled(
    monkeypatch, caplog
):
    repository = _flaky_repository(monkeypatch, failures=10**6)

    with caplog.at_level("WARNING"), _build_client(_empty_store()) as client:
        deadline = time.monotonic() + 5
        while repository.attempts < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.app.state.questdb_repo is None
        retry_task = client.app.state.questdb_retry_task
        assert not retry_task.done()
        # A derived route keeps answering 503 while the repository is missing.
        assert client.get("/api/prices/latest").status_code == 503

    assert retry_task.cancelled()
    assert any(
        "repository unavailable" in r.getMessage()
        and "Connection refused (test)" in r.getMessage()
        for r in caplog.records
    )


def test_startup_does_not_start_a_retry_task_when_questdb_is_up(monkeypatch):
    repository = _flaky_repository(monkeypatch, failures=0)

    with _build_client(_empty_store()) as client:
        assert isinstance(client.app.state.questdb_repo, repository)
        assert client.app.state.questdb_retry_task is None
