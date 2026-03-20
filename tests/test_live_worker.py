from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import pytest

from scripts.live.models import (
    HyperliquidPriceSnapshot,
    LiveFeatureSet,
    OracleObservation,
    SourceHealth,
)
from scripts.live.source_clients import SourceRead
from scripts.live.worker import LiveWorker


class QueueClient:
    def __init__(self, method_name: str, reads: list[SourceRead]):
        self._method_name = method_name
        self._reads = deque(reads)

    def __getattr__(self, item: str):
        if item != self._method_name:
            raise AttributeError(item)

        async def _runner():
            return self._reads.popleft()

        return _runner


class RecordingResolver:
    def __init__(self, observations: list[OracleObservation]):
        self.calls: list[tuple[int, bool]] = []
        self._observations = deque(observations)

    async def __call__(self, block_height: int, block_changed: bool) -> OracleObservation:
        self.calls.append((block_height, block_changed))
        return self._observations.popleft()


@pytest.mark.asyncio
async def test_worker_builds_snapshot_and_tracks_block_changes():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(
                value=941453,
                health=SourceHealth(status="healthy", observed_height=941453),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
            SourceRead(
                value=941453,
                health=SourceHealth(status="healthy", observed_height=941453),
                source_timestamp="2026-03-20T17:14:05Z",
            ),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(value=84302.11, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=84305.0, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:05Z"),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(
                value=LiveFeatureSet(brk_realized_price=54311.39, brk_liveliness=0.63),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:13:19Z",
            ),
            SourceRead(
                value=LiveFeatureSet(brk_realized_price=54312.00, brk_liveliness=0.631),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:13:20Z",
            ),
        ],
    )
    hyperliquid = QueueClient(
        "fetch_snapshot",
        [
            SourceRead(
                value=HyperliquidPriceSnapshot(
                    source="api",
                    timestamp="2026-03-20T17:14:00Z",
                    oracle_price=84295.40,
                    mark_price=84310.80,
                ),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
            SourceRead(
                value=HyperliquidPriceSnapshot(
                    source="api",
                    timestamp="2026-03-20T17:14:05Z",
                    oracle_price=84290.00,
                    mark_price=84312.00,
                ),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:05Z",
            ),
        ],
    )
    resolver = RecordingResolver(
        [
            OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82),
            OracleObservation(timestamp="2026-03-20T17:14:05Z", price=84212.00, confidence=0.83),
        ]
    )
    timestamps = deque(
        [
            datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 20, 17, 14, 5, tzinfo=timezone.utc),
        ]
    )
    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        clock=lambda: timestamps.popleft(),
    )

    first = await worker.collect_once()
    second = await worker.collect_once()

    assert first is not None
    assert second is not None
    assert first.comparison.utxo_vs_mempool_bps == pytest.approx(-10.745875755659792, rel=1e-6)
    assert resolver.calls == [(941453, True), (941453, False)]
    assert second.utxoracle_confidence == pytest.approx(0.83)


@pytest.mark.asyncio
async def test_worker_carries_forward_previous_values_when_sources_fail():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(value=941453, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=941454, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:10Z"),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(value=84302.11, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=None, health=SourceHealth(status="unavailable", last_error="timeout"), source_timestamp=None),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(value=LiveFeatureSet(brk_realized_price=54311.39), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:19Z"),
            SourceRead(value=None, health=SourceHealth(status="unavailable", last_error="brk timeout"), source_timestamp=None),
        ],
    )
    hyperliquid = QueueClient(
        "fetch_snapshot",
        [
            SourceRead(
                value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:00Z", oracle_price=84295.40, mark_price=84310.80),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
            SourceRead(value=None, health=SourceHealth(status="unavailable", last_error="invalid content-type"), source_timestamp=None),
        ],
    )
    resolver = RecordingResolver(
        [
            OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82),
            OracleObservation(timestamp="2026-03-20T17:14:10Z", price=None, confidence=None),
        ]
    )
    timestamps = deque(
        [
            datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 20, 17, 14, 10, tzinfo=timezone.utc),
        ]
    )
    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        clock=lambda: timestamps.popleft(),
    )

    first = await worker.collect_once()
    second = await worker.collect_once()

    assert first is not None
    assert second is not None
    assert second.utxoracle_price == first.utxoracle_price
    assert second.mempool_exchange_price == first.mempool_exchange_price
    assert second.features.brk_realized_price == first.features.brk_realized_price
    assert second.hyperliquid_oracle_price == first.hyperliquid_oracle_price
    assert second.source_health["utxoracle"].status == "stale"
    assert second.source_health["mempool_api"].status == "stale"
    assert second.source_health["brk"].status == "stale"
    assert second.source_health["hyperliquid"].status == "stale"
