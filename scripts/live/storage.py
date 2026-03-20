from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now


class LiveSnapshotStore:
    """DuckDB-backed storage for short-horizon live snapshots.

    The intended runtime model is:
    - worker process: single writer with short-lived write connections
    - API process: read-only readers with short-lived read connections
    """

    def __init__(self, db_path: str | Path, *, retention_hours: int = 24) -> None:
        self.db_path = Path(db_path)
        self.retention_hours = retention_hours

    def initialize(self) -> None:
        self._ensure_parent_dir()
        with self._connect(read_only=False) as conn:
            self._ensure_schema(conn)

    def write_snapshot(self, snapshot: LiveSnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        self._ensure_parent_dir()

        with self._connect(read_only=False) as conn:
            self._ensure_schema(conn)
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
            self._ensure_schema(conn)
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
        return duckdb.connect(str(self.db_path), read_only=read_only)

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
