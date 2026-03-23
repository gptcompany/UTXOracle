from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb
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
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
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
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
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
    store = LiveSnapshotStore(tmp_path / "live.duckdb", retention_hours=1)
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


def test_store_uses_read_only_connections_for_reads(tmp_path, monkeypatch):
    db_path = tmp_path / "live.duckdb"
    store = LiveSnapshotStore(db_path)
    store.initialize(for_write=True)
    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )

    original_connect = duckdb.connect
    observed_modes: list[bool] = []

    def tracking_connect(*args, **kwargs):
        observed_modes.append(bool(kwargs.get("read_only", False)))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr("scripts.live.storage.duckdb.connect", tracking_connect)

    assert store.get_latest() is not None
    assert len(store.get_history(60, now=datetime(2026, 3, 20, 18, 30, tzinfo=timezone.utc))) == 1
    assert observed_modes
    assert all(observed_modes)


def test_store_write_snapshot_requires_initialize(tmp_path):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")

    with pytest.raises(RuntimeError, match="initialize"):
        store.write_snapshot(
            _build_snapshot(
                timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
                block_height=941456,
                price=84211.52,
            )
        )


def test_store_write_snapshot_skips_schema_check_after_initialize(tmp_path, monkeypatch):
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
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
