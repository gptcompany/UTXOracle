from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from scripts.live.models import LiveSnapshot


class TradableSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    timestamp: datetime
    block_height: int | None
    utxoracle_price: float
    utxoracle_confidence: float
    mempool_exchange_price: float
    utxo_vs_mempool_bps: float
    source_spread_bps: float
    required_source_statuses: dict[str, str]
    required_source_timestamps: dict[str, datetime | None]


def normalize_live_snapshot(snapshot: LiveSnapshot) -> TradableSnapshot:
    if snapshot.utxoracle_price is None:
        raise ValueError("utxoracle_price is required")
    if snapshot.utxoracle_confidence is None:
        raise ValueError("utxoracle_confidence is required")
    if snapshot.mempool_exchange_price is None:
        raise ValueError("mempool_exchange_price is required")
    if snapshot.comparison.utxo_vs_mempool_bps is None:
        raise ValueError("utxo_vs_mempool_bps is required")

    required_sources = ("electrs", "utxoracle", "mempool_api")
    source_statuses: dict[str, str] = {}
    source_timestamps: dict[str, datetime | None] = {}
    for source_name in required_sources:
        health = snapshot.source_health.get(source_name)
        if health is None:
            raise ValueError(f"required source health missing: {source_name}")
        source_statuses[source_name] = health.status
        source_timestamps[source_name] = snapshot.source_timestamps.get(source_name)

    return TradableSnapshot(
        schema_version=snapshot.schema_version,
        timestamp=snapshot.timestamp,
        block_height=snapshot.block_height,
        utxoracle_price=snapshot.utxoracle_price,
        utxoracle_confidence=snapshot.utxoracle_confidence,
        mempool_exchange_price=snapshot.mempool_exchange_price,
        utxo_vs_mempool_bps=snapshot.comparison.utxo_vs_mempool_bps,
        source_spread_bps=abs(snapshot.comparison.utxo_vs_mempool_bps),
        required_source_statuses=source_statuses,
        required_source_timestamps=source_timestamps,
    )

