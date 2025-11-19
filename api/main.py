#!/usr/bin/env python3
"""
UTXOracle FastAPI Backend

REST API serving price comparison data from DuckDB.

Spec: 003-mempool-integration-refactor
Phase: 4 - API & Visualization
Tasks: T058-T065

Spec: 005-mempool-whale-realtime
Phase: 5 - Dashboard
Tasks: T036 - Whale detection REST API endpoints

Security: T036a/b - JWT Authentication Required
"""

import os
import logging
import time
import asyncio
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import aiohttp

# =============================================================================
# P2: Structured Logging Configuration
# =============================================================================

import sys

sys.path.insert(0, str(Path(__file__).parent))

try:
    from logging_config import (
        configure_structured_logging,
        CorrelationIDMiddleware,
        get_logger,
    )

    configure_structured_logging()
    LOGGING_CONFIGURED = True
    logging.info("✅ Structured logging (structlog) configured successfully")
except ImportError as e:
    LOGGING_CONFIGURED = False
    logging.warning(f"⚠️ Structured logging not available: {e}")
    logging.warning("   Using standard Python logging")

# =============================================================================
# T036a: Security - JWT Authentication Middleware
# =============================================================================

try:
    from auth_middleware import require_auth, optional_auth, AuthToken

    AUTH_AVAILABLE = True
    logging.info("✅ JWT authentication middleware loaded successfully")
except ImportError as e:
    AUTH_AVAILABLE = False
    logging.warning(f"⚠️ Auth middleware not available: {e}")
    logging.warning("   All endpoints will be unprotected (development mode)")

    # Fallback no-op dependency for development
    class AuthToken:
        def __init__(self):
            self.client_id = "dev-client"
            self.permissions = {"read", "write"}

    async def require_auth() -> AuthToken:
        return AuthToken()

    async def optional_auth() -> Optional[AuthToken]:
        return AuthToken()


# =============================================================================
# P1: Database Retry Logic
# =============================================================================

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from scripts.utils.db_retry import with_db_retry, connect_with_retry

    RETRY_AVAILABLE = True
    logging.info("✅ Database retry decorator loaded successfully")
except ImportError as e:
    RETRY_AVAILABLE = False
    logging.warning(f"⚠️ Database retry not available: {e}")

    # Fallback no-op decorator
    def with_db_retry(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def connect_with_retry(db_path, **kwargs):
        import duckdb

        return duckdb.connect(db_path, read_only=kwargs.get("read_only", True))


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
# P2: Correlation ID Middleware (Structured Logging)
# =============================================================================

if LOGGING_CONFIGURED:
    app.add_middleware(CorrelationIDMiddleware)
    logging.info("✅ Correlation ID middleware registered")

# =============================================================================
# T053: Performance Metrics Collection
# =============================================================================

try:
    from metrics_collector import MetricsCollector, metrics_middleware

    metrics_collector = MetricsCollector(max_history=1000)
    app.middleware("http")(metrics_middleware(metrics_collector))
    METRICS_AVAILABLE = True
    logging.info("✅ Performance metrics collector enabled")
except ImportError as e:
    METRICS_AVAILABLE = False
    metrics_collector = None
    logging.warning(f"⚠️ Performance metrics not available: {e}")

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
# T036: Include Whale Detection REST API Router
# =============================================================================

try:
    from mempool_whale_endpoints import router as whale_router

    app.include_router(whale_router)
    logging.info("✅ Whale detection API endpoints registered at /api/whale/*")
except ImportError as e:
    logging.warning(f"⚠️ Whale detection endpoints not available: {e}")
    logging.warning("   Install mempool_whale_endpoints.py to enable whale API")

# =============================================================================
# Pydantic Models
# =============================================================================


class PriceEntry(BaseModel):
    """Single price comparison entry"""

    timestamp: str
    utxoracle_price: Optional[float] = None
    mempool_price: Optional[float] = None
    confidence: float
    tx_count: Optional[int] = None
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


class ServiceCheck(BaseModel):
    """Individual service health check result"""

    status: str = Field(description="ok, error, or timeout")
    latency_ms: Optional[float] = Field(
        default=None, description="Service response time in milliseconds"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    last_success: Optional[str] = Field(
        default=None, description="ISO timestamp of last successful check"
    )


class HealthStatus(BaseModel):
    """API health check response with service connectivity checks"""

    status: str = Field(description="healthy, degraded, or unhealthy")
    timestamp: datetime = Field(description="Current timestamp")
    uptime_seconds: float
    started_at: str
    checks: Dict[str, ServiceCheck] = Field(
        default_factory=dict, description="Individual service health checks"
    )

    # T035: Memory usage indicator
    memory_mb: Optional[float] = Field(
        default=None, description="Current process memory usage in MB"
    )
    memory_percent: Optional[float] = Field(
        default=None, description="Memory usage as percentage of configured max"
    )

    # Backward compatibility fields
    database: str
    gaps_detected: Optional[int] = Field(
        default=None, description="Number of missing dates in last 7 days"
    )
    missing_dates: Optional[List[str]] = Field(
        default=None, description="List of missing dates (max 10)"
    )


class WhaleFlowData(BaseModel):
    """Whale flow signal data from latest analysis"""

    timestamp: str
    whale_net_flow: Optional[float] = Field(
        default=None,
        description="Net BTC flow to/from exchanges (+ bearish, - bullish)",
    )
    whale_direction: Optional[str] = Field(
        default=None,
        description="ACCUMULATION (bullish) | DISTRIBUTION (bearish) | NEUTRAL",
    )
    action: Optional[str] = Field(
        default=None, description="Trading recommendation: BUY | SELL | HOLD"
    )
    combined_signal: Optional[float] = Field(
        default=None,
        description="Fused signal: whale (70%) + UTXOracle (30%), range: -1.0 to 1.0",
    )


# =============================================================================
# Database Helper Functions
# =============================================================================


@with_db_retry(max_attempts=3, initial_delay=1.0)
def get_db_connection():
    """Get DuckDB connection with automatic retry on transient errors"""
    try:
        conn = connect_with_retry(DUCKDB_PATH, max_attempts=3, read_only=True)
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to DuckDB after retries: {e}")
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
async def get_latest_price(auth: AuthToken = Depends(require_auth)):
    """
    Get the most recent price comparison entry.

    **Authentication Required:** JWT token with 'read' permission

    Returns:
        PriceEntry: Latest price data from database

    Raises:
        401: Missing or invalid authentication token
        429: Rate limit exceeded
    """
    conn = get_db_connection()

    try:
        result = conn.execute("""
            SELECT date AS timestamp, utxoracle_price, exchange_price AS mempool_price, confidence,
                   tx_count, price_difference AS diff_amount, avg_pct_diff AS diff_percent, is_valid
            FROM price_analysis
            ORDER BY date DESC
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
        if isinstance(data["timestamp"], (datetime, date)):
            data["timestamp"] = data["timestamp"].isoformat()

        return PriceEntry(**data)

    finally:
        conn.close()


# =============================================================================
# T061: GET /api/prices/historical
# =============================================================================


@app.get("/api/prices/historical", response_model=List[PriceEntry])
async def get_historical_prices(
    auth: AuthToken = Depends(require_auth),
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
            SELECT date AS timestamp, utxoracle_price, exchange_price AS mempool_price, confidence,
                   tx_count, price_difference AS diff_amount, avg_pct_diff AS diff_percent, is_valid
            FROM price_analysis
            WHERE date >= ?
            ORDER BY date ASC
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
            if isinstance(entry["timestamp"], (datetime, date)):
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
    auth: AuthToken = Depends(require_auth),
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
                AVG(price_difference) as avg_diff,
                MAX(price_difference) as max_diff,
                MIN(price_difference) as min_diff,
                AVG(avg_pct_diff) as avg_diff_percent,
                COUNT(*) as total_entries,
                SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_entries
            FROM price_analysis
            WHERE date >= ?
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
# GET /api/whale/latest - Whale Flow Data (spec-004)
# =============================================================================


@app.get("/api/whale/latest", response_model=WhaleFlowData)
async def get_latest_whale_flow(auth: AuthToken = Depends(require_auth)):
    """
    Get the most recent whale flow signal data.

    **Authentication Required:** JWT token with 'read' permission

    Returns:
        WhaleFlowData: Latest whale flow metrics (net_flow, direction, action, combined_signal)

    Raises:
        401: Missing or invalid authentication token
        429: Rate limit exceeded
    """
    conn = get_db_connection()

    try:
        result = conn.execute("""
            SELECT date AS timestamp, whale_net_flow, whale_direction, action, combined_signal
            FROM price_analysis
            WHERE whale_net_flow IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
        """).fetchone()

        if not result:
            # No whale data available yet
            raise HTTPException(
                status_code=404,
                detail="No whale flow data available yet. Whale detector may not have run.",
            )

        return WhaleFlowData(
            timestamp=str(result[0]),
            whale_net_flow=float(result[1]) if result[1] is not None else None,
            whale_direction=result[2],
            action=result[3],
            combined_signal=float(result[4]) if result[4] is not None else None,
        )

    finally:
        conn.close()


# =============================================================================
# Service Connectivity Helper Functions
# =============================================================================


async def check_electrs_connectivity() -> ServiceCheck:
    """
    Check electrs HTTP API connectivity with timeout.

    Returns:
        ServiceCheck: Status, latency, and error details
    """
    url = "http://localhost:3001/blocks/tip/height"
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=2.0)
            ) as response:
                latency_ms = round((time.time() - start) * 1000, 2)

                if response.status == 200:
                    return ServiceCheck(
                        status="ok",
                        latency_ms=latency_ms,
                        last_success=datetime.utcnow().isoformat(),
                    )
                else:
                    return ServiceCheck(status="error", error=f"HTTP {response.status}")
    except asyncio.TimeoutError:
        return ServiceCheck(status="timeout", error="Request timeout (>2s)")
    except Exception as e:
        return ServiceCheck(status="error", error=str(e))


async def check_mempool_backend() -> ServiceCheck:
    """
    Check mempool.space backend API connectivity with timeout.

    Returns:
        ServiceCheck: Status, latency, and error details
    """
    url = "http://localhost:8999/api/v1/prices"
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=2.0)
            ) as response:
                latency_ms = round((time.time() - start) * 1000, 2)

                if response.status == 200:
                    return ServiceCheck(
                        status="ok",
                        latency_ms=latency_ms,
                        last_success=datetime.utcnow().isoformat(),
                    )
                else:
                    return ServiceCheck(status="error", error=f"HTTP {response.status}")
    except asyncio.TimeoutError:
        return ServiceCheck(status="timeout", error="Request timeout (>2s)")
    except Exception as e:
        return ServiceCheck(status="error", error=str(e))


# =============================================================================
# T063: GET /health (Enhanced with Service Connectivity Checks)
# =============================================================================


@app.get("/health", response_model=HealthStatus)
async def health_check():
    """
    Comprehensive health check with service connectivity.

    Checks:
    - Database (DuckDB) connectivity and gap detection
    - electrs HTTP API availability
    - mempool.space backend API availability

    Returns:
        HealthStatus: Detailed health status with service checks
    """
    # Calculate uptime
    uptime = (datetime.now() - STARTUP_TIME).total_seconds()

    # Check database connectivity and detect gaps
    db_status = "disconnected"
    gaps = []
    gaps_count = 0

    try:
        start = time.time()
        conn = get_db_connection()

        # Try a simple query
        conn.execute("SELECT 1").fetchone()
        latency_ms = round((time.time() - start) * 1000, 2)

        # Detect gaps in last 7 days
        gap_query = """
            WITH date_range AS (
                SELECT (CURRENT_DATE - INTERVAL (n) DAY)::DATE as expected_date
                FROM generate_series(0, 6) as t(n)
            )
            SELECT dr.expected_date::VARCHAR
            FROM date_range dr
            LEFT JOIN price_analysis p ON p.date = dr.expected_date
            WHERE p.date IS NULL
            ORDER BY dr.expected_date DESC
            LIMIT 10
        """
        gap_results = conn.execute(gap_query).fetchall()
        gaps = [row[0] for row in gap_results]
        gaps_count = len(gaps)

        conn.close()

        # Create successful database check
        db_check = ServiceCheck(
            status="ok",
            latency_ms=latency_ms,
            last_success=datetime.utcnow().isoformat(),
        )
        db_status = "connected"

    except Exception as e:
        logging.error(f"Health check database error: {e}")
        db_check = ServiceCheck(status="error", error=str(e))
        db_status = f"error: {str(e)}"

    # Run connectivity checks in parallel
    electrs_check, mempool_check = await asyncio.gather(
        check_electrs_connectivity(), check_mempool_backend()
    )

    # T035: Calculate memory usage
    memory_mb = None
    memory_percent = None
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = round(memory_info.rss / 1024 / 1024, 2)  # Convert to MB
        # Assume 512MB as default max (configurable in production)
        max_memory_mb = int(os.getenv("MAX_MEMORY_MB", "512"))
        memory_percent = round((memory_mb / max_memory_mb) * 100, 1)
    except Exception as e:
        logging.warning(f"Failed to get memory usage: {e}")

    # Build checks dictionary
    checks = {
        "database": db_check,
        "electrs": electrs_check,
        "mempool_backend": mempool_check,
    }

    # Determine overall status
    if all(c.status == "ok" for c in checks.values()):
        # All services OK
        if gaps_count > 0:
            overall_status = "degraded"  # Services OK but data gaps
        else:
            overall_status = "healthy"  # Perfect health
    elif checks["database"].status != "ok":
        overall_status = "unhealthy"  # Critical service down
    else:
        overall_status = "degraded"  # Non-critical service issues

    return HealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow(),
        uptime_seconds=uptime,
        started_at=STARTUP_TIME.isoformat(),
        checks=checks,
        # T035: Memory usage
        memory_mb=memory_mb,
        memory_percent=memory_percent,
        # Backward compatibility
        database=db_status,
        gaps_detected=gaps_count if gaps_count > 0 else None,
        missing_dates=gaps if gaps else None,
    )


# =============================================================================
# T053: GET /metrics (Performance Metrics)
# =============================================================================


@app.get("/metrics")
async def performance_metrics(
    window: int = Query(
        60, description="Time window in seconds for throughput calculation"
    ),
):
    """
    Get performance metrics for API endpoints.

    Returns:
        dict: Aggregated metrics including:
            - total_requests: Total requests processed
            - total_errors: Total error responses
            - error_rate_percent: Percentage of failed requests
            - uptime_seconds: Time since metrics collection started
            - avg_latency_ms: Average request latency
            - min_latency_ms: Minimum request latency
            - max_latency_ms: Maximum request latency
            - throughput_rps: Requests per second in recent window
            - endpoints: Per-endpoint statistics
    """
    if not METRICS_AVAILABLE or metrics_collector is None:
        raise HTTPException(
            status_code=503, detail="Performance metrics collection is not enabled"
        )

    return metrics_collector.get_metrics(window_seconds=window)


# =============================================================================
# Root Endpoint
# =============================================================================


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "UTXOracle API",
        "version": "1.0.0",
        "spec": "003-mempool-integration-refactor, 004-whale-flow-detection, 005-mempool-whale-realtime",
        "endpoints": {
            "latest": "/api/prices/latest",
            "historical": "/api/prices/historical?days=7",
            "comparison": "/api/prices/comparison?days=7",
            "whale_latest": "/api/whale/latest",
            "health": "/health",
            "metrics": "/metrics?window=60",
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
