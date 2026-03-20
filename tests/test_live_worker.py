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
from scripts.live.storage import LiveSnapshotStore
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


class RecordingSnapshotStore:
    def __init__(self):
        self.snapshots = []

    def write_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


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


@pytest.mark.asyncio
async def test_worker_persists_snapshot_when_store_is_configured():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(
                value=941453,
                health=SourceHealth(status="healthy", observed_height=941453),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(
                value=84302.11,
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
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
        ],
    )
    resolver = RecordingResolver(
        [OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82)]
    )
    store = RecordingSnapshotStore()

    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        snapshot_store=store,
        clock=lambda: datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
    )

    snapshot = await worker.collect_once()

    assert snapshot is not None
    assert len(store.snapshots) == 1
    assert store.snapshots[0].utxoracle_price == pytest.approx(84211.52)


@pytest.mark.asyncio
async def test_worker_run_collects_on_market_interval_without_block_change():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:02Z"),
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:04Z"),
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:06Z"),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(value=84302.11, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=84303.00, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:06Z"),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(value=LiveFeatureSet(brk_realized_price=54311.39, brk_liveliness=0.63), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:19Z"),
            SourceRead(value=LiveFeatureSet(brk_realized_price=54312.00, brk_liveliness=0.631), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:25Z"),
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
            SourceRead(
                value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:06Z", oracle_price=84296.00, mark_price=84311.00),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:06Z",
            ),
        ],
    )
    resolver = RecordingResolver(
        [
            OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82),
            OracleObservation(timestamp="2026-03-20T17:14:06Z", price=84212.00, confidence=0.83),
        ]
    )
    timestamps = deque(
        [
            datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 20, 17, 14, 6, tzinfo=timezone.utc),
        ]
    )
    monotonic_ticks = deque([0.0, 2.0, 4.0, 6.0])
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        clock=lambda: timestamps.popleft(),
    )

    snapshots = await worker.run(
        market_interval_seconds=5.0,
        block_poll_interval_seconds=2.0,
        max_cycles=4,
        monotonic=lambda: monotonic_ticks.popleft(),
        sleep=fake_sleep,
    )

    assert len(snapshots) == 2
    assert resolver.calls == [(941453, True), (941453, False)]
    assert sleep_calls == [2.0, 2.0, 2.0]


@pytest.mark.asyncio
async def test_worker_run_collects_immediately_on_block_change_before_market_interval():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=941454, health=SourceHealth(status="healthy", observed_height=941454), source_timestamp="2026-03-20T17:14:01Z"),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(value=84302.11, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=84305.00, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:01Z"),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(value=LiveFeatureSet(brk_realized_price=54311.39), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:19Z"),
            SourceRead(value=LiveFeatureSet(brk_realized_price=54312.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:20Z"),
        ],
    )
    hyperliquid = QueueClient(
        "fetch_snapshot",
        [
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:00Z", oracle_price=84295.40, mark_price=84310.80), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:01Z", oracle_price=84296.00, mark_price=84311.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:01Z"),
        ],
    )
    resolver = RecordingResolver(
        [
            OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82),
            OracleObservation(timestamp="2026-03-20T17:14:01Z", price=84215.00, confidence=0.84),
        ]
    )
    timestamps = deque(
        [
            datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 20, 17, 14, 1, tzinfo=timezone.utc),
        ]
    )
    monotonic_ticks = deque([0.0, 1.0])

    async def fake_sleep(_seconds: float):
        return None

    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        clock=lambda: timestamps.popleft(),
    )

    snapshots = await worker.run(
        market_interval_seconds=60.0,
        block_poll_interval_seconds=2.0,
        max_cycles=2,
        monotonic=lambda: monotonic_ticks.popleft(),
        sleep=fake_sleep,
    )

    assert len(snapshots) == 2
    assert [snapshot.block_height for snapshot in snapshots] == [941453, 941454]
    assert resolver.calls == [(941453, True), (941454, True)]


@pytest.mark.asyncio
async def test_worker_persists_comparison_and_curated_features_to_store(tmp_path):
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(
                value=941453,
                health=SourceHealth(status="healthy", observed_height=941453),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(
                value=84302.11,
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:14:00Z",
            ),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(
                value=LiveFeatureSet(
                    brk_realized_price=54311.39,
                    brk_liveliness=0.63,
                    brk_reserve_risk=4.100239e-06,
                ),
                health=SourceHealth(status="healthy"),
                source_timestamp="2026-03-20T17:13:19Z",
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
        ],
    )
    resolver = RecordingResolver(
        [OracleObservation(timestamp="2026-03-20T17:14:00Z", price=84211.52, confidence=0.82)]
    )
    store = LiveSnapshotStore(tmp_path / "live.duckdb")
    store.initialize()

    worker = LiveWorker(
        electrs_client=electrs,
        mempool_client=mempool,
        brk_client=brk,
        hyperliquid_client=hyperliquid,
        oracle_resolver=resolver,
        snapshot_store=store,
        clock=lambda: datetime(2026, 3, 20, 17, 14, 0, tzinfo=timezone.utc),
    )

    snapshot = await worker.collect_once()
    persisted = store.get_latest()

    assert snapshot is not None
    assert persisted is not None
    assert persisted.comparison.utxo_vs_mempool_bps == snapshot.comparison.utxo_vs_mempool_bps
    assert persisted.features.brk_realized_price == pytest.approx(54311.39)
    assert persisted.features.brk_liveliness == pytest.approx(0.63)
    assert persisted.features.brk_reserve_risk == pytest.approx(4.100239e-06)


@pytest.mark.asyncio
async def test_worker_marks_comparisons_unavailable_when_canonical_oracle_is_stale():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=941454, health=SourceHealth(status="healthy", observed_height=941454), source_timestamp="2026-03-20T17:14:10Z"),
        ],
    )
    mempool = QueueClient(
        "fetch_exchange_price",
        [
            SourceRead(value=84302.11, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=84305.0, health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:10Z"),
        ],
    )
    brk = QueueClient(
        "fetch_curated_features",
        [
            SourceRead(value=LiveFeatureSet(brk_realized_price=54311.39), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:19Z"),
            SourceRead(value=LiveFeatureSet(brk_realized_price=54312.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:20Z"),
        ],
    )
    hyperliquid = QueueClient(
        "fetch_snapshot",
        [
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:00Z", oracle_price=84295.40, mark_price=84310.80), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:10Z", oracle_price=84296.00, mark_price=84311.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:10Z"),
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
    assert second.source_health["utxoracle"].status == "stale"
    assert second.comparison.utxo_vs_mempool_bps is None
    assert second.comparison.utxo_vs_hl_oracle_bps is None
    assert second.comparison.utxo_vs_hl_mark_bps is None


@pytest.mark.asyncio
async def test_worker_remembers_observed_block_after_failed_initial_collection():
    electrs = QueueClient(
        "fetch_tip_height",
        [
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=941453, health=SourceHealth(status="healthy", observed_height=941453), source_timestamp="2026-03-20T17:14:05Z"),
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
            SourceRead(value=LiveFeatureSet(brk_realized_price=54311.39), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:19Z"),
            SourceRead(value=LiveFeatureSet(brk_realized_price=54312.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:13:20Z"),
        ],
    )
    hyperliquid = QueueClient(
        "fetch_snapshot",
        [
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:00Z", oracle_price=84295.40, mark_price=84310.80), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:00Z"),
            SourceRead(value=HyperliquidPriceSnapshot(source="api", timestamp="2026-03-20T17:14:05Z", oracle_price=84296.00, mark_price=84311.00), health=SourceHealth(status="healthy"), source_timestamp="2026-03-20T17:14:05Z"),
        ],
    )
    resolver = RecordingResolver(
        [
            OracleObservation(timestamp="2026-03-20T17:14:00Z", price=None, confidence=None),
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

    assert first is None
    assert second is not None
    assert resolver.calls == [(941453, True), (941453, False)]
