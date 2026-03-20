from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

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


class LiveWorker:
    def __init__(
        self,
        *,
        electrs_client,
        mempool_client,
        brk_client,
        hyperliquid_client,
        oracle_resolver: OracleResolver,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.electrs_client = electrs_client
        self.mempool_client = mempool_client
        self.brk_client = brk_client
        self.hyperliquid_client = hyperliquid_client
        self.oracle_resolver = oracle_resolver
        self.clock = clock
        self._last_snapshot: LiveSnapshot | None = None
        self._last_observed_block_height: int | None = None

    @property
    def last_snapshot(self) -> LiveSnapshot | None:
        return self._last_snapshot

    async def collect_once(self) -> LiveSnapshot | None:
        electrs_read = await self.electrs_client.fetch_tip_height()

        mempool_task = asyncio.create_task(self.mempool_client.fetch_exchange_price())
        brk_task = asyncio.create_task(self.brk_client.fetch_curated_features())
        hyperliquid_task = asyncio.create_task(self.hyperliquid_client.fetch_snapshot())

        effective_height = electrs_read.value
        if effective_height is None and self._last_snapshot is not None:
            effective_height = self._last_snapshot.block_height

        utxo_read = await self._resolve_oracle(effective_height)
        mempool_read, brk_read, hyperliquid_read = await asyncio.gather(
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

        snapshot = LiveSnapshot(
            timestamp=self.clock(),
            block_height=effective_height,
            utxoracle_price=utxoracle_price,
            utxoracle_confidence=utxoracle_confidence,
            mempool_exchange_price=mempool_exchange_price,
            hyperliquid_oracle_price=hyperliquid_snapshot.oracle_price if hyperliquid_snapshot else None,
            hyperliquid_mark_price=hyperliquid_snapshot.mark_price if hyperliquid_snapshot else None,
            comparison=build_live_comparison(
                utxoracle_price,
                mempool_exchange_price,
                hyperliquid_snapshot.oracle_price if hyperliquid_snapshot else None,
                hyperliquid_snapshot.mark_price if hyperliquid_snapshot else None,
            ),
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
        if electrs_read.value is not None:
            self._last_observed_block_height = electrs_read.value
        return snapshot

    async def _resolve_oracle(self, block_height: int | None) -> SourceRead[OracleObservation]:
        if block_height is None:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    last_error="block height unavailable; oracle resolver not called",
                ),
            )

        block_changed = block_height != self._last_observed_block_height
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
