from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from scripts.live.models import LiveComparisonSnapshot, LiveHistoryQuery, LiveSnapshot
from scripts.live.storage import LiveSnapshotStore

router = APIRouter(prefix="/live", tags=["live"])


def get_live_snapshot_store() -> LiveSnapshotStore:
    db_path = os.getenv(
        "LIVE_DUCKDB_PATH",
        "/media/sam/1TB/UTXOracle/data/utxoracle_live.duckdb",
    )
    retention_hours = int(os.getenv("LIVE_RETENTION_HOURS", "24"))
    return LiveSnapshotStore(db_path, retention_hours=retention_hours)


def _require_snapshot(store: LiveSnapshotStore) -> LiveSnapshot:
    snapshot = store.get_latest()
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live snapshot unavailable")
    return snapshot


def build_live_health_summary(store: LiveSnapshotStore) -> dict[str, object]:
    snapshot = store.get_latest()
    if snapshot is None:
        return {
            "status": "unavailable",
            "sources": {},
        }

    source_statuses = {
        name: health.status
        for name, health in snapshot.source_health.items()
    }
    overall_status = (
        "healthy"
        if source_statuses and all(status == "healthy" for status in source_statuses.values())
        else "degraded"
    )
    return {
        "status": overall_status,
        "timestamp": snapshot.timestamp.isoformat(),
        "block_height": snapshot.block_height,
        "sources": source_statuses,
    }


@router.get("/snapshot", response_model=LiveSnapshot)
async def get_live_snapshot(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> LiveSnapshot:
    return _require_snapshot(store)


@router.get("/history", response_model=list[LiveSnapshot])
async def get_live_history(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
) -> list[LiveSnapshot]:
    return store.get_history(LiveHistoryQuery(minutes=minutes))


@router.get("/comparison/latest", response_model=LiveComparisonSnapshot)
async def get_live_comparison_latest(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> LiveComparisonSnapshot:
    snapshot = _require_snapshot(store)
    return LiveComparisonSnapshot(
        timestamp=snapshot.timestamp,
        block_height=snapshot.block_height,
        utxoracle_price=snapshot.utxoracle_price,
        mempool_exchange_price=snapshot.mempool_exchange_price,
        hyperliquid_oracle_price=snapshot.hyperliquid_oracle_price,
        hyperliquid_mark_price=snapshot.hyperliquid_mark_price,
        comparison=snapshot.comparison,
    )


@router.get("/ready")
async def get_live_ready(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> dict[str, object]:
    snapshot = _require_snapshot(store)
    return {
        "status": "ready",
        "timestamp": snapshot.timestamp,
        "block_height": snapshot.block_height,
    }
