#!/usr/bin/env python3
"""
UTXOracle FastAPI Backend

REST API serving price comparison data from DuckDB.

Spec: 003-mempool-integration-refactor
Phase: 4 - API & Visualization
Tasks: T058-T065
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import duckdb
from dotenv import load_dotenv

# =============================================================================
# T064: Configuration Management
# =============================================================================

# Load .env file (override=True to prioritize .env over existing env vars)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    logging.info(f"Config loaded from .env file at {env_path} (override=True)")
else:
    logging.info("Config loaded from environment variables (no .env file found)")

# Configuration with defaults
DUCKDB_PATH = os.getenv(
    "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# T064a: Config validation
def validate_config():
    """Validate required configuration exists"""
    duckdb_dir = Path(DUCKDB_PATH).parent
    if not duckdb_dir.exists():
        raise EnvironmentError(
            f"DUCKDB_PATH directory does not exist: {duckdb_dir}\n"
            f"Set DUCKDB_PATH env var or check configuration."
        )

    logging.info(
        f"Config validated: duckdb_path={DUCKDB_PATH}, "
        f"host={FASTAPI_HOST}, port={FASTAPI_PORT}"
    )


# Validate on startup
validate_config()

# Track startup time for /health endpoint
STARTUP_TIME = datetime.now()

# =============================================================================
# T058: FastAPI App Initialization
# =============================================================================

app = FastAPI(
    title="UTXOracle API",
    description="REST API for BTC/USD price comparison data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# =============================================================================
# T059: CORS Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# T078: Serve Frontend Static Files
# =============================================================================

# Mount frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logging.info(f"Frontend mounted at /static from {FRONTEND_DIR}")

# =============================================================================
# Pydantic Models
# =============================================================================


class PriceEntry(BaseModel):
    """Single price comparison entry"""

    timestamp: str
    utxoracle_price: Optional[float] = None
    mempool_price: Optional[float] = None
    confidence: float
    tx_count: int
    diff_amount: Optional[float] = None
    diff_percent: Optional[float] = None
    is_valid: bool


class ComparisonStats(BaseModel):
    """Statistical comparison metrics"""

    avg_diff: Optional[float] = None
    max_diff: Optional[float] = None
    min_diff: Optional[float] = None
    avg_diff_percent: Optional[float] = None
    total_entries: int
    valid_entries: int
    timeframe_days: int = 7


class HealthStatus(BaseModel):
    """API health check response"""

    status: str = Field(description="healthy, degraded, or unhealthy")
    database: str
    uptime_seconds: float
    started_at: str


# =============================================================================
# Database Helper Functions
# =============================================================================


def get_db_connection():
    """Get DuckDB connection"""
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to DuckDB: {e}")
        raise HTTPException(
            status_code=503, detail=f"Database connection failed: {str(e)}"
        )


def row_to_dict(row, columns) -> Dict:
    """Convert DuckDB row tuple to dictionary"""
    return dict(zip(columns, row))


# =============================================================================
# T060: GET /api/prices/latest
# =============================================================================


@app.get("/api/prices/latest", response_model=PriceEntry)
async def get_latest_price():
    """
    Get the most recent price comparison entry.

    Returns:
        PriceEntry: Latest price data from database
    """
    conn = get_db_connection()

    try:
        result = conn.execute("""
            SELECT timestamp, utxoracle_price, mempool_price, confidence,
                   tx_count, diff_amount, diff_percent, is_valid
            FROM prices
            ORDER BY timestamp DESC
            LIMIT 1
        """).fetchone()

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No price data available yet. Wait for cron to populate data.",
            )

        columns = [
            "timestamp",
            "utxoracle_price",
            "mempool_price",
            "confidence",
            "tx_count",
            "diff_amount",
            "diff_percent",
            "is_valid",
        ]
        data = row_to_dict(result, columns)

        # Convert timestamp to ISO format string
        if isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        return PriceEntry(**data)

    finally:
        conn.close()


# =============================================================================
# T061: GET /api/prices/historical
# =============================================================================


@app.get("/api/prices/historical", response_model=List[PriceEntry])
async def get_historical_prices(
    days: int = Query(
        default=7,
        ge=1,
        le=365,
        description="Number of days of historical data to retrieve",
    ),
):
    """
    Get historical price comparison data.

    Args:
        days: Number of days to retrieve (1-365, default: 7)

    Returns:
        List[PriceEntry]: Historical price data
    """
    conn = get_db_connection()

    try:
        # Calculate cutoff timestamp
        cutoff = datetime.now() - timedelta(days=days)

        result = conn.execute(
            """
            SELECT timestamp, utxoracle_price, mempool_price, confidence,
                   tx_count, diff_amount, diff_percent, is_valid
            FROM prices
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """,
            [cutoff],
        ).fetchall()

        columns = [
            "timestamp",
            "utxoracle_price",
            "mempool_price",
            "confidence",
            "tx_count",
            "diff_amount",
            "diff_percent",
            "is_valid",
        ]

        data = []
        for row in result:
            entry = row_to_dict(row, columns)
            # Convert timestamp to ISO format string
            if isinstance(entry["timestamp"], datetime):
                entry["timestamp"] = entry["timestamp"].isoformat()
            data.append(entry)

        return [PriceEntry(**entry) for entry in data]

    finally:
        conn.close()


# =============================================================================
# T062: GET /api/prices/comparison
# =============================================================================


@app.get("/api/prices/comparison", response_model=ComparisonStats)
async def get_comparison_stats(
    days: int = Query(
        default=7, ge=1, le=365, description="Number of days for statistics calculation"
    ),
):
    """
    Get statistical comparison metrics between UTXOracle and exchange prices.

    Args:
        days: Number of days to calculate stats for (1-365, default: 7)

    Returns:
        ComparisonStats: Statistical metrics
    """
    conn = get_db_connection()

    try:
        # Calculate cutoff timestamp
        cutoff = datetime.now() - timedelta(days=days)

        result = conn.execute(
            """
            SELECT
                AVG(diff_amount) as avg_diff,
                MAX(diff_amount) as max_diff,
                MIN(diff_amount) as min_diff,
                AVG(diff_percent) as avg_diff_percent,
                COUNT(*) as total_entries,
                SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_entries
            FROM prices
            WHERE timestamp >= ?
        """,
            [cutoff],
        ).fetchone()

        if result is None or result[4] == 0:  # total_entries = 0
            return ComparisonStats(
                avg_diff=None,
                max_diff=None,
                min_diff=None,
                avg_diff_percent=None,
                total_entries=0,
                valid_entries=0,
                timeframe_days=days,
            )

        return ComparisonStats(
            avg_diff=float(result[0]) if result[0] is not None else None,
            max_diff=float(result[1]) if result[1] is not None else None,
            min_diff=float(result[2]) if result[2] is not None else None,
            avg_diff_percent=float(result[3]) if result[3] is not None else None,
            total_entries=int(result[4]),
            valid_entries=int(result[5]),
            timeframe_days=days,
        )

    finally:
        conn.close()


# =============================================================================
# T063: GET /health
# =============================================================================


@app.get("/health", response_model=HealthStatus)
async def health_check():
    """
    API health check endpoint.

    Returns:
        HealthStatus: Health status with database and uptime info
    """
    # Calculate uptime
    uptime = (datetime.now() - STARTUP_TIME).total_seconds()

    # Check database connectivity
    db_status = "disconnected"
    try:
        conn = get_db_connection()
        # Try a simple query
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_status = "connected"
    except Exception as e:
        logging.error(f"Health check database error: {e}")
        db_status = f"error: {str(e)}"

    # Determine overall status
    if db_status == "connected":
        status = "healthy"
    elif "error" in db_status:
        status = "unhealthy"
    else:
        status = "degraded"

    return HealthStatus(
        status=status,
        database=db_status,
        uptime_seconds=uptime,
        started_at=STARTUP_TIME.isoformat(),
    )


# =============================================================================
# Root Endpoint
# =============================================================================


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "UTXOracle API",
        "version": "1.0.0",
        "spec": "003-mempool-integration-refactor",
        "endpoints": {
            "latest": "/api/prices/latest",
            "historical": "/api/prices/historical?days=7",
            "comparison": "/api/prices/comparison?days=7",
            "health": "/health",
            "docs": "/docs",
        },
    }


# =============================================================================
# T065: Startup Event
# =============================================================================


@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logging.info("=" * 60)
    logging.info("UTXOracle API starting...")
    logging.info(f"DuckDB path: {DUCKDB_PATH}")
    logging.info(f"Listening on: {FASTAPI_HOST}:{FASTAPI_PORT}")
    logging.info(f"Docs available at: http://{FASTAPI_HOST}:{FASTAPI_PORT}/docs")
    logging.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown information"""
    logging.info("UTXOracle API shutting down...")


# =============================================================================
# Run with uvicorn (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        reload=True,
        log_level=LOG_LEVEL.lower(),
    )
