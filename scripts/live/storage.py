from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from api.questdb_repository import QuestDBRepository
from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now

logger = logging.getLogger(__name__)


class LiveSnapshotStore:
    """Hybrid live snapshot store.

    An explicit ``db_path`` keeps the existing SQLite WAL contract used by the live
    worker and tests. Omitting ``db_path`` switches reads and writes to QuestDB for
    the production app surface.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        retention_hours: int = 24,
        lock_path: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        self.retention_hours = retention_hours
        self.lock_path = (
            Path(lock_path)
            if lock_path
            else self.db_path.with_suffix(".lock") if self.db_path is not None else None
        )
        self.repo = QuestDBRepository() if self.db_path is None else None
        self._initialized = False
        self._lock_fd: int | None = None

    def initialize(self, *, for_write: bool = False) -> None:
        if self.db_path is None:
            self._run_async(self.ainitialize(for_write=for_write))
            return
        self._initialize_sqlite(for_write=for_write)

    async def ainitialize(self, *, for_write: bool = False) -> None:
        if self.db_path is None:
            if not self._initialized:
                assert self.repo is not None
                await self.repo.initialize()
                self._initialized = True
            return
        await asyncio.to_thread(self._initialize_sqlite, for_write=for_write)

    def close(self) -> None:
        if self.db_path is None:
            self._run_async(self.aclose())
            return
        self._close_sqlite()

    async def aclose(self) -> None:
        if self.db_path is None:
            if self._initialized and self.repo is not None:
                await self.repo.close()
            self._initialized = False
            return
        await asyncio.to_thread(self._close_sqlite)

    def write_snapshot(self, snapshot: LiveSnapshot) -> None:
        if self.db_path is None:
            self._run_async(self.awrite_snapshot(snapshot))
            return
        self._write_snapshot_sqlite(snapshot)

    async def awrite_snapshot(self, snapshot: LiveSnapshot) -> None:
        if self.db_path is None:
            if not self._initialized:
                await self.ainitialize(for_write=True)

            payload = snapshot.model_dump(mode="json")
            assert self.repo is not None
            success = await self.repo.async_send_row(
                "live_snapshots",
                symbols={"schema_version": snapshot.schema_version},
                columns={
                    "snapshot_ts": snapshot.timestamp,
                    "block_height": snapshot.block_height,
                    "utxoracle_price": snapshot.utxoracle_price,
                    "utxoracle_confidence": snapshot.utxoracle_confidence,
                    "mempool_exchange_price": snapshot.mempool_exchange_price,
                    "hyperliquid_oracle_price": snapshot.hyperliquid_oracle_price,
                    "hyperliquid_mark_price": snapshot.hyperliquid_mark_price,
                    "comparison_json": json.dumps(payload["comparison"], sort_keys=True),
                    "features_json": json.dumps(payload["features"], sort_keys=True),
                    "source_health_json": json.dumps(payload["source_health"], sort_keys=True),
                    "source_timestamps_json": json.dumps(
                        payload["source_timestamps"], sort_keys=True
                    ),
                    "snapshot_json": json.dumps(payload, sort_keys=True),
                },
                at=snapshot.timestamp,
            )
            if not success:
                logger.error("Failed to write live snapshot to QuestDB at %s", snapshot.timestamp)
            return

        await asyncio.to_thread(self._write_snapshot_sqlite, snapshot)

    def get_latest(self) -> LiveSnapshot | None:
        if self.db_path is None:
            return self._run_async(self.aget_latest())
        return self._get_latest_sqlite()

    async def aget_latest(self) -> LiveSnapshot | None:
        if self.db_path is None:
            if not self._initialized:
                await self.ainitialize()
            assert self.repo is not None
            row = await self.repo.fetchrow(
                "SELECT snapshot_json FROM live_snapshots ORDER BY ts DESC LIMIT 1"
            )
            return self._deserialize_snapshot(row["snapshot_json"]) if row else None

        return await asyncio.to_thread(self._get_latest_sqlite)

    def get_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        if self.db_path is None:
            return self._run_async(self.aget_history(query, now=now))
        return self._get_history_sqlite(query, now=now)

    async def aget_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        if self.db_path is None:
            if not self._initialized:
                await self.ainitialize()

            if query is None:
                query = LiveHistoryQuery()
            elif isinstance(query, int):
                query = LiveHistoryQuery(minutes=query)

            start_time = ((now or utc_now()) - timedelta(minutes=query.minutes)).replace(tzinfo=None)
            sql = (
                "SELECT snapshot_json FROM live_snapshots "
                "WHERE ts >= $1 ORDER BY ts ASC"
            )
            assert self.repo is not None
            rows = await self.repo.fetch(sql, start_time)
            return [self._deserialize_snapshot(row["snapshot_json"]) for row in rows]

        return await asyncio.to_thread(self._get_history_sqlite, query, now=now)

    def prune(self, *, now: datetime | None = None) -> int:
        if self.db_path is None:
            return self._run_async(self.aprune(now=now))
        return self._prune_sqlite(now=now)

    async def aprune(self, *, now: datetime | None = None) -> int:
        if self.db_path is None:
            return 0
        return await asyncio.to_thread(self._prune_sqlite, now=now)

    def _initialize_sqlite(self, *, for_write: bool = False) -> None:
        assert self.db_path is not None
        self._ensure_parent_dir()

        if for_write and self._lock_fd is None:
            self._acquire_lock()

        if not self._initialized:
            self._initialized = True

        if for_write:
            with self._connect(for_write=True) as conn:
                self._ensure_schema(conn)

    def _close_sqlite(self) -> None:
        if self._lock_fd is None:
            return

        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
        except OSError:
            pass
        finally:
            self._lock_fd = None
            self._initialized = False

    def _write_snapshot_sqlite(self, snapshot: LiveSnapshot) -> None:
        if not self._initialized:
            raise RuntimeError(
                "LiveSnapshotStore.initialize() must be called before write_snapshot()"
            )

        payload = snapshot.model_dump(mode="json")
        snapshot_ts_iso = snapshot.timestamp.isoformat()

        with self._connect(for_write=True) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    "DELETE FROM live_snapshots WHERE snapshot_ts = ?",
                    [snapshot_ts_iso],
                )
                conn.execute(
                    """
                    INSERT INTO live_snapshots (
                        snapshot_ts,
                        schema_version,
                        block_height,
                        utxoracle_price,
                        utxoracle_confidence,
                        mempool_exchange_price,
                        hyperliquid_oracle_price,
                        hyperliquid_mark_price,
                        comparison_json,
                        features_json,
                        source_health_json,
                        source_timestamps_json,
                        snapshot_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        snapshot_ts_iso,
                        snapshot.schema_version,
                        snapshot.block_height,
                        snapshot.utxoracle_price,
                        snapshot.utxoracle_confidence,
                        snapshot.mempool_exchange_price,
                        snapshot.hyperliquid_oracle_price,
                        snapshot.hyperliquid_mark_price,
                        json.dumps(payload["comparison"], sort_keys=True),
                        json.dumps(payload["features"], sort_keys=True),
                        json.dumps(payload["source_health"], sort_keys=True),
                        json.dumps(payload["source_timestamps"], sort_keys=True),
                        json.dumps(payload, sort_keys=True),
                    ],
                )

                if self.retention_hours > 0:
                    cutoff = (
                        snapshot.timestamp - timedelta(hours=self.retention_hours)
                    ).isoformat()
                    conn.execute(
                        "DELETE FROM live_snapshots WHERE snapshot_ts < ?",
                        [cutoff],
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _get_latest_sqlite(self) -> LiveSnapshot | None:
        assert self.db_path is not None
        if not self.db_path.exists():
            return None

        try:
            with self._connect(for_write=False) as conn:
                row = conn.execute(
                    """
                    SELECT snapshot_json
                    FROM live_snapshots
                    ORDER BY snapshot_ts DESC
                    LIMIT 1
                    """
                ).fetchone()
        except sqlite3.OperationalError:
            return None

        return self._deserialize_snapshot(row[0]) if row else None

    def _get_history_sqlite(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        assert self.db_path is not None
        if not self.db_path.exists():
            return []

        if query is None:
            query = LiveHistoryQuery()
        elif isinstance(query, int):
            query = LiveHistoryQuery(minutes=query)

        start_time_iso = ((now or utc_now()) - timedelta(minutes=query.minutes)).isoformat()

        try:
            with self._connect(for_write=False) as conn:
                rows = conn.execute(
                    """
                    SELECT snapshot_json
                    FROM live_snapshots
                    WHERE snapshot_ts >= ?
                    ORDER BY snapshot_ts ASC
                    """,
                    [start_time_iso],
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        return [self._deserialize_snapshot(row[0]) for row in rows]

    def _prune_sqlite(self, *, now: datetime | None = None) -> int:
        assert self.db_path is not None
        if self.retention_hours <= 0 or not self.db_path.exists():
            return 0

        cutoff = ((now or utc_now()) - timedelta(hours=self.retention_hours)).isoformat()

        with self._connect(for_write=True) as conn:
            deleted = conn.execute(
                "SELECT COUNT(*) FROM live_snapshots WHERE snapshot_ts < ?",
                [cutoff],
            ).fetchone()
            conn.execute(
                "DELETE FROM live_snapshots WHERE snapshot_ts < ?",
                [cutoff],
            )

        return int(deleted[0]) if deleted else 0

    def _connect(self, *, for_write: bool) -> sqlite3.Connection:
        assert self.db_path is not None
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        if for_write:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_parent_dir(self) -> None:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _acquire_lock(self) -> None:
        assert self.lock_path is not None
        try:
            self._lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            raise RuntimeError(
                f"Could not acquire lock on {self.lock_path}. Another worker process might be running."
            )

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_snapshots (
                snapshot_ts TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                block_height INTEGER,
                utxoracle_price REAL,
                utxoracle_confidence REAL,
                mempool_exchange_price REAL,
                hyperliquid_oracle_price REAL,
                hyperliquid_mark_price REAL,
                comparison_json TEXT NOT NULL,
                features_json TEXT NOT NULL,
                source_health_json TEXT NOT NULL,
                source_timestamps_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_live_snapshots_ts
            ON live_snapshots(snapshot_ts)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_live_snapshots_height
            ON live_snapshots(block_height)
            """
        )

    @staticmethod
    def _run_async(awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError(
            "LiveSnapshotStore sync methods cannot be called from an active event loop. "
            "Use the async store methods instead."
        )

    @staticmethod
    def _deserialize_snapshot(raw_payload: str) -> LiveSnapshot:
        return LiveSnapshot.model_validate(json.loads(raw_payload))
