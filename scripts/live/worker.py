from __future__ import annotations

import asyncio
import fcntl
import os
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from scripts.live.comparison import build_live_comparison
from scripts.live.models import (
    HyperliquidPriceSnapshot,
    LiveFeatureSet,
    LiveSnapshot,
    OracleObservation,
    SourceHealth,
    utc_now,
)
from scripts.live.source_clients import SourceRead

OracleResolver = Callable[[int, bool], Awaitable[OracleObservation]]


class ProcessLockError(RuntimeError):
    """Raised when another live worker already holds the writer lock."""


class _WorkerProcessLock:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> None:
        if self._handle is not None:
            raise ProcessLockError(
                f"live worker process lock already held by current process: {self.path}"
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            holder = handle.read().strip()
            handle.close()
            message = f"live worker process lock already held: {self.path}"
            if holder:
                message = f"{message} (holder={holder})"
            raise ProcessLockError(message) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return

        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None



class SnapshotStore(Protocol):
    def write_snapshot(self, snapshot: LiveSnapshot) -> None: ...


class LiveWorker:
    def __init__(
        self,
        *,
        electrs_client,
        mempool_client,
        brk_client,
        hyperliquid_client,
        oracle_resolver: OracleResolver,
        snapshot_store: SnapshotStore | None = None,
        process_lock_path: str | Path | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.electrs_client = electrs_client
        self.mempool_client = mempool_client
        self.brk_client = brk_client
        self.hyperliquid_client = hyperliquid_client
        self.oracle_resolver = oracle_resolver
        self.snapshot_store = snapshot_store
        self.process_lock_path = _resolve_process_lock_path(
            process_lock_path,
            snapshot_store,
        )
        self._process_lock = (
            _WorkerProcessLock(self.process_lock_path)
            if self.process_lock_path is not None
            else None
        )
        self.clock = clock
        self._last_snapshot: LiveSnapshot | None = None
        self._last_observed_block_height: int | None = None

    @property
    def last_snapshot(self) -> LiveSnapshot | None:
        return self._last_snapshot

    async def collect_once(
        self,
        *,
        electrs_read: SourceRead[int] | None = None,
    ) -> LiveSnapshot | None:
        electrs_read = electrs_read or await self.electrs_client.fetch_tip_height()

        effective_height = electrs_read.value
        if effective_height is None and self._last_snapshot is not None:
            effective_height = self._last_snapshot.block_height

        block_changed = (
            effective_height is not None
            and effective_height != self._last_observed_block_height
        )
        if electrs_read.value is not None:
            self._last_observed_block_height = electrs_read.value

        utxo_task = asyncio.create_task(
            self._resolve_oracle(effective_height, block_changed=bool(block_changed))
        )
        mempool_task = asyncio.create_task(self.mempool_client.fetch_exchange_price())
        brk_task = asyncio.create_task(self.brk_client.fetch_curated_features())
        hyperliquid_task = asyncio.create_task(self.hyperliquid_client.fetch_snapshot())

        utxo_read, mempool_read, brk_read, hyperliquid_read = await asyncio.gather(
            utxo_task,
            mempool_task,
            brk_task,
            hyperliquid_task,
        )

        previous = self._last_snapshot
        utxoracle_price = _carry_forward_scalar(
            utxo_read.value.price if utxo_read.value else None,
            previous.utxoracle_price if previous else None,
        )
        utxoracle_confidence = _carry_forward_scalar(
            utxo_read.value.confidence if utxo_read.value else None,
            previous.utxoracle_confidence if previous else None,
        )
        mempool_exchange_price = _carry_forward_scalar(
            mempool_read.value,
            previous.mempool_exchange_price if previous else None,
        )
        hyperliquid_snapshot = _carry_forward_hyperliquid(
            hyperliquid_read.value,
            previous,
        )
        features = _carry_forward_features(brk_read.value, previous)

        if utxoracle_price is None and previous is None:
            return None

        source_health = {
            "electrs": electrs_read.health,
            "utxoracle": _mark_stale_if_carried(
                utxo_read.health,
                is_current=utxo_read.value is not None and utxo_read.value.price is not None,
                had_previous=previous is not None and previous.utxoracle_price is not None,
                stale_message="using previous UTXOracle value",
            ),
            "mempool_api": _mark_stale_if_carried(
                mempool_read.health,
                is_current=mempool_read.value is not None,
                had_previous=previous is not None and previous.mempool_exchange_price is not None,
                stale_message="using previous mempool price",
            ),
            "brk": _mark_stale_if_carried(
                brk_read.health,
                is_current=brk_read.value is not None,
                had_previous=previous is not None,
                stale_message="using previous BRK feature values",
            ),
            "hyperliquid": _mark_stale_if_carried(
                hyperliquid_read.health,
                is_current=hyperliquid_read.value is not None,
                had_previous=previous is not None
                and (
                    previous.hyperliquid_oracle_price is not None
                    or previous.hyperliquid_mark_price is not None
                ),
                stale_message="using previous Hyperliquid snapshot",
            ),
        }

        comparison = build_live_comparison(
            utxoracle_price if source_health["utxoracle"].status == "healthy" else None,
            mempool_exchange_price if source_health["mempool_api"].status == "healthy" else None,
            (
                hyperliquid_snapshot.oracle_price
                if hyperliquid_snapshot and source_health["hyperliquid"].status == "healthy"
                else None
            ),
            (
                hyperliquid_snapshot.mark_price
                if hyperliquid_snapshot and source_health["hyperliquid"].status == "healthy"
                else None
            ),
        )

        snapshot = LiveSnapshot(
            timestamp=self.clock(),
            block_height=effective_height,
            utxoracle_price=utxoracle_price,
            utxoracle_confidence=utxoracle_confidence,
            mempool_exchange_price=mempool_exchange_price,
            hyperliquid_oracle_price=hyperliquid_snapshot.oracle_price if hyperliquid_snapshot else None,
            hyperliquid_mark_price=hyperliquid_snapshot.mark_price if hyperliquid_snapshot else None,
            comparison=comparison,
            features=features,
            source_health=source_health,
            source_timestamps={
                "electrs": electrs_read.source_timestamp,
                "utxoracle": utxo_read.source_timestamp,
                "mempool_api": mempool_read.source_timestamp,
                "brk": brk_read.source_timestamp,
                "hyperliquid": hyperliquid_read.source_timestamp,
            },
        )

        self._last_snapshot = snapshot
        if self.snapshot_store is not None:
            await asyncio.to_thread(self.snapshot_store.write_snapshot, snapshot)
        return snapshot

    async def run(
        self,
        *,
        market_interval_seconds: float,
        block_poll_interval_seconds: float,
        max_cycles: int | None = None,
        stop_event: asyncio.Event | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> list[LiveSnapshot]:
        if market_interval_seconds <= 0:
            raise ValueError("market_interval_seconds must be > 0")
        if block_poll_interval_seconds <= 0:
            raise ValueError("block_poll_interval_seconds must be > 0")

        if self._process_lock is not None:
            self._process_lock.acquire()

        try:
            produced: list[LiveSnapshot] = []
            last_market_run_at: float | None = None
            cycles = 0

            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                if max_cycles is not None and cycles >= max_cycles:
                    break

                electrs_read = await self.electrs_client.fetch_tip_height()
                now = monotonic()
                block_changed = (
                    electrs_read.value is not None
                    and electrs_read.value != self._last_observed_block_height
                )
                market_due = (
                    last_market_run_at is None
                    or (now - last_market_run_at) >= market_interval_seconds
                )

                if block_changed or market_due:
                    snapshot = await self.collect_once(electrs_read=electrs_read)
                    if snapshot is not None:
                        produced.append(snapshot)
                    last_market_run_at = now

                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                if stop_event is not None and stop_event.is_set():
                    break

                await sleep(block_poll_interval_seconds)

            return produced
        finally:
            if self._process_lock is not None:
                self._process_lock.release()

    async def _resolve_oracle(
        self,
        block_height: int | None,
        *,
        block_changed: bool,
    ) -> SourceRead[OracleObservation]:
        if block_height is None:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    last_error="block height unavailable; oracle resolver not called",
                ),
            )

        try:
            observation = await self.oracle_resolver(block_height, block_changed)
        except Exception as exc:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    last_error=str(exc),
                    observed_height=block_height,
                ),
            )

        if observation.price is None:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    last_error="oracle resolver returned no price",
                    observed_height=block_height,
                ),
                source_timestamp=observation.timestamp,
            )

        return SourceRead(
            value=observation,
            health=SourceHealth(
                status="healthy",
                last_success=observation.timestamp,
                observed_height=block_height,
            ),
            source_timestamp=observation.timestamp,
        )


def _resolve_process_lock_path(
    process_lock_path: str | Path | None,
    snapshot_store: SnapshotStore | None,
) -> Path | None:
    if process_lock_path is not None:
        return Path(process_lock_path)

    lock_path = getattr(snapshot_store, "lock_path", None)
    if lock_path is not None:
        return Path(lock_path)

    db_path = getattr(snapshot_store, "db_path", None)
    if db_path is None:
        return None

    db_path = Path(db_path)
    return db_path.parent / f"{db_path.name}.worker.lock"


def _carry_forward_scalar(current: float | None, previous: float | None) -> float | None:
    return current if current is not None else previous


def _carry_forward_features(
    current: LiveFeatureSet | None,
    previous: LiveSnapshot | None,
) -> LiveFeatureSet:
    current = current or LiveFeatureSet()
    if previous is None:
        return current
    return LiveFeatureSet(
        brk_realized_price=_carry_forward_scalar(
            current.brk_realized_price,
            previous.features.brk_realized_price,
        ),
        brk_liveliness=_carry_forward_scalar(
            current.brk_liveliness,
            previous.features.brk_liveliness,
        ),
        brk_reserve_risk=_carry_forward_scalar(
            current.brk_reserve_risk,
            previous.features.brk_reserve_risk,
        ),
    )


def _carry_forward_hyperliquid(
    current: HyperliquidPriceSnapshot | None,
    previous: LiveSnapshot | None,
) -> HyperliquidPriceSnapshot | None:
    if current is not None:
        return current
    if previous is None:
        return None
    if previous.hyperliquid_oracle_price is None and previous.hyperliquid_mark_price is None:
        return None
    timestamp = previous.source_timestamps.get("hyperliquid") or previous.timestamp
    return HyperliquidPriceSnapshot(
        source="filesystem",
        timestamp=timestamp,
        oracle_price=previous.hyperliquid_oracle_price,
        mark_price=previous.hyperliquid_mark_price,
    )


def _mark_stale_if_carried(
    health: SourceHealth,
    *,
    is_current: bool,
    had_previous: bool,
    stale_message: str,
) -> SourceHealth:
    if is_current or not had_previous:
        return health
    return health.model_copy(
        update={
            "status": "stale",
            "details": {**health.details, "stale_reason": stale_message},
        }
    )
