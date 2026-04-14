from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import inspect
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.config import LIVE_API_CORS_ALLOWED_ORIGINS, get_cors_middleware_kwargs
from api.routes.charts import router as charts_router
from api.routes.live import (
    build_live_health_summary_async,
    get_live_snapshot_store,
    router as live_router,
)
from api.routes.questdb import router as questdb_router
from api.routes.features import router as features_router
from api.routes.signals import router as signals_router
from api.mempool_whale_endpoints import router as whale_router
from api.routes.meta import router as meta_router
from api.questdb_repository import QuestDBRepository
from scripts.live.storage import LiveSnapshotStore

APP_VERSION = os.getenv("UTXORACLE_VERSION", "unknown")
APP_COMMIT_SHA = os.getenv("UTXORACLE_COMMIT_SHA", "unknown")
APP_BUILD_AT = os.getenv("UTXORACLE_BUILD_AT", "unknown")
STARTUP_TIME = datetime.now(timezone.utc)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
WHALE_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "exchange_addresses.csv"
LIVE_PRICE_COMPARISON_PAGE = FRONTEND_DIR / "live_price_comparison.html"
SUPPORTED_CHART_PAGES = {
    "live-price-comparison",
    "realized-price-reference",
}


def _log_background_task_failure(task: asyncio.Task) -> None:
    with suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logging.error("Background task %s failed: %s", task.get_name(), exc)


def _get_registry_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


async def _reload_registry_if_changed(
    monitor: Any,
    registry_path: Path,
    last_mtime: float | None,
) -> float | None:
    current_mtime = _get_registry_mtime(registry_path)
    if current_mtime is None or current_mtime == last_mtime:
        return last_mtime

    await monitor.reload_exchange_registry()
    logging.info("Reloaded whale registry from %s", registry_path)
    return current_mtime


async def _watch_exchange_registry(
    monitor: Any,
    registry_path: Path,
    *,
    poll_interval_seconds: float,
) -> None:
    last_mtime = _get_registry_mtime(registry_path)
    interval = max(poll_interval_seconds, 1.0)

    while True:
        await asyncio.sleep(interval)
        try:
            last_mtime = await _reload_registry_if_changed(
                monitor,
                registry_path,
                last_mtime,
            )
        except Exception as exc:
            logging.error("Failed to reload whale registry from %s: %s", registry_path, exc)


class LiveServiceCheck(BaseModel):
    status: str = Field(description="ok or error")
    error: str | None = Field(default=None, description="Error details when degraded")
    last_success: str | None = Field(
        default=None, description="ISO timestamp of last success"
    )


class LiveHealthStatus(BaseModel):
    status: str = Field(description="healthy, degraded, or unavailable")
    timestamp: datetime = Field(description="Current timestamp")
    uptime_seconds: float
    started_at: str
    version: str
    commit_sha: str
    build_at: str
    checks: dict[str, LiveServiceCheck]
    live: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("UTXOracle live production API starting...")

    # Keep live snapshot surfaces available even if QuestDB startup is unavailable.
    app.state.questdb_repo = None
    try:
        questdb_repo = QuestDBRepository()
        await questdb_repo.initialize()
        app.state.questdb_repo = questdb_repo
        logging.info("QuestDB repository initialized for live production app.")
    except Exception as exc:
        logging.warning(
            "QuestDB repository unavailable during live app startup; derived routes will stay degraded: %s",
            exc,
        )

    # Initialize Unified Mempool Whale Monitor
    from scripts.mempool_whale_monitor import MempoolWhaleMonitor
    from api.routes.execution import stream_manager
    try:
        monitor = MempoolWhaleMonitor()
        if app.state.questdb_repo is not None:
            monitor.repo = app.state.questdb_repo

        # Set our new FastAPI-native stream manager as the broadcaster
        class BroadcasterAdapter:
            async def broadcast_whale_alert(self, payload: dict[str, Any]):
                await stream_manager.broadcast(
                    {
                        "type": "whale_alert",
                        "data": payload,
                    }
                )

            async def broadcast_alert(self, signal):
                await self.broadcast_whale_alert(signal.to_broadcast_dict())

        monitor.broadcaster = BroadcasterAdapter()
        app.state.whale_monitor = monitor
        app.state.whale_monitor_task = asyncio.create_task(
            monitor.start(),
            name="live-whale-monitor",
        )
        app.state.whale_monitor_task.add_done_callback(_log_background_task_failure)
        registry_reload_seconds = float(
            os.getenv("WHALE_REGISTRY_RELOAD_SECONDS", "60")
        )
        app.state.whale_registry_task = asyncio.create_task(
            _watch_exchange_registry(
                monitor,
                WHALE_REGISTRY_PATH,
                poll_interval_seconds=registry_reload_seconds,
            ),
            name="live-whale-registry-watch",
        )
        app.state.whale_registry_task.add_done_callback(_log_background_task_failure)
        logging.info("Unified Mempool Whale Monitor started within FastAPI.")
    except Exception as exc:
        logging.error("Failed to start Mempool Whale Monitor: %s", exc)

    yield
    logging.info("UTXOracle live production API shutting down...")
    
    if hasattr(app.state, "whale_monitor"):
        try:
            if hasattr(app.state, "whale_registry_task"):
                app.state.whale_registry_task.cancel()
                with suppress(asyncio.CancelledError):
                    await app.state.whale_registry_task
            await app.state.whale_monitor.stop()
            if hasattr(app.state, "whale_monitor_task"):
                app.state.whale_monitor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await app.state.whale_monitor_task
        except Exception as exc:
            logging.error("Failed to stop Mempool Whale Monitor: %s", exc)

    try:
        store = _resolve_snapshot_store(app)
        close = getattr(store, "aclose", None)
        if close is not None:
            await close()
        else:
            maybe_close = getattr(store, "close", None)
            if maybe_close is not None:
                result = maybe_close()
                if inspect.isawaitable(result):
                    await result
        cache_clear = getattr(get_live_snapshot_store, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()
    except Exception as exc:
        logging.warning("Failed to close live snapshot store cleanly: %s", exc)

    try:
        questdb_repo = getattr(app.state, "questdb_repo", None)
        if questdb_repo is not None:
            await questdb_repo.close()
    except Exception as exc:
        logging.warning("Failed to close QuestDB repository cleanly: %s", exc)


def _resolve_snapshot_store(app: FastAPI) -> LiveSnapshotStore:
    override = app.dependency_overrides.get(get_live_snapshot_store)
    if override is not None:
        return override()
    return get_live_snapshot_store()


def create_app() -> FastAPI:
    app = FastAPI(
        title="UTXOracle Live API",
        description="Production-scoped live API for UTXOracle snapshots",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_methods=["*"],
        allow_headers=["*"],
        **get_cors_middleware_kwargs(LIVE_API_CORS_ALLOWED_ORIGINS),
    )

    app.include_router(live_router, prefix="/api/v1")

    # tier_2_operator — NOT execution-eligible, see docs/contracts/surface_boundary.yaml
    app.include_router(charts_router, prefix="/api/v1")

    # tier_2_operator — NOT execution-eligible, see docs/contracts/surface_boundary.yaml
    app.include_router(questdb_router)

    from api.routes.execution import router as execution_router

    app.include_router(execution_router)
    app.include_router(features_router)
    app.include_router(signals_router)
    from api.routes.entities import router as entities_router

    # tier_2_operator — NOT execution-eligible, see docs/contracts/surface_boundary.yaml
    app.include_router(entities_router)

    # tier_2_operator — NOT execution-eligible, see docs/contracts/surface_boundary.yaml
    app.include_router(whale_router)

    # tier_2_operator — NOT execution-eligible, see docs/contracts/surface_boundary.yaml
    app.include_router(meta_router)

    @app.get("/charts/{chart_id}", include_in_schema=False)
    async def chart_page(chart_id: str) -> FileResponse:
        if chart_id not in SUPPORTED_CHART_PAGES:
            raise HTTPException(status_code=404, detail="chart_id not supported")
        return FileResponse(LIVE_PRICE_COMPARISON_PAGE)

    @app.get("/health", response_model=LiveHealthStatus)
    async def health_check(
        store: LiveSnapshotStore = Depends(get_live_snapshot_store),
    ) -> LiveHealthStatus:
        now = datetime.now(timezone.utc)
        uptime = (now - STARTUP_TIME).total_seconds()

        try:
            live_summary = await build_live_health_summary_async(store)
            live_status = str(live_summary.get("status", "unavailable"))
            if live_status == "healthy":
                status = "healthy"
                check = LiveServiceCheck(
                    status="ok",
                    last_success=live_summary.get("timestamp"),
                )
            else:
                status = "degraded"
                check = LiveServiceCheck(
                    status="error",
                    error=f"live status: {live_status}",
                    last_success=live_summary.get("timestamp"),
                )
        except Exception as exc:
            logging.warning("Live production health check failed: %s", exc)
            status = "unavailable"
            live_summary = {"status": "unavailable", "sources": {}}
            check = LiveServiceCheck(status="error", error="live health check failed")

        return LiveHealthStatus(
            status=status,
            timestamp=now,
            uptime_seconds=uptime,
            started_at=STARTUP_TIME.isoformat(),
            version=APP_VERSION,
            commit_sha=APP_COMMIT_SHA,
            build_at=APP_BUILD_AT,
            checks={"utxoracle_live": check},
            live=live_summary,
        )

    return app


app = create_app()
