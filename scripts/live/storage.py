from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now
from api.questdb_repository import QuestDBRepository

logger = logging.getLogger(__name__)

class LiveSnapshotStore:
    """QuestDB-backed storage for short-horizon live snapshots using ILP."""

    def __init__(
        self,
        *,
        retention_hours: int = 24,
    ) -> None:
        self.retention_hours = retention_hours
        self.repo = QuestDBRepository()
        self._initialized = False

    async def initialize(self) -> None:
        await self.repo.initialize()
        self._initialized = True

    async def close(self) -> None:
        await self.repo.close()

    async def write_snapshot(self, snapshot: LiveSnapshot) -> None:
        if not self._initialized:
            await self.initialize()

        payload = snapshot.model_dump(mode="json")
        
        # Use ILP for lock-free ingestion (asynchronously to avoid blocking the event loop)
        success = await self.repo.async_send_row(
            "live_snapshots",
            symbols={
                "schema_version": snapshot.schema_version,
            },
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
                "source_timestamps_json": json.dumps(payload["source_timestamps"], sort_keys=True),
                "snapshot_json": json.dumps(payload, sort_keys=True),
            },
            at=snapshot.timestamp
        )
        
        if not success:
            logger.error(f"Failed to write live snapshot to QuestDB at {snapshot.timestamp}")

    async def get_latest(self) -> LiveSnapshot | None:
        if not self._initialized:
            await self.initialize()

        query = "SELECT snapshot_json FROM live_snapshots ORDER BY ts DESC LIMIT 1"
        row = await self.repo.fetchrow(query)
        
        return self._deserialize_snapshot(row["snapshot_json"]) if row else None

    async def get_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        if not self._initialized:
            await self.initialize()

        if query is None:
            query = LiveHistoryQuery()
        elif isinstance(query, int):
            query = LiveHistoryQuery(minutes=query)

        minutes = query.minutes
        sql = f"SELECT snapshot_json FROM live_snapshots WHERE ts > now() - interval '{minutes}m' ORDER BY ts ASC"
        
        rows = await self.repo.fetch(sql)
        return [self._deserialize_snapshot(row["snapshot_json"]) for row in rows]

    async def prune(self, *, now: datetime | None = None) -> int:
        # QuestDB doesn't need manual pruning if PARTITION BY DAY is used and we drop partitions.
        # But we can simulate it with a DELETE if needed.
        # However, ILP is append-only, so DELETE might be slow.
        # In a real QuestDB setup, we would use a retention policy.
        return 0

    @staticmethod
    def _deserialize_snapshot(raw_payload: str) -> LiveSnapshot:
        return LiveSnapshot.model_validate(json.loads(raw_payload))
