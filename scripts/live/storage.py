from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from api.questdb_repository import QuestDBRepository
from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now

logger = logging.getLogger(__name__)


class LiveSnapshotStore:
    """QuestDB-backed live snapshot store."""

    def __init__(
        self,
        repo: QuestDBRepository | None = None,
        *,
        retention_hours: int = 24,
        lock_path: str | None = None,
    ) -> None:
        self.repo = repo or QuestDBRepository()
        self.retention_hours = retention_hours
        self.lock_path = lock_path
        self._initialized = False
        self._recovery_lock = asyncio.Lock()

    def initialize(self, *, for_write: bool = False) -> None:
        del for_write
        self._run_async(self.ainitialize())

    async def ainitialize(self, *, for_write: bool = False) -> None:
        del for_write
        if not self._initialized:
            await self.repo.initialize()
            self._initialized = True

    def close(self) -> None:
        self._run_async(self.aclose())

    async def aclose(self) -> None:
        if self._initialized:
            await self.repo.close()
        self._initialized = False

    def write_snapshot(self, snapshot: LiveSnapshot) -> None:
        self._run_async(self.awrite_snapshot(snapshot))

    async def awrite_snapshot(self, snapshot: LiveSnapshot) -> None:
        if not self._initialized:
            await self.ainitialize()

        payload = snapshot.model_dump(mode="json")
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
                "source_timestamps_json": json.dumps(payload["source_timestamps"], sort_keys=True),
                "snapshot_json": json.dumps(payload, sort_keys=True),
            },
            at=snapshot.timestamp,
        )
        if not success:
            logger.error("Failed to write live snapshot to QuestDB at %s", snapshot.timestamp)
            return

        if self.retention_hours > 0:
            await self.aprune(now=snapshot.timestamp)

    def get_latest(self) -> LiveSnapshot | None:
        return self._run_async(self.aget_latest())

    async def aget_latest(self) -> LiveSnapshot | None:
        if not self._initialized:
            await self.ainitialize()
        row = await self._retry_on_missing_live_snapshots(
            self.repo.fetchrow,
            "SELECT snapshot_json FROM live_snapshots ORDER BY ts DESC LIMIT 1",
        )
        return self._deserialize_snapshot(row["snapshot_json"]) if row else None

    def get_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        return self._run_async(self.aget_history(query, now=now))

    async def aget_history(
        self,
        query: LiveHistoryQuery | int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[LiveSnapshot]:
        if not self._initialized:
            await self.ainitialize()

        if query is None:
            query = LiveHistoryQuery()
        elif isinstance(query, int):
            query = LiveHistoryQuery(minutes=query)

        start_time = ((now or utc_now()) - timedelta(minutes=query.minutes)).replace(tzinfo=None)
        rows = await self._retry_on_missing_live_snapshots(
            self.repo.fetch,
            "SELECT snapshot_json FROM live_snapshots WHERE ts >= $1 ORDER BY ts ASC",
            start_time,
        )
        return [self._deserialize_snapshot(row["snapshot_json"]) for row in rows]

    def prune(self, *, now: datetime | None = None) -> int:
        return self._run_async(self.aprune(now=now))

    async def aprune(self, *, now: datetime | None = None) -> int:
        if self.retention_hours <= 0:
            return 0
        if not self._initialized:
            await self.ainitialize()

        cutoff = ((now or utc_now()) - timedelta(hours=self.retention_hours)).replace(tzinfo=None)
        count_row = await self._retry_on_missing_live_snapshots(
            self.repo.fetchrow,
            "SELECT COUNT(*) AS count FROM live_snapshots WHERE ts < $1",
            cutoff,
        )
        deleted = int(count_row["count"]) if count_row else 0
        if deleted:
            await self._retry_on_missing_live_snapshots(
                self.repo.execute,
                "DELETE FROM live_snapshots WHERE ts < $1",
                cutoff,
            )
        return deleted

    async def _retry_on_missing_live_snapshots(self, operation, *args):
        try:
            return await operation(*args)
        except Exception as exc:
            if not self._requires_live_snapshots_recovery(exc):
                raise

        async with self._recovery_lock:
            try:
                return await operation(*args)
            except Exception as exc:
                if not self._requires_live_snapshots_recovery(exc):
                    raise

                logger.warning(
                    "QuestDB live store needs recovery; reinitializing store and retrying once"
                )
                await self.repo.close()
                self._initialized = False
                await self.ainitialize()
                return await operation(*args)

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

    @staticmethod
    def _is_missing_live_snapshots_error(exc: Exception) -> bool:
        return "table does not exist [table=live_snapshots]" in str(exc)

    @classmethod
    def _requires_live_snapshots_recovery(cls, exc: Exception) -> bool:
        message = str(exc)
        return cls._is_missing_live_snapshots_error(exc) or "pool is closing" in message
