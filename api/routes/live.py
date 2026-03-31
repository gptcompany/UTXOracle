from __future__ import annotations

import os
from functools import lru_cache
import asyncio
import inspect
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from scripts.live.models import LiveComparisonSnapshot, LiveHistoryQuery, LiveSnapshot, utc_now
from scripts.live.storage import LiveSnapshotStore

router = APIRouter(prefix="/live", tags=["live"])


@lru_cache(maxsize=1)
def get_live_snapshot_store() -> LiveSnapshotStore:
    retention_hours = int(os.getenv("LIVE_RETENTION_HOURS", "24"))
    live_db_path = os.getenv("LIVE_DB_PATH")
    return LiveSnapshotStore(
        live_db_path,
        retention_hours=retention_hours,
    )


async def _call_store(store: LiveSnapshotStore, method_name: str, *args, **kwargs):
    async_method = getattr(store, f"a{method_name}", None)
    if async_method is not None:
        return await async_method(*args, **kwargs)

    method = getattr(store, method_name)
    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


def _require_snapshot(store: LiveSnapshotStore) -> LiveSnapshot:
    snapshot = store.get_latest()
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live snapshot unavailable")
    return snapshot


def _build_live_health_summary_from_snapshot(snapshot: LiveSnapshot | None) -> dict[str, object]:
    if snapshot is None:
        return {
            "status": "unavailable",
            "sources": {},
        }

    now = utc_now()
    age_seconds = (now - snapshot.timestamp).total_seconds()

    source_statuses = {
        name: health.status
        for name, health in snapshot.source_health.items()
    }
    
    if age_seconds > 60:
        overall_status = "stale"
    else:
        overall_status = (
            "healthy"
            if source_statuses and all(status == "healthy" for status in source_statuses.values())
            else "degraded"
        )
        
    return {
        "status": overall_status,
        "timestamp": snapshot.timestamp.isoformat(),
        "age_seconds": round(age_seconds, 1),
        "block_height": snapshot.block_height,
        "sources": source_statuses,
    }


def build_live_health_summary(store: LiveSnapshotStore) -> dict[str, object]:
    return _build_live_health_summary_from_snapshot(store.get_latest())


async def build_live_health_summary_async(store: LiveSnapshotStore) -> dict[str, object]:
    snapshot = await _call_store(store, "get_latest")
    return _build_live_health_summary_from_snapshot(snapshot)


@router.get("/snapshot", response_model=LiveSnapshot)
async def get_live_snapshot(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> LiveSnapshot:
    snapshot = await _call_store(store, "get_latest")
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live snapshot unavailable")
    return snapshot


@router.get("/history", response_model=list[LiveSnapshot])
async def get_live_history(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
) -> list[LiveSnapshot]:
    return await _call_store(store, "get_history", LiveHistoryQuery(minutes=minutes))


@router.get("/comparison/latest", response_model=LiveComparisonSnapshot)
async def get_live_comparison_latest(
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> LiveComparisonSnapshot:
    snapshot = await _call_store(store, "get_latest")
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live snapshot unavailable")
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
    snapshot = await _call_store(store, "get_latest")
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live snapshot unavailable")
    now = utc_now()
    age_seconds = (now - snapshot.timestamp).total_seconds()
    
    if age_seconds > 60:
        raise HTTPException(
            status_code=503, 
            detail=f"live data is stale ({age_seconds:.1f}s old)"
        )
        
    return {
        "status": "ready",
        "timestamp": snapshot.timestamp,
        "block_height": snapshot.block_height,
        "age_seconds": round(age_seconds, 1),
    }
