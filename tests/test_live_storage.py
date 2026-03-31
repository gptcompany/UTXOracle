from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.live.models import (
    LiveComparison,
    LiveFeatureSet,
    LiveHistoryQuery,
    LiveSnapshot,
    SourceHealth,
)
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
            ),
            "hyperliquid": SourceHealth(status="healthy", last_success=timestamp),
        },
        source_timestamps={
            "electrs": timestamp,
            "hyperliquid": timestamp,
        },
    )


def test_store_round_trips_latest_snapshot(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.sqlite3")
    snapshot = _build_snapshot(
        timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
        block_height=941456,
        price=84211.52,
    )

    store.initialize(for_write=True)
    store.write_snapshot(snapshot)
    latest = store.get_latest()

    assert latest is not None
    assert latest.timestamp == snapshot.timestamp
    assert latest.block_height == 941456
    assert latest.utxoracle_price == 84211.52
    assert latest.features.brk_liveliness == snapshot.features.brk_liveliness
    assert latest.source_health["electrs"].observed_height == 941456


def test_store_returns_recent_history_in_ascending_order(tmp_path):
    now = datetime(2026, 3, 20, 18, 15, tzinfo=timezone.utc)
    store = LiveSnapshotStore(tmp_path / "live.sqlite3")
    store.initialize(for_write=True)

    older = _build_snapshot(
        timestamp=now - timedelta(minutes=12),
        block_height=941450,
        price=84100.0,
    )
    middle = _build_snapshot(
        timestamp=now - timedelta(minutes=5),
        block_height=941451,
        price=84200.0,
    )
    latest = _build_snapshot(
        timestamp=now - timedelta(minutes=1),
        block_height=941452,
        price=84300.0,
    )

    store.write_snapshot(older)
    store.write_snapshot(middle)
    store.write_snapshot(latest)

    history = store.get_history(LiveHistoryQuery(minutes=6), now=now)

    assert [item.block_height for item in history] == [941451, 941452]
    assert [item.utxoracle_price for item in history] == [84200.0, 84300.0]


def test_store_prunes_rows_older_than_retention_window(tmp_path):
    now = datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc)
    store = LiveSnapshotStore(tmp_path / "live.sqlite3", retention_hours=1)
    store.initialize(for_write=True)

    stale_snapshot = _build_snapshot(
        timestamp=now - timedelta(hours=2),
        block_height=941430,
        price=83000.0,
    )
    fresh_snapshot = _build_snapshot(
        timestamp=now,
        block_height=941456,
        price=84211.52,
    )

    store.write_snapshot(stale_snapshot)
    store.write_snapshot(fresh_snapshot)

    history = store.get_history(180, now=now)

    assert [item.block_height for item in history] == [941456]


def test_store_enables_wal_mode_for_writes(tmp_path):
    db_path = tmp_path / "live.sqlite3"
    store = LiveSnapshotStore(db_path)
    store.initialize(for_write=True)
    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )

    # Validate WAL mode was enabled
    conn = sqlite3.connect(str(db_path))
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    
    # Depending on sqlite versions and platform, it may say 'wal' or 'WAL'
    assert journal_mode.lower() == "wal"


def test_store_write_snapshot_requires_initialize(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.sqlite3")

    with pytest.raises(RuntimeError, match="initialize"):
        store.write_snapshot(
            _build_snapshot(
                timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        )


def test_store_write_snapshot_skips_schema_check_after_initialize(tmp_path, monkeypatch):
    store = LiveSnapshotStore(tmp_path / "live.sqlite3")
    store.initialize(for_write=True)
    schema_calls = []

    def tracking_schema(_conn):
        schema_calls.append(True)

    monkeypatch.setattr(store, "_ensure_schema", tracking_schema)

    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )

    assert schema_calls == []


@pytest.mark.asyncio
async def test_store_questdb_history_uses_python_cutoff_timestamp(monkeypatch):
    now = datetime(2026, 3, 31, 16, 30, tzinfo=timezone.utc)
    snapshot = _build_snapshot(
        timestamp=now - timedelta(minutes=3),
        block_height=941460,
        price=84321.11,
    )
    calls: list[tuple[str, object]] = []

    class FakeRepo:
        async def fetch(self, sql, *args):
            calls.append((sql, args[0]))
            return [{"snapshot_json": snapshot.model_dump_json()}]

    store = LiveSnapshotStore(None)
    store.repo = FakeRepo()
    store._initialized = True

    history = await store.aget_history(LiveHistoryQuery(minutes=15), now=now)

    assert len(history) == 1
    assert history[0].block_height == 941460
    assert calls == [
        (
            "SELECT snapshot_json FROM live_snapshots WHERE ts >= $1 ORDER BY ts ASC",
            (now - timedelta(minutes=15)).replace(tzinfo=None),
        )
    ]
