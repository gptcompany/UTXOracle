from datetime import datetime, timezone

from scripts.live.models import (
    LiveComparison,
    LiveComparisonSnapshot,
    LiveFeatureSet,
    LiveSnapshot,
    SourceHealth,
)


def test_source_health_normalizes_naive_datetime_to_utc():
    health = SourceHealth(status="healthy", last_success=datetime(2026, 3, 20, 17, 0, 0))

    assert health.last_success is not None
    assert health.last_success.tzinfo == timezone.utc


def test_live_snapshot_preserves_nested_models_and_source_timestamps():
    snapshot = LiveSnapshot(
        timestamp="2026-03-20T17:14:00Z",
        block_height=941453,
        utxoracle_price=84_211.52,
        utxoracle_confidence=0.82,
        mempool_exchange_price=84_302.11,
        hyperliquid_oracle_price=84_295.40,
        hyperliquid_mark_price=84_310.80,
        comparison=LiveComparison(utxo_vs_mempool_bps=-10.75),
        features=LiveFeatureSet(brk_realized_price=54_311.39, brk_liveliness=0.63),
        source_health={
            "electrs": SourceHealth(status="healthy", observed_height=941453),
        },
        source_timestamps={"electrs": "2026-03-20T17:14:00Z"},
    )

    assert snapshot.source_health["electrs"].observed_height == 941453
    assert snapshot.source_timestamps["electrs"] is not None
    assert snapshot.source_timestamps["electrs"].tzinfo == timezone.utc
    assert snapshot.model_dump()["comparison"]["utxo_vs_mempool_bps"] == -10.75


def test_source_health_accepts_nanosecond_iso_strings():
    health = SourceHealth(
        status="healthy",
        last_success="2026-03-20T12:59:59.633355851",
    )

    assert health.last_success is not None
    assert health.last_success.tzinfo == timezone.utc
    assert health.last_success.microsecond == 633355


def test_live_comparison_snapshot_normalizes_timestamp():
    snapshot = LiveComparisonSnapshot(
        timestamp="2026-03-20T17:14:00.123456789Z",
        block_height=941453,
        utxoracle_price=84211.52,
    )

    assert snapshot.timestamp == datetime(2026, 3, 20, 17, 14, 0, 123456, tzinfo=timezone.utc)
