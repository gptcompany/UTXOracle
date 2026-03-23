from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now

DEFAULT_DUCKDB_CONNECT_RETRY_ATTEMPTS = int(
    os.getenv("LIVE_DUCKDB_CONNECT_RETRY_ATTEMPTS", "5")
)
DEFAULT_DUCKDB_CONNECT_RETRY_BACKOFF_SECONDS = float(
    os.getenv("LIVE_DUCKDB_CONNECT_RETRY_BACKOFF_SECONDS", "0.05")
)


class LiveSnapshotStore:
    """DuckDB-backed storage for short-horizon live snapshots."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        retention_hours: int = 24,
        lock_path: str | Path | None = None,
        connect_retry_attempts: int = DEFAULT_DUCKDB_CONNECT_RETRY_ATTEMPTS,
        connect_retry_backoff_seconds: float = DEFAULT_DUCKDB_CONNECT_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.db_path = Path(db_path)
        self.retention_hours = retention_hours
        self.lock_path = Path(lock_path) if lock_path else self.db_path.with_suffix(".lock")
        self.connect_retry_attempts = max(int(connect_retry_attempts), 1)
        self.connect_retry_backoff_seconds = max(float(connect_retry_backoff_seconds), 0.0)
        self._initialized = False
        self._lock_fd: int | None = None

    def initialize(self, *, for_write: bool = False) -> None:
        self._ensure_parent_dir()

        if for_write and self._lock_fd is None:
            self._acquire_lock()

        if not self._initialized:
            self._initialized = True

        if for_write:
            with self._connect(read_only=False) as conn:
                self._ensure_schema(conn)

    def _acquire_lock(self) -> None:
        """Acquire an exclusive lock on the lockfile."""
        try:
            self._lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            raise RuntimeError(
                f"Could not acquire lock on {self.lock_path}. "
                "Another worker process might be running."
            )

    def close(self) -> None:
        """Release the lock and clean up."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    def write_snapshot(self, snapshot: LiveSnapshot) -> None:
        if not self._initialized:
            raise RuntimeError("LiveSnapshotStore.initialize() must be called before write_snapshot()")

        payload = snapshot.model_dump(mode="json")

        with self._connect(read_only=False) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    "DELETE FROM live_snapshots WHERE snapshot_ts = ?",
                    [snapshot.timestamp],
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
                        snapshot.timestamp,
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
                    cutoff = snapshot.timestamp - timedelta(hours=self.retention_hours)
                    conn.execute(
                        "DELETE FROM live_snapshots WHERE snapshot_ts < ?",
                        [cutoff],
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_latest(self) -> LiveSnapshot | None:
        if not self.db_path.exists():
            return None

        try:
            with self._connect(read_only=True) as conn:
                row = conn.execute(
                    """
                    SELECT snapshot_json
                    FROM live_snapshots
                    ORDER BY snapshot_ts DESC
                    LIMIT 1
                    """
                ).fetchone()
        except duckdb.CatalogException:
            return None

        return self._deserialize_snapshot(row[0]) if row else None

    def get_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        if not self.db_path.exists():
            return []

        if query is None:
            query = LiveHistoryQuery()
        elif isinstance(query, int):
            query = LiveHistoryQuery(minutes=query)

        start_time = (now or utc_now()) - timedelta(minutes=query.minutes)

        try:
            with self._connect(read_only=True) as conn:
                rows = conn.execute(
                    """
                    SELECT snapshot_json
                    FROM live_snapshots
                    WHERE snapshot_ts >= ?
                    ORDER BY snapshot_ts ASC
                    """,
                    [start_time],
                ).fetchall()
        except duckdb.CatalogException:
            return []

        return [self._deserialize_snapshot(row[0]) for row in rows]

    def prune(self, *, now: datetime | None = None) -> int:
        if self.retention_hours <= 0 or not self.db_path.exists():
            return 0

        cutoff = (now or utc_now()) - timedelta(hours=self.retention_hours)

        with self._connect(read_only=False) as conn:
            deleted = conn.execute(
                "SELECT COUNT(*) FROM live_snapshots WHERE snapshot_ts < ?",
                [cutoff],
            ).fetchone()
            conn.execute(
                "DELETE FROM live_snapshots WHERE snapshot_ts < ?",
                [cutoff],
            )

        return int(deleted[0]) if deleted else 0

    def _connect(self, *, read_only: bool) -> duckdb.DuckDBPyConnection:
        for attempt in range(1, self.connect_retry_attempts + 1):
            try:
                return duckdb.connect(str(self.db_path), read_only=read_only)
            except duckdb.IOException as exc:
                if not self._is_retryable_connect_error(exc) or attempt >= self.connect_retry_attempts:
                    raise
                delay = self.connect_retry_backoff_seconds * attempt
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError("duckdb connection retries exhausted")

    @staticmethod
    def _is_retryable_connect_error(exc: duckdb.IOException) -> bool:
        message = str(exc)
        return (
            "Could not set lock on file" in message
            or "Conflicting lock is held" in message
        )

    def _ensure_parent_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_snapshots (
                snapshot_ts TIMESTAMPTZ PRIMARY KEY,
                schema_version VARCHAR NOT NULL,
                block_height BIGINT,
                utxoracle_price DOUBLE,
                utxoracle_confidence DOUBLE,
                mempool_exchange_price DOUBLE,
                hyperliquid_oracle_price DOUBLE,
                hyperliquid_mark_price DOUBLE,
                comparison_json TEXT NOT NULL,
                features_json TEXT NOT NULL,
                source_health_json TEXT NOT NULL,
                source_timestamps_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    def _deserialize_snapshot(raw_payload: str) -> LiveSnapshot:
        return LiveSnapshot.model_validate(json.loads(raw_payload))
