from __future__ import annotations

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
LIVE_PRICE_COMPARISON_PAGE = FRONTEND_DIR / "live_price_comparison.html"
SUPPORTED_CHART_PAGES = {
    "live-price-comparison",
    "realized-price-reference",
}


class LiveServiceCheck(BaseModel):
    status: str = Field(description="ok or error")
    error: str | None = Field(default=None, description="Error details when degraded")
    last_success: str | None = Field(default=None, description="ISO timestamp of last success")


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

    yield
    logging.info("UTXOracle live production API shutting down...")
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
