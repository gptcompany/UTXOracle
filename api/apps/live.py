from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.routes.live import (
    build_live_health_summary,
    get_live_snapshot_store,
    router as live_router,
)
from scripts.live.storage import LiveSnapshotStore

APP_VERSION = os.getenv("UTXORACLE_VERSION", "unknown")
APP_COMMIT_SHA = os.getenv("UTXORACLE_COMMIT_SHA", "unknown")
APP_BUILD_AT = os.getenv("UTXORACLE_BUILD_AT", "unknown")
STARTUP_TIME = datetime.now(timezone.utc)


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
    yield
    logging.info("UTXOracle live production API shutting down...")
    try:
        store = _resolve_snapshot_store(app)
        await store.close()
        get_live_snapshot_store.cache_clear()
    except Exception as exc:
        logging.warning("Failed to close live snapshot store cleanly: %s", exc)


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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(live_router, prefix="/api/v1")

    @app.get("/health", response_model=LiveHealthStatus)
    async def health_check(
        store: LiveSnapshotStore = Depends(get_live_snapshot_store),
    ) -> LiveHealthStatus:
        now = datetime.now(timezone.utc)
        uptime = (now - STARTUP_TIME).total_seconds()

        try:
            live_summary = await build_live_health_summary(store)
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
            check = LiveServiceCheck(status="error", error=str(exc))

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
