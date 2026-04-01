from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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


class FakeQuestDBRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.initialized = 0
        self.closed = 0
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def initialize(self) -> None:
        self.initialized += 1

    async def close(self) -> None:
        self.closed += 1

    async def async_send_row(self, _table, symbols, columns, at=None):
        self.rows.append(
            {
                "ts": at,
                "schema_version": symbols["schema_version"],
                "snapshot_json": columns["snapshot_json"],
            }
        )
        self.rows.sort(key=lambda item: item["ts"])
        return True

    async def fetchrow(self, sql, *args):
        self.fetch_calls.append((sql, args))
        if "COUNT(*) AS count" in sql:
            cutoff = args[0]
            return {"count": sum(1 for row in self.rows if row["ts"].replace(tzinfo=None) < cutoff)}
        if "ORDER BY ts DESC LIMIT 1" in sql:
            if not self.rows:
                return None
            return {"snapshot_json": self.rows[-1]["snapshot_json"]}
        raise AssertionError(f"unexpected fetchrow SQL: {sql}")

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        cutoff = args[0]
        return [
            {"snapshot_json": row["snapshot_json"]}
            for row in self.rows
            if row["ts"].replace(tzinfo=None) >= cutoff
        ]

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        cutoff = args[0]
        self.rows = [row for row in self.rows if row["ts"].replace(tzinfo=None) >= cutoff]
        return "DELETE"


def test_store_round_trips_latest_snapshot():
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo)
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
    assert repo.initialized == 1


def test_store_returns_recent_history_in_ascending_order():
    now = datetime(2026, 3, 20, 18, 15, tzinfo=timezone.utc)
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo)
    store.initialize(for_write=True)

    older = _build_snapshot(timestamp=now - timedelta(minutes=12), block_height=941450, price=84100.0)
    middle = _build_snapshot(timestamp=now - timedelta(minutes=5), block_height=941451, price=84200.0)
    latest = _build_snapshot(timestamp=now - timedelta(minutes=1), block_height=941452, price=84300.0)

    store.write_snapshot(older)
    store.write_snapshot(middle)
    store.write_snapshot(latest)

    history = store.get_history(LiveHistoryQuery(minutes=6), now=now)

    assert [item.block_height for item in history] == [941451, 941452]
    assert [item.utxoracle_price for item in history] == [84200.0, 84300.0]


def test_store_prunes_rows_older_than_retention_window():
    now = datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc)
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo, retention_hours=1)
    store.initialize(for_write=True)

    stale_snapshot = _build_snapshot(timestamp=now - timedelta(hours=2), block_height=941430, price=83000.0)
    fresh_snapshot = _build_snapshot(timestamp=now, block_height=941456, price=84211.52)

    store.write_snapshot(stale_snapshot)
    store.write_snapshot(fresh_snapshot)
    deleted = store.prune(now=now)
    history = store.get_history(180, now=now)

    assert deleted == 1
    assert [item.block_height for item in history] == [941456]


def test_store_close_closes_repo():
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo)
    store.initialize(for_write=True)

    store.close()

    assert repo.closed == 1


def test_store_serialize_payload_is_valid_json():
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo)
    store.initialize(for_write=True)
    snapshot = _build_snapshot(
        timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
        block_height=941456,
        price=84211.52,
    )

    store.write_snapshot(snapshot)

    payload = json.loads(repo.rows[0]["snapshot_json"])
    assert payload["block_height"] == 941456
    assert payload["comparison"]["utxo_vs_mempool_bps"] == -2.97


def test_store_write_snapshot_initializes_repo_on_demand():
    repo = FakeQuestDBRepo()
    store = LiveSnapshotStore(repo=repo)

    store.write_snapshot(
        _build_snapshot(
            timestamp=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            block_height=941456,
            price=84211.52,
        )
    )

    assert repo.initialized == 1


async def test_store_questdb_history_uses_python_cutoff_timestamp():
    now = datetime(2026, 3, 31, 16, 30, tzinfo=timezone.utc)
    snapshot = _build_snapshot(timestamp=now - timedelta(minutes=3), block_height=941460, price=84321.11)
    calls: list[tuple[str, object]] = []

    class RecordingRepo(FakeQuestDBRepo):
        async def fetch(self, sql, *args):
            calls.append((sql, args[0]))
            return [{"snapshot_json": snapshot.model_dump_json()}]

    store = LiveSnapshotStore(repo=RecordingRepo())
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
