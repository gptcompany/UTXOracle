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

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import aiohttp
import psutil

# =============================================================================
# P2: Structured Logging Configuration
# =============================================================================

import sys

sys.path.insert(0, str(Path(__file__).parent))

try:
    from logging_config import (
        configure_structured_logging,
        CorrelationIDMiddleware,
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

# Wasserstein Distance Configuration (spec-010)
WASSERSTEIN_SHIFT_THRESHOLD = float(os.getenv("WASSERSTEIN_SHIFT_THRESHOLD", "0.10"))

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
async def get_latest_price():
    """
    Get the most recent price comparison entry.

    **Public Endpoint:** No authentication required

    Returns:
        PriceEntry: Latest price data from database

    Raises:
        404: No price data available
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
    days: int = Query(
        default=7,
        ge=1,
        le=365,
        description="Number of days of historical data to retrieve",
    ),
):
    """
    Get historical price comparison data.

    **Public Endpoint:** No authentication required

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
    days: int = Query(
        default=7, ge=1, le=365, description="Number of days for statistics calculation"
    ),
):
    """
    Get statistical comparison metrics between UTXOracle and exchange prices.

    **Public Endpoint:** No authentication required

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
async def get_latest_whale_flow():
    """
    Get the most recent whale flow signal data.

    **Public Endpoint:** No authentication required

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
# GET /api/whale/historical - Historical Whale Flow Data (spec-004, T064)
# =============================================================================


@app.get("/api/whale/historical")
async def get_historical_whale_flow(
    start: int = Query(None, description="Start timestamp (milliseconds)"),
    end: int = Query(None, description="End timestamp (milliseconds)"),
    timeframe: str = Query("24h", description="Timeframe (1h, 6h, 24h, 7d)"),
):
    """
    Get historical whale flow data for the specified time range.

    **Public Endpoint:** No authentication required

    Args:
        start: Start timestamp in milliseconds (optional, derived from timeframe if not provided)
        end: End timestamp in milliseconds (optional, defaults to now)
        timeframe: Time range (1h, 6h, 24h, 7d) - used if start/end not provided

    Returns:
        dict: { success: bool, data: [...], count: int }

    Example:
        GET /api/whale/historical?timeframe=24h
        GET /api/whale/historical?start=1700000000000&end=1700086400000
    """
    conn = get_db_connection()

    try:
        # Calculate time range
        if end is None:
            end_time = datetime.utcnow()
        else:
            end_time = datetime.fromtimestamp(end / 1000)  # Convert ms to seconds

        if start is None:
            # Derive from timeframe
            duration_map = {
                "1h": timedelta(hours=1),
                "6h": timedelta(hours=6),
                "24h": timedelta(hours=24),
                "7d": timedelta(days=7),
            }
            duration = duration_map.get(timeframe, timedelta(hours=24))
            start_time = end_time - duration
        else:
            start_time = datetime.fromtimestamp(start / 1000)

        # Query database for whale flow data in time range
        results = conn.execute(
            """
            SELECT
                date AS timestamp,
                whale_net_flow,
                whale_direction
            FROM price_analysis
            WHERE whale_net_flow IS NOT NULL
              AND date >= ?
              AND date <= ?
            ORDER BY date ASC
        """,
            (start_time.isoformat(), end_time.isoformat()),
        ).fetchall()

        # Transform to expected format
        data = [
            {
                "timestamp": row[0],
                "net_flow_btc": float(row[1]) if row[1] is not None else 0.0,
                "direction": row[2] if row[2] else "NEUTRAL",
            }
            for row in results
        ]

        return {"success": True, "data": data, "count": len(data)}

    except Exception as e:
        logging.error(f"Error fetching historical whale data: {e}")
        return {"success": False, "error": str(e), "data": [], "count": 0}

    finally:
        conn.close()


# Alias: /api/whale/history -> /api/whale/historical (for backward compatibility)
@app.get("/api/whale/history")
async def whale_history_alias(
    start: int = Query(None),
    end: int = Query(None),
    timeframe: str = Query("24h"),
):
    """Alias for /api/whale/historical endpoint (backward compatibility)."""
    return await get_historical_whale_flow(start=start, end=end, timeframe=timeframe)


# =============================================================================
# Spec-007: On-Chain Metrics API Endpoints
# =============================================================================


class MonteCarloFusionResponse(BaseModel):
    """Monte Carlo signal fusion result."""

    signal_mean: float = Field(..., description="Mean of bootstrap samples")
    signal_std: float = Field(..., description="Standard deviation of samples")
    ci_lower: float = Field(..., description="95% CI lower bound")
    ci_upper: float = Field(..., description="95% CI upper bound")
    action: str = Field(..., description="Recommended action: BUY/SELL/HOLD")
    action_confidence: float = Field(..., description="Confidence in action")
    n_samples: int = Field(default=1000, description="Bootstrap iterations")
    distribution_type: str = Field(default="unimodal", description="unimodal/bimodal")


class ActiveAddressesResponse(BaseModel):
    """Active addresses metric."""

    block_height: int = Field(..., description="Bitcoin block height")
    active_addresses_block: int = Field(..., description="Unique addresses in block")
    active_addresses_24h: Optional[int] = Field(
        None, description="24h unique addresses"
    )
    unique_senders: int = Field(..., description="Unique senders")
    unique_receivers: int = Field(..., description="Unique receivers")
    is_anomaly: bool = Field(default=False, description="Anomaly detected")


class TxVolumeResponse(BaseModel):
    """Transaction volume metric."""

    tx_count: int = Field(..., description="Transaction count")
    tx_volume_btc: float = Field(..., description="Volume in BTC")
    tx_volume_usd: Optional[float] = Field(None, description="Volume in USD")
    utxoracle_price_used: Optional[float] = Field(None, description="Price used")
    low_confidence: bool = Field(default=False, description="Low confidence flag")


class MetricsLatestResponse(BaseModel):
    """Combined metrics response for /api/metrics/latest."""

    timestamp: datetime = Field(..., description="Metrics timestamp")
    monte_carlo: Optional[MonteCarloFusionResponse] = Field(
        None, description="Signal fusion"
    )
    active_addresses: Optional[ActiveAddressesResponse] = Field(
        None, description="Address metrics"
    )
    tx_volume: Optional[TxVolumeResponse] = Field(None, description="Volume metrics")


# =============================================================================
# Spec-009: Advanced On-Chain Analytics Response Models
# =============================================================================


class PowerLawResponse(BaseModel):
    """Power law regime detection result (spec-009)."""

    tau: float = Field(..., description="Power law exponent")
    tau_std: float = Field(..., description="Standard error of tau")
    xmin: float = Field(..., description="Minimum cutoff value")
    ks_statistic: float = Field(..., description="KS goodness-of-fit statistic")
    ks_pvalue: float = Field(..., description="KS test p-value")
    is_valid: bool = Field(..., description="Whether fit is statistically valid")
    regime: str = Field(
        ..., description="Market regime: ACCUMULATION/NEUTRAL/DISTRIBUTION"
    )
    power_law_vote: float = Field(..., description="Signal vote [-1, 1]")
    sample_size: int = Field(..., description="Number of samples analyzed")


class SymbolicDynamicsResponse(BaseModel):
    """Symbolic dynamics pattern detection result (spec-009)."""

    permutation_entropy: float = Field(..., description="Normalized entropy H [0, 1]")
    statistical_complexity: float = Field(..., description="Statistical complexity C")
    order: int = Field(..., description="Embedding order used")
    complexity_class: str = Field(..., description="LOW/MEDIUM/HIGH")
    pattern_type: str = Field(
        ...,
        description="Pattern type: ACCUMULATION_TREND/DISTRIBUTION_TREND/CHAOTIC_TRANSITION/EDGE_OF_CHAOS",
    )
    symbolic_vote: float = Field(..., description="Signal vote [-1, 1]")
    series_length: int = Field(..., description="Length of analyzed series")
    series_trend: float = Field(
        ..., description="Trend direction (+/- for accumulation/distribution)"
    )
    is_valid: bool = Field(..., description="Whether analysis is valid")


class FractalDimensionResponse(BaseModel):
    """Fractal dimension analysis result (spec-009)."""

    dimension: float = Field(..., description="Box-counting dimension D")
    dimension_std: float = Field(..., description="Standard error of D")
    r_squared: float = Field(..., description="R² of log-log fit")
    is_valid: bool = Field(..., description="Whether fit is statistically valid")
    structure: str = Field(
        ..., description="Market structure: WHALE_DOMINATED/MIXED/RETAIL_DOMINATED"
    )
    fractal_vote: float = Field(..., description="Signal vote [-1, 1]")
    sample_size: int = Field(..., description="Number of samples analyzed")


class EnhancedFusionResponse(BaseModel):
    """Enhanced 7-component Monte Carlo fusion result (spec-009)."""

    signal_mean: float = Field(..., description="Mean of bootstrap samples")
    signal_std: float = Field(..., description="Standard deviation of samples")
    ci_lower: float = Field(..., description="95% CI lower bound")
    ci_upper: float = Field(..., description="95% CI upper bound")
    action: str = Field(..., description="Recommended action: BUY/SELL/HOLD")
    action_confidence: float = Field(..., description="Confidence in action")
    n_samples: int = Field(default=1000, description="Bootstrap iterations")
    distribution_type: str = Field(default="unimodal", description="unimodal/bimodal")
    components_available: int = Field(..., description="Number of components used")
    components_used: List[str] = Field(
        default_factory=list, description="List of component names used"
    )


class AdvancedMetricsResponse(BaseModel):
    """Combined advanced metrics response for /api/metrics/advanced (spec-009)."""

    timestamp: datetime = Field(..., description="Metrics timestamp")
    power_law: Optional[PowerLawResponse] = Field(
        None, description="Power law regime detection"
    )
    symbolic_dynamics: Optional[SymbolicDynamicsResponse] = Field(
        None, description="Symbolic dynamics pattern"
    )
    fractal_dimension: Optional[FractalDimensionResponse] = Field(
        None, description="Fractal dimension analysis"
    )
    enhanced_fusion: Optional[EnhancedFusionResponse] = Field(
        None, description="7-component enhanced fusion"
    )


def _fetch_derivatives_sync() -> dict:
    """
    Synchronous helper to fetch derivatives data from LiquidationHeatmap.

    Called via asyncio.to_thread() to avoid blocking the event loop.
    Connection is properly managed with finally block.
    """
    from scripts.derivatives import get_liq_connection, close_connection
    from scripts.derivatives.funding_rate_reader import get_latest_funding_signal
    from scripts.derivatives.oi_reader import get_latest_oi_signal

    liq_conn = None
    try:
        liq_conn = get_liq_connection()
        if not liq_conn:
            return {"available": False}

        derivatives_data = {"available": True}

        # Funding rate signal
        funding_signal = get_latest_funding_signal(conn=liq_conn)
        if funding_signal:
            derivatives_data["funding"] = {
                "timestamp": funding_signal.timestamp.isoformat(),
                "funding_rate": funding_signal.funding_rate,
                "funding_vote": funding_signal.funding_vote,
                "is_extreme": funding_signal.is_extreme,
            }

        # OI signal (using NEUTRAL whale direction for API)
        oi_signal = get_latest_oi_signal(conn=liq_conn, whale_direction="NEUTRAL")
        if oi_signal:
            derivatives_data["oi"] = {
                "timestamp": oi_signal.timestamp.isoformat(),
                "oi_value": oi_signal.oi_value,
                "oi_change_1h": oi_signal.oi_change_1h,
                "oi_change_24h": oi_signal.oi_change_24h,
                "oi_vote": oi_signal.oi_vote,
                "context": oi_signal.context,
            }

        return derivatives_data
    finally:
        if liq_conn:
            close_connection(liq_conn)


@app.get("/api/metrics/latest", response_model=MetricsLatestResponse)
async def get_latest_metrics():
    """
    Get the most recent on-chain metrics (spec-007).

    Returns Monte Carlo fusion, Active Addresses, and TX Volume.
    """
    import duckdb

    db_path = os.getenv(
        "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
    )

    conn = None
    try:
        conn = duckdb.connect(db_path, read_only=True)

        # Fetch latest metrics record
        result = conn.execute(
            "SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="No metrics found")

        columns = [desc[0] for desc in conn.description]
        data = dict(zip(columns, result))

        # Build response
        response = {"timestamp": data.get("timestamp", datetime.now())}

        # Monte Carlo Fusion
        if data.get("signal_mean") is not None:
            response["monte_carlo"] = {
                "signal_mean": data["signal_mean"],
                "signal_std": data.get("signal_std", 0),
                "ci_lower": data.get("ci_lower", 0),
                "ci_upper": data.get("ci_upper", 0),
                "action": data.get("action", "HOLD"),
                "action_confidence": data.get("action_confidence", 0),
                "n_samples": data.get("n_samples", 1000),
                "distribution_type": data.get("distribution_type", "unimodal"),
            }

        # Active Addresses
        if data.get("active_addresses_block") is not None:
            response["active_addresses"] = {
                "block_height": data.get("block_height", 0),
                "active_addresses_block": data["active_addresses_block"],
                "active_addresses_24h": data.get("active_addresses_24h"),
                "unique_senders": data.get("unique_senders", 0),
                "unique_receivers": data.get("unique_receivers", 0),
                "is_anomaly": data.get("is_anomaly", False),
            }

        # TX Volume
        if data.get("tx_count") is not None:
            response["tx_volume"] = {
                "tx_count": data["tx_count"],
                "tx_volume_btc": data.get("tx_volume_btc", 0),
                "tx_volume_usd": data.get("tx_volume_usd"),
                "utxoracle_price_used": data.get("utxoracle_price_used"),
                "low_confidence": data.get("low_confidence", False),
            }

        # Derivatives signals (spec-008)
        # Fetch from LiquidationHeatmap if available
        # Use asyncio.to_thread to avoid blocking the event loop with sync DuckDB calls
        try:
            derivatives_data = await asyncio.to_thread(_fetch_derivatives_sync)
            response["derivatives"] = derivatives_data
        except ImportError:
            response["derivatives"] = {"available": False, "error": "module_not_found"}
        except Exception as e:
            response["derivatives"] = {"available": False, "error": str(e)}

        return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/advanced", response_model=AdvancedMetricsResponse)
async def get_advanced_metrics():
    """
    Get advanced on-chain analytics (spec-009).

    Returns Power Law regime detection, Symbolic Dynamics patterns,
    Fractal Dimension analysis, and Enhanced 7-component fusion.

    These metrics provide +40% improvement in signal accuracy over spec-007.
    """
    try:
        # Import advanced metrics modules
        from scripts.metrics.power_law import fit as power_law_fit
        from scripts.metrics.symbolic_dynamics import analyze as symbolic_analyze
        from scripts.metrics.fractal_dimension import analyze as fractal_analyze
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        # Fetch recent UTXO data from mempool.space API
        utxo_values = []
        tx_volumes = []

        # Fetch transactions from electrs
        async with aiohttp.ClientSession() as session:
            # Get latest block hash
            async with session.get(
                "http://localhost:3001/blocks/tip/hash",
                timeout=aiohttp.ClientTimeout(total=10.0),
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="electrs unavailable")
                best_hash = (await response.text()).strip().strip('"')

            # Get transaction IDs from block
            async with session.get(
                f"http://localhost:3001/block/{best_hash}/txids",
                timeout=aiohttp.ClientTimeout(total=30.0),
            ) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=503, detail="Failed to fetch block txids"
                    )
                txids = await response.json()

            # Fetch a sample of transactions (max 500 for performance)
            sample_txids = txids[:500] if len(txids) > 500 else txids
            logging.info(
                f"Fetching {len(sample_txids)} transactions for advanced metrics"
            )

            for txid in sample_txids:
                try:
                    async with session.get(
                        f"http://localhost:3001/tx/{txid}",
                        timeout=aiohttp.ClientTimeout(total=5.0),
                    ) as response:
                        if response.status == 200:
                            tx = await response.json()
                            total_out = 0
                            for vout in tx.get("vout", []):
                                value = vout.get("value", 0) / 1e8  # satoshi to BTC
                                if value > 0:
                                    utxo_values.append(value)
                                    total_out += value
                            if total_out > 0:
                                tx_volumes.append(total_out)
                except Exception:
                    continue  # Skip failed transactions

        # Build response
        response = {"timestamp": datetime.now()}

        # US1: Power Law Regime Detection
        if len(utxo_values) >= 100:
            try:
                power_law_result = await asyncio.to_thread(power_law_fit, utxo_values)
                response["power_law"] = {
                    "tau": power_law_result.tau,
                    "tau_std": power_law_result.tau_std,
                    "xmin": power_law_result.xmin,
                    "ks_statistic": power_law_result.ks_statistic,
                    "ks_pvalue": power_law_result.ks_pvalue,
                    "is_valid": power_law_result.is_valid,
                    "regime": power_law_result.regime,
                    "power_law_vote": power_law_result.power_law_vote,
                    "sample_size": power_law_result.sample_size,
                }
            except Exception as e:
                logging.warning(f"Power law analysis failed: {e}")

        # US3: Fractal Dimension Analysis
        if len(utxo_values) >= 100:
            try:
                fractal_result = await asyncio.to_thread(fractal_analyze, utxo_values)
                response["fractal_dimension"] = {
                    "dimension": fractal_result.dimension,
                    "dimension_std": fractal_result.dimension_std,
                    "r_squared": fractal_result.r_squared,
                    "is_valid": fractal_result.is_valid,
                    "structure": fractal_result.structure,
                    "fractal_vote": fractal_result.fractal_vote,
                    "sample_size": fractal_result.sample_size,
                }
            except Exception as e:
                logging.warning(f"Fractal dimension analysis failed: {e}")

        # US2: Symbolic Dynamics Pattern Detection
        if len(tx_volumes) >= 240:
            try:
                symbolic_result = await asyncio.to_thread(
                    symbolic_analyze, tx_volumes, 5
                )
                response["symbolic_dynamics"] = {
                    "permutation_entropy": symbolic_result.permutation_entropy,
                    "statistical_complexity": symbolic_result.statistical_complexity,
                    "order": symbolic_result.order,
                    "complexity_class": symbolic_result.complexity_class,
                    "pattern_type": symbolic_result.pattern_type,
                    "symbolic_vote": symbolic_result.symbolic_vote,
                    "series_length": symbolic_result.series_length,
                    "series_trend": symbolic_result.series_trend,
                    "is_valid": symbolic_result.is_valid,
                }
            except Exception as e:
                logging.warning(f"Symbolic dynamics analysis failed: {e}")

        # US4: Enhanced Fusion (if we have enough components)
        power_law_vote = (
            response.get("power_law", {}).get("power_law_vote")
            if response.get("power_law", {}).get("is_valid")
            else None
        )
        symbolic_vote = (
            response.get("symbolic_dynamics", {}).get("symbolic_vote")
            if response.get("symbolic_dynamics", {}).get("is_valid")
            else None
        )
        fractal_vote = (
            response.get("fractal_dimension", {}).get("fractal_vote")
            if response.get("fractal_dimension", {}).get("is_valid")
            else None
        )

        # Only run enhanced fusion if we have at least one advanced metric
        if any([power_law_vote, symbolic_vote, fractal_vote]):
            try:
                enhanced_result = await asyncio.to_thread(
                    enhanced_fusion,
                    None,  # whale_vote (not available in API context)
                    None,  # whale_conf
                    None,  # utxo_vote (would need UTXOracle calculation)
                    None,  # utxo_conf
                    None,  # funding_vote
                    None,  # oi_vote
                    power_law_vote,
                    symbolic_vote,
                    fractal_vote,
                    1000,  # n_samples
                    None,  # weights
                )
                response["enhanced_fusion"] = {
                    "signal_mean": enhanced_result.signal_mean,
                    "signal_std": enhanced_result.signal_std,
                    "ci_lower": enhanced_result.ci_lower,
                    "ci_upper": enhanced_result.ci_upper,
                    "action": enhanced_result.action,
                    "action_confidence": enhanced_result.action_confidence,
                    "n_samples": enhanced_result.n_samples,
                    "distribution_type": enhanced_result.distribution_type,
                    "components_available": enhanced_result.components_available,
                    "components_used": enhanced_result.components_used,
                }
            except Exception as e:
                logging.warning(f"Enhanced fusion failed: {e}")

        return response

    except HTTPException:
        raise
    except ImportError as e:
        logging.error(f"Spec-009 modules not available: {e}")
        raise HTTPException(
            status_code=501,
            detail="Advanced metrics modules not installed. Run: pip install -e .",
        )
    except Exception as e:
        logging.error(f"Error computing advanced metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Computation error: {str(e)}")


# =============================================================================
# spec-010: Wasserstein Distance API Endpoints
# =============================================================================


@app.get("/api/metrics/wasserstein")
async def get_wasserstein_latest():
    """
    Get latest Wasserstein metrics (spec-010).

    Returns the most recent Wasserstein distance calculation and regime status.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        # Query latest Wasserstein metrics from metrics table
        result = conn.execute(
            """
            SELECT
                timestamp,
                wasserstein_distance,
                wasserstein_normalized,
                wasserstein_shift_direction,
                wasserstein_regime_status,
                wasserstein_vote,
                wasserstein_is_valid
            FROM metrics
            WHERE wasserstein_distance IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No Wasserstein metrics available. Run daily_analysis.py first.",
            )

        return {
            "timestamp": result[0].isoformat() if result[0] else None,
            "distance": result[1],
            "distance_normalized": result[2],
            "shift_direction": result[3] or "NONE",
            "regime_status": result[4] or "STABLE",
            "wasserstein_vote": result[5] or 0.0,
            "is_valid": result[6] if result[6] is not None else False,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Handle missing columns gracefully (schema not yet migrated)
        if "wasserstein" in error_msg or "column" in error_msg or "binder" in error_msg:
            logging.info("Wasserstein columns not yet available in database schema")
            raise HTTPException(
                status_code=404,
                detail="Wasserstein metrics not available. Schema migration pending.",
            )
        logging.error(f"Error fetching Wasserstein metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/wasserstein/history")
async def get_wasserstein_history(
    hours: int = Query(
        default=24, ge=1, le=168, description="Hours of history to return"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum data points"),
):
    """
    Get historical Wasserstein distances (spec-010).

    Returns rolling Wasserstein distances for the specified period.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        cutoff = datetime.now() - timedelta(hours=hours)

        # L2 fix: Use configurable threshold instead of hardcoded 0.10
        results = conn.execute(
            f"""
            SELECT
                timestamp,
                wasserstein_distance,
                wasserstein_shift_direction,
                CASE WHEN wasserstein_distance > {WASSERSTEIN_SHIFT_THRESHOLD} THEN true ELSE false END as is_significant
            FROM metrics
            WHERE wasserstein_distance IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT {limit}
            """,
            [cutoff],
        ).fetchall()

        data = [
            {
                "timestamp": r[0].isoformat() if r[0] else None,
                "distance": r[1],
                "shift_direction": r[2] or "NONE",
                "is_significant": r[3],
            }
            for r in results
        ]

        # Compute summary statistics
        distances = [r[1] for r in results if r[1] is not None]

        summary = {
            "mean_distance": sum(distances) / len(distances) if distances else 0.0,
            "max_distance": max(distances) if distances else 0.0,
            "min_distance": min(distances) if distances else 0.0,
            "std_distance": 0.0,
            "sustained_shifts": sum(1 for d in data if d["is_significant"]),
            "period_hours": hours,
        }

        # Compute std if we have enough data
        if len(distances) > 1:
            mean = summary["mean_distance"]
            variance = sum((d - mean) ** 2 for d in distances) / (len(distances) - 1)
            summary["std_distance"] = variance**0.5

        return {"data": data, "summary": summary}

    except Exception as e:
        error_msg = str(e).lower()
        # L3 fix: Consistent error handling - raise 404 for schema migration issues
        if "wasserstein" in error_msg or "column" in error_msg or "binder" in error_msg:
            logging.info("Wasserstein columns not yet available in database schema")
            raise HTTPException(
                status_code=404,
                detail="Wasserstein metrics not available. Schema migration pending.",
            )
        logging.error(f"Error fetching Wasserstein history: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/wasserstein/regime")
async def get_wasserstein_regime():
    """
    Get current regime status (spec-010).

    Returns simplified regime status for trading decisions.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        # Get recent Wasserstein metrics to determine regime
        results = conn.execute(
            """
            SELECT
                wasserstein_distance,
                wasserstein_shift_direction,
                wasserstein_regime_status,
                timestamp
            FROM metrics
            WHERE wasserstein_distance IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 10
            """
        ).fetchall()

        if not results:
            raise HTTPException(
                status_code=404,
                detail="No Wasserstein metrics available.",
            )

        # Determine overall status
        latest = results[0]
        status = latest[2] or "STABLE"

        # Calculate confidence based on consistency
        statuses = [r[2] for r in results if r[2]]
        if statuses:
            status_counts = {}
            for s in statuses:
                status_counts[s] = status_counts.get(s, 0) + 1
            confidence = max(status_counts.values()) / len(statuses)
        else:
            confidence = 0.5

        # Generate recommendation
        recommendations = {
            "STABLE": "No significant distribution shift detected. Current strategy valid.",
            "TRANSITIONING": "Distribution shift in progress. Monitor closely for confirmation.",
            "SHIFTED": "Significant regime change detected. Consider adjusting strategy.",
        }

        return {
            "status": status,
            "confidence": round(confidence, 2),
            "recommendation": recommendations.get(status, "Unknown status."),
            "last_shift_timestamp": (
                results[0][3].isoformat()
                if results[0][3] and status != "STABLE"
                else None
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Handle missing columns gracefully (schema not yet migrated)
        if "wasserstein" in error_msg or "column" in error_msg or "binder" in error_msg:
            logging.info("Wasserstein columns not yet available in database schema")
            raise HTTPException(
                status_code=404,
                detail="Wasserstein metrics not available. Schema migration pending.",
            )
        logging.error(f"Error fetching regime status: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Spec-018: Cointime Economics Endpoints
# =============================================================================


@app.get("/api/metrics/cointime")
async def get_cointime_latest():
    """
    Get latest Cointime Economics metrics (spec-018).

    Returns the most recent coinblocks, liveliness, supply split, and AVIV metrics.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        # Query latest Cointime metrics from cointime_metrics table
        result = conn.execute(
            """
            SELECT
                block_height,
                timestamp,
                coinblocks_created,
                coinblocks_destroyed,
                cumulative_created,
                cumulative_destroyed,
                liveliness,
                vaultedness,
                active_supply_btc,
                vaulted_supply_btc,
                true_market_mean_usd,
                aviv_ratio,
                aviv_percentile
            FROM cointime_metrics
            ORDER BY block_height DESC
            LIMIT 1
            """
        ).fetchone()

        if not result:
            raise HTTPException(
                status_code=404,
                detail="No Cointime metrics found. Run Cointime calculation first.",
            )

        columns = [desc[0] for desc in conn.description]
        data = dict(zip(columns, result))

        # Classify valuation zone
        valuation_zone = "FAIR"
        if data.get("aviv_ratio") is not None:
            if data["aviv_ratio"] < 1.0:
                valuation_zone = "UNDERVALUED"
            elif data["aviv_ratio"] > 2.5:
                valuation_zone = "OVERVALUED"

        return {
            "block_height": data["block_height"],
            "timestamp": data["timestamp"].isoformat() if data["timestamp"] else None,
            "coinblocks": {
                "created": data["coinblocks_created"],
                "destroyed": data["coinblocks_destroyed"],
                "cumulative_created": data["cumulative_created"],
                "cumulative_destroyed": data["cumulative_destroyed"],
            },
            "liveliness": {
                "value": data["liveliness"],
                "vaultedness": data["vaultedness"],
            },
            "supply": {
                "active_btc": data["active_supply_btc"],
                "vaulted_btc": data["vaulted_supply_btc"],
            },
            "valuation": {
                "true_market_mean_usd": data["true_market_mean_usd"],
                "aviv_ratio": data["aviv_ratio"],
                "aviv_percentile": data["aviv_percentile"],
                "zone": valuation_zone,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Handle missing table gracefully
        if "cointime" in error_msg or "does not exist" in error_msg:
            logging.info("Cointime table not yet available in database schema")
            raise HTTPException(
                status_code=404,
                detail="Cointime metrics not available. Schema migration pending.",
            )
        logging.error(f"Error fetching Cointime metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/cointime/history")
async def get_cointime_history(
    days: int = Query(
        default=30, ge=1, le=365, description="Days of history to return"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum data points"),
):
    """
    Get historical Cointime metrics (spec-018).

    Returns liveliness, AVIV, and supply split history for charting.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        cutoff = datetime.now() - timedelta(days=days)

        results = conn.execute(
            """
            SELECT
                block_height,
                timestamp,
                liveliness,
                aviv_ratio,
                active_supply_btc,
                vaulted_supply_btc
            FROM cointime_metrics
            WHERE timestamp >= ?
            ORDER BY block_height DESC
            LIMIT ?
            """,
            [cutoff, limit],
        ).fetchall()

        if not results:
            raise HTTPException(
                status_code=404,
                detail="No historical Cointime metrics found.",
            )

        columns = [desc[0] for desc in conn.description]
        history = []
        for row in results:
            data = dict(zip(columns, row))
            history.append(
                {
                    "block_height": data["block_height"],
                    "timestamp": data["timestamp"].isoformat()
                    if data["timestamp"]
                    else None,
                    "liveliness": data["liveliness"],
                    "aviv_ratio": data["aviv_ratio"],
                    "active_supply_btc": data["active_supply_btc"],
                    "vaulted_supply_btc": data["vaulted_supply_btc"],
                }
            )

        return {
            "count": len(history),
            "days": days,
            "data": history,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "cointime" in error_msg or "does not exist" in error_msg:
            logging.info("Cointime table not yet available in database schema")
            raise HTTPException(
                status_code=404,
                detail="Cointime metrics not available. Schema migration pending.",
            )
        logging.error(f"Error fetching Cointime history: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/cointime/signal")
async def get_cointime_signal():
    """
    Get current Cointime trading signal (spec-018).

    Returns the AVIV-based valuation signal for fusion integration.
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        # Get recent cointime metrics for signal generation
        result = conn.execute(
            """
            SELECT
                block_height,
                timestamp,
                liveliness,
                aviv_ratio,
                active_supply_btc
            FROM cointime_metrics
            ORDER BY block_height DESC
            LIMIT 1
            """
        ).fetchone()

        if not result:
            raise HTTPException(
                status_code=404,
                detail="No Cointime metrics found for signal generation.",
            )

        columns = [desc[0] for desc in conn.description]
        data = dict(zip(columns, result))

        # Import signal generation from cointime module
        from scripts.metrics.cointime import generate_cointime_signal

        # Get historical data for rolling calculations (simplified)
        signal = generate_cointime_signal(
            liveliness=data["liveliness"],
            liveliness_7d_change=0.0,  # Would need historical data
            liveliness_30d_change=0.0,  # Would need historical data
            aviv_ratio=data["aviv_ratio"] if data["aviv_ratio"] else 1.5,
            active_supply_btc=data["active_supply_btc"],
        )

        return {
            "block_height": data["block_height"],
            "timestamp": data["timestamp"].isoformat() if data["timestamp"] else None,
            "cointime_vote": signal["cointime_vote"],
            "confidence": signal["confidence"],
            "valuation_zone": signal["valuation_zone"],
            "extreme_dormancy": signal["extreme_dormancy"],
            "supply_squeeze": signal["supply_squeeze"],
            "liveliness_trend": signal["liveliness_trend"],
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "cointime" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="Cointime metrics not available. Schema migration pending.",
            )
        logging.error(f"Error generating Cointime signal: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-021: Advanced On-Chain Metrics - URPD
# =============================================================================


class URPDQueryParams(BaseModel):
    """Query parameters for URPD endpoint."""

    bucket_size: float = Field(
        default=5000.0,
        ge=100.0,
        le=50000.0,
        description="Size of each price bucket in USD (100-50000)",
    )
    current_price: float = Field(
        default=100000.0,
        ge=1.0,
        description="Current BTC price for profit/loss calculation",
    )


class URPDBucketResponse(BaseModel):
    """Single price bucket in URPD response."""

    price_low: float
    price_high: float
    btc_amount: float
    utxo_count: int
    percentage: float


class URPDResponse(BaseModel):
    """URPD calculation response."""

    buckets: List[URPDBucketResponse]
    bucket_size_usd: float
    total_supply_btc: float
    current_price_usd: float
    supply_above_price_btc: float
    supply_below_price_btc: float
    supply_above_price_pct: float
    supply_below_price_pct: float
    dominant_bucket: Optional[URPDBucketResponse]
    block_height: int
    timestamp: str


# UTXO Lifecycle Database Path (separate from price_analysis DB)
UTXO_DB_PATH = os.getenv(
    "UTXO_DB_PATH",
    "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxo_lifecycle.duckdb",
)


@app.get("/api/metrics/urpd", response_model=URPDResponse)
async def get_urpd(
    bucket_size: float = Query(
        default=5000.0,
        ge=100.0,
        le=50000.0,
        description="Size of each price bucket in USD",
    ),
    current_price: float = Query(
        default=100000.0, ge=1.0, description="Current BTC price for profit/loss split"
    ),
):
    """
    Calculate UTXO Realized Price Distribution (URPD).

    URPD groups unspent UTXOs into price buckets based on their creation price
    (cost basis). This reveals support/resistance zones based on where holders
    acquired their coins.

    **Use Cases:**
    - Identify price levels with high BTC concentration (support/resistance)
    - Calculate supply in profit vs loss at current price
    - Find the dominant price bucket (most BTC accumulated)

    **Parameters:**
    - `bucket_size`: Width of each price bucket (default: $5,000)
    - `current_price`: Current BTC price for profit/loss calculation

    **Response Fields:**
    - `buckets`: List of price buckets with BTC amount and UTXO count
    - `supply_above_price_btc`: BTC with cost basis > current price (in loss)
    - `supply_below_price_btc`: BTC with cost basis < current price (in profit)
    - `dominant_bucket`: Bucket with highest BTC concentration

    Spec: 021-advanced-onchain-metrics
    """
    import duckdb

    conn = None
    try:
        # Connect to UTXO lifecycle database
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        # Import and calculate URPD
        from scripts.metrics.urpd import calculate_urpd

        result = calculate_urpd(
            conn=conn,
            current_price_usd=current_price,
            bucket_size_usd=bucket_size,
            block_height=block_height,
        )

        # Convert to response model
        return URPDResponse(
            buckets=[
                URPDBucketResponse(
                    price_low=b.price_low,
                    price_high=b.price_high,
                    btc_amount=b.btc_amount,
                    utxo_count=b.utxo_count,
                    percentage=b.percentage,
                )
                for b in result.buckets
            ],
            bucket_size_usd=result.bucket_size_usd,
            total_supply_btc=result.total_supply_btc,
            current_price_usd=result.current_price_usd,
            supply_above_price_btc=result.supply_above_price_btc,
            supply_below_price_btc=result.supply_below_price_btc,
            supply_above_price_pct=result.supply_above_price_pct,
            supply_below_price_pct=result.supply_below_price_pct,
            dominant_bucket=URPDBucketResponse(
                price_low=result.dominant_bucket.price_low,
                price_high=result.dominant_bucket.price_high,
                btc_amount=result.dominant_bucket.btc_amount,
                utxo_count=result.dominant_bucket.utxo_count,
                percentage=result.dominant_bucket.percentage,
            )
            if result.dominant_bucket
            else None,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating URPD: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-021: Advanced On-Chain Metrics - Supply Profit/Loss
# =============================================================================


class SupplyProfitLossResponse(BaseModel):
    """Supply profit/loss calculation response."""

    current_price_usd: float
    total_supply_btc: float
    supply_in_profit_btc: float
    supply_in_loss_btc: float
    supply_breakeven_btc: float
    pct_in_profit: float
    pct_in_loss: float
    sth_in_profit_btc: float
    sth_in_loss_btc: float
    sth_pct_in_profit: float
    lth_in_profit_btc: float
    lth_in_loss_btc: float
    lth_pct_in_profit: float
    market_phase: str
    signal_strength: float
    block_height: int
    timestamp: str


@app.get("/api/metrics/supply-profit-loss", response_model=SupplyProfitLossResponse)
async def get_supply_profit_loss(
    current_price: float = Query(
        default=100000.0,
        ge=1.0,
        description="Current BTC price for profit/loss calculation",
    ),
):
    """
    Calculate Supply Profit/Loss Distribution.

    Classifies circulating supply by profit/loss status based on UTXO cost basis
    vs current price, with STH/LTH cohort segmentation.

    **Market Phases:**
    - **EUPHORIA** (>95% in profit): Cycle top warning
    - **BULL** (80-95% in profit): Strong uptrend
    - **TRANSITION** (50-80% in profit): Uncertain market
    - **CAPITULATION** (<50% in profit): Accumulation zone

    **Use Cases:**
    - Detect market cycle phases
    - Identify overbought/oversold conditions
    - Compare STH vs LTH profitability (sentiment divergence)

    **Parameters:**
    - `current_price`: Current BTC price for comparison (default: $100,000)

    Spec: 021-advanced-onchain-metrics
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        result = calculate_supply_profit_loss(
            conn=conn,
            current_price_usd=current_price,
            block_height=block_height,
        )

        return SupplyProfitLossResponse(
            current_price_usd=result.current_price_usd,
            total_supply_btc=result.total_supply_btc,
            supply_in_profit_btc=result.supply_in_profit_btc,
            supply_in_loss_btc=result.supply_in_loss_btc,
            supply_breakeven_btc=result.supply_breakeven_btc,
            pct_in_profit=result.pct_in_profit,
            pct_in_loss=result.pct_in_loss,
            sth_in_profit_btc=result.sth_in_profit_btc,
            sth_in_loss_btc=result.sth_in_loss_btc,
            sth_pct_in_profit=result.sth_pct_in_profit,
            lth_in_profit_btc=result.lth_in_profit_btc,
            lth_in_loss_btc=result.lth_in_loss_btc,
            lth_pct_in_profit=result.lth_pct_in_profit,
            market_phase=result.market_phase,
            signal_strength=result.signal_strength,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Supply P/L: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-021: Advanced On-Chain Metrics - Reserve Risk
# =============================================================================


class ReserveRiskResponse(BaseModel):
    """Reserve Risk calculation response."""

    reserve_risk: float
    current_price_usd: float
    hodl_bank: float
    circulating_supply_btc: float
    mvrv: float
    liveliness: float
    signal_zone: str
    confidence: float
    block_height: int
    timestamp: str


@app.get("/api/metrics/reserve-risk", response_model=ReserveRiskResponse)
async def get_reserve_risk(
    current_price: float = Query(
        default=100000.0, ge=1.0, description="Current BTC price"
    ),
):
    """
    Calculate Reserve Risk ratio.

    Reserve Risk measures long-term holder confidence relative to price.
    Lower values indicate higher conviction (historically good buy zones).

    **Signal Zones:**
    - **STRONG_BUY** (<0.002): Cycle bottom territory
    - **ACCUMULATION** (0.002-0.008): Good accumulation zone
    - **FAIR_VALUE** (0.008-0.02): Normal market
    - **DISTRIBUTION** (>0.02): Cycle top warning

    Spec: 021-advanced-onchain-metrics
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.reserve_risk import calculate_reserve_risk

        result = calculate_reserve_risk(
            conn=conn,
            current_price_usd=current_price,
            block_height=block_height,
        )

        return ReserveRiskResponse(
            reserve_risk=result.reserve_risk,
            current_price_usd=result.current_price_usd,
            hodl_bank=result.hodl_bank,
            circulating_supply_btc=result.circulating_supply_btc,
            mvrv=result.mvrv,
            liveliness=result.liveliness,
            signal_zone=result.signal_zone,
            confidence=result.confidence,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Reserve Risk: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-021: Advanced On-Chain Metrics - Sell-side Risk
# =============================================================================


class SellSideRiskResponse(BaseModel):
    """Sell-side Risk calculation response."""

    sell_side_risk: float
    sell_side_risk_pct: float
    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    market_cap_usd: float
    window_days: int
    spent_utxos_in_window: int
    signal_zone: str
    confidence: float
    block_height: int
    timestamp: str


@app.get("/api/metrics/sell-side-risk", response_model=SellSideRiskResponse)
async def get_sell_side_risk(
    market_cap: float = Query(
        default=2_000_000_000_000.0, ge=1.0, description="Current market cap in USD"
    ),
    window_days: int = Query(
        default=30, ge=1, le=365, description="Rolling window in days"
    ),
):
    """
    Calculate Sell-side Risk ratio.

    Ratio of realized profit to market cap. High values indicate
    aggressive profit-taking (potential distribution phase).

    **Signal Zones:**
    - **LOW** (<0.1%): Low distribution, bullish
    - **NORMAL** (0.1-0.3%): Normal profit-taking
    - **ELEVATED** (0.3-1.0%): Elevated distribution
    - **AGGRESSIVE** (>1.0%): Cycle top warning

    Spec: 021-advanced-onchain-metrics
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        result = calculate_sell_side_risk(
            conn=conn,
            market_cap_usd=market_cap,
            block_height=block_height,
            window_days=window_days,
        )

        return SellSideRiskResponse(
            sell_side_risk=result.sell_side_risk,
            sell_side_risk_pct=result.sell_side_risk_pct,
            realized_profit_usd=result.realized_profit_usd,
            realized_loss_usd=result.realized_loss_usd,
            net_realized_pnl_usd=result.net_realized_pnl_usd,
            market_cap_usd=result.market_cap_usd,
            window_days=result.window_days,
            spent_utxos_in_window=result.spent_utxos_in_window,
            signal_zone=result.signal_zone,
            confidence=result.confidence,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Sell-side Risk: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-021: Advanced On-Chain Metrics - CDD/VDD
# =============================================================================


class CDDVDDResponse(BaseModel):
    """CDD/VDD calculation response."""

    cdd_total: float
    cdd_daily_avg: float
    vdd_total: float
    vdd_daily_avg: float
    vdd_multiple: Optional[float]
    window_days: int
    spent_utxos_count: int
    avg_utxo_age_days: float
    max_single_day_cdd: float
    max_single_day_date: Optional[str]
    current_price_usd: float
    signal_zone: str
    confidence: float
    block_height: int
    timestamp: str


@app.get("/api/metrics/cdd-vdd", response_model=CDDVDDResponse)
async def get_cdd_vdd(
    current_price: float = Query(
        default=100000.0, ge=1.0, description="Current BTC price"
    ),
    window_days: int = Query(
        default=30, ge=1, le=365, description="Rolling window in days"
    ),
):
    """
    Calculate Coindays Destroyed (CDD) and Value Days Destroyed (VDD).

    Measures "old money" movement. Spikes indicate long-term holders
    moving coins (distribution or exchange deposit).

    **Signal Zones:**
    - **LOW_ACTIVITY**: Below average CDD (accumulation)
    - **NORMAL**: Typical market activity
    - **ELEVATED**: Above average (distribution possible)
    - **SPIKE**: VDD multiple >2.0 (significant distribution)

    Spec: 021-advanced-onchain-metrics
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=conn,
            current_price_usd=current_price,
            block_height=block_height,
            window_days=window_days,
        )

        return CDDVDDResponse(
            cdd_total=result.cdd_total,
            cdd_daily_avg=result.cdd_daily_avg,
            vdd_total=result.vdd_total,
            vdd_daily_avg=result.vdd_daily_avg,
            vdd_multiple=result.vdd_multiple,
            window_days=result.window_days,
            spent_utxos_count=result.spent_utxos_count,
            avg_utxo_age_days=result.avg_utxo_age_days,
            max_single_day_cdd=result.max_single_day_cdd,
            max_single_day_date=result.max_single_day_date.isoformat()
            if result.max_single_day_date
            else None,
            current_price_usd=result.current_price_usd,
            signal_zone=result.signal_zone,
            confidence=result.confidence,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating CDD/VDD: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-022: NUPL Oscillator
# =============================================================================


class NUPLResponse(BaseModel):
    """NUPL Oscillator response model (spec-022)."""

    nupl: float = Field(..., description="NUPL value (-1 to 1 range)")
    zone: str = Field(
        ...,
        description="Market cycle zone: CAPITULATION|HOPE_FEAR|OPTIMISM|BELIEF|EUPHORIA",
    )
    market_cap_usd: float = Field(..., description="Market cap in USD")
    realized_cap_usd: float = Field(..., description="Realized cap in USD")
    unrealized_profit_usd: float = Field(
        ..., description="Unrealized profit (Market Cap - Realized Cap)"
    )
    pct_supply_in_profit: float = Field(
        ..., description="Approximate % of supply in profit"
    )
    confidence: float = Field(..., description="Signal confidence (0-1)")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")


@app.get("/api/metrics/nupl", response_model=NUPLResponse)
async def get_nupl(
    current_price: float = Query(
        default=100000.0,
        ge=1.0,
        description="Current BTC price for market cap calculation",
    ),
):
    """
    Calculate NUPL (Net Unrealized Profit/Loss) Oscillator.

    NUPL = (Market Cap - Realized Cap) / Market Cap

    **Market Cycle Zones:**
    - **CAPITULATION** (< 0): Network underwater, extreme fear
    - **HOPE_FEAR** (0-0.25): Recovery phase
    - **OPTIMISM** (0.25-0.5): Bull market building
    - **BELIEF** (0.5-0.75): Strong conviction
    - **EUPHORIA** (> 0.75): Extreme greed, historically cycle tops

    **Use Cases:**
    - Identify market cycle phases
    - Detect overbought/oversold conditions
    - Compare with MVRV and other on-chain metrics

    Spec: 022-nupl-oscillator
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.nupl import calculate_nupl_signal

        result = calculate_nupl_signal(
            conn=conn,
            block_height=block_height,
            current_price_usd=current_price,
        )

        return NUPLResponse(
            nupl=result.nupl,
            zone=result.zone.value,
            market_cap_usd=result.market_cap_usd,
            realized_cap_usd=result.realized_cap_usd,
            unrealized_profit_usd=result.unrealized_profit_usd,
            pct_supply_in_profit=result.pct_supply_in_profit,
            confidence=result.confidence,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating NUPL: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-024: Revived Supply
# =============================================================================


class RevivedSupplyResponse(BaseModel):
    """Revived Supply response model (spec-024)."""

    revived_1y: float = Field(..., description="BTC revived after 1+ year dormancy")
    revived_2y: float = Field(..., description="BTC revived after 2+ year dormancy")
    revived_5y: float = Field(..., description="BTC revived after 5+ year dormancy")
    revived_total_usd: float = Field(
        ..., description="USD value of revived supply (1y threshold)"
    )
    revived_avg_age: float = Field(
        ..., description="Weighted average age of revived UTXOs (days)"
    )
    zone: str = Field(..., description="Behavioral zone: dormant|normal|elevated|spike")
    utxo_count: int = Field(..., description="Number of revived UTXOs")
    window_days: int = Field(..., description="Lookback window used")
    current_price_usd: float = Field(..., description="Current BTC price used")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")
    confidence: float = Field(..., description="Signal confidence (0-1)")


@app.get("/api/metrics/revived-supply", response_model=RevivedSupplyResponse)
async def get_revived_supply(
    window: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Lookback window in days for spent UTXOs",
    ),
):
    """
    Calculate Revived Supply metrics for dormant coin movement tracking.

    Tracks coins that have been dormant for fixed thresholds (1y, 2y, 5y)
    and are now being spent. Rising revived supply during rallies indicates
    LTH distribution.

    **Fixed Dormancy Thresholds:**
    - **revived_1y**: BTC dormant >= 365 days before spending
    - **revived_2y**: BTC dormant >= 730 days before spending
    - **revived_5y**: BTC dormant >= 1825 days before spending

    **Behavioral Zones (based on daily revived BTC):**
    - **DORMANT** (< 1000): Low LTH activity, stable holding
    - **NORMAL** (1000-5000): Baseline movement
    - **ELEVATED** (5000-10000): Increased LTH selling, watch closely
    - **SPIKE** (> 10000): Major distribution event, potential top signal

    **Key Signals:**
    - Rising revived supply during rally: LTH distributing (bearish)
    - Low revived supply during dip: LTH holding strong (bullish)
    - 5Y+ coins moving: Extremely rare, significant behavior shift

    Spec: 024-revived-supply
    """
    import duckdb
    from datetime import datetime

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        # Get current price (average of 1000 most recent spent UTXOs)
        price_result = conn.execute(
            """
            SELECT AVG(spent_price_usd)
            FROM (
                SELECT spent_price_usd
                FROM utxo_lifecycle_full
                WHERE is_spent = TRUE AND spent_price_usd > 0
                ORDER BY spent_timestamp DESC
                LIMIT 1000
            ) recent_spent
            """
        ).fetchone()
        current_price = (
            price_result[0] if price_result and price_result[0] else 100000.0
        )

        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        result = calculate_revived_supply_signal(
            conn=conn,
            current_block=block_height,
            current_price_usd=current_price,
            timestamp=datetime.utcnow(),
            window_days=window,
        )

        return RevivedSupplyResponse(
            revived_1y=result.revived_1y,
            revived_2y=result.revived_2y,
            revived_5y=result.revived_5y,
            revived_total_usd=result.revived_total_usd,
            revived_avg_age=result.revived_avg_age,
            zone=result.zone.value,
            utxo_count=result.utxo_count,
            window_days=result.window_days,
            current_price_usd=result.current_price_usd,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
            confidence=result.confidence,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating revived supply: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# spec-023: STH/LTH Cost Basis
# =============================================================================


class CostBasisResponse(BaseModel):
    """STH/LTH Cost Basis response model (spec-023)."""

    sth_cost_basis: float = Field(
        ..., description="STH weighted average cost basis (USD)"
    )
    lth_cost_basis: float = Field(
        ..., description="LTH weighted average cost basis (USD)"
    )
    total_cost_basis: float = Field(
        ..., description="Total weighted average cost basis (USD)"
    )
    sth_mvrv: float = Field(..., description="STH MVRV ratio (price/cost_basis)")
    lth_mvrv: float = Field(..., description="LTH MVRV ratio (price/cost_basis)")
    sth_supply_btc: float = Field(..., description="STH supply in BTC")
    lth_supply_btc: float = Field(..., description="LTH supply in BTC")
    current_price_usd: float = Field(..., description="Current BTC price used")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")
    confidence: float = Field(..., description="Signal confidence (0-1)")


@app.get("/api/metrics/cost-basis", response_model=CostBasisResponse)
async def get_cost_basis(
    current_price: float = Query(
        default=100000.0,
        ge=1.0,
        description="Current BTC price for MVRV calculation",
    ),
):
    """
    Calculate STH/LTH Cost Basis (weighted average acquisition price per cohort).

    Cost Basis = SUM(realized_value_usd) / SUM(btc_value)

    **Cohort Definitions:**
    - **STH (Short-Term Holders)**: UTXOs created < 155 days ago
    - **LTH (Long-Term Holders)**: UTXOs created >= 155 days ago

    **Signal Interpretation:**
    - Price < STH Cost Basis → STH underwater → capitulation risk
    - Price > LTH Cost Basis → LTH in profit → distribution risk
    - STH Cost Basis = key short-term support level
    - LTH Cost Basis = macro support level

    Spec: 023-cost-basis-cohorts
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.cost_basis import calculate_cost_basis_signal

        result = calculate_cost_basis_signal(
            conn=conn,
            current_block=block_height,
            current_price_usd=current_price,
        )

        return CostBasisResponse(
            sth_cost_basis=result.sth_cost_basis,
            lth_cost_basis=result.lth_cost_basis,
            total_cost_basis=result.total_cost_basis,
            sth_mvrv=result.sth_mvrv,
            lth_mvrv=result.lth_mvrv,
            sth_supply_btc=result.sth_supply_btc,
            lth_supply_btc=result.lth_supply_btc,
            current_price_usd=result.current_price_usd,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
            confidence=result.confidence,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Cost Basis: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Spec-025: Wallet Waves & Absorption Rates Endpoints
# =============================================================================


class WalletBandResponse(BaseModel):
    """Response model for a single wallet band metrics."""

    band: str = Field(
        ..., description="Wallet band name (shrimp, crab, fish, shark, whale, humpback)"
    )
    supply_btc: float = Field(
        ..., description="Total BTC held by addresses in this band"
    )
    supply_pct: float = Field(
        ..., description="Percentage of total supply in this band (0-100)"
    )
    address_count: int = Field(..., description="Number of addresses in this band")
    avg_balance: float = Field(
        ..., description="Average balance per address in this band"
    )


class WalletWavesResponse(BaseModel):
    """Response model for wallet waves distribution snapshot."""

    timestamp: str = Field(..., description="ISO timestamp of calculation")
    block_height: int = Field(..., description="Bitcoin block height at calculation")
    total_supply_btc: float = Field(
        ..., description="Total circulating supply (unspent)"
    )
    bands: List[WalletBandResponse] = Field(
        ..., description="List of 6 wallet band metrics"
    )
    retail_supply_pct: float = Field(
        ..., description="Combined percentage for bands 1-3 (shrimp+crab+fish)"
    )
    institutional_supply_pct: float = Field(
        ..., description="Combined percentage for bands 4-6 (shark+whale+humpback)"
    )
    address_count_total: int = Field(
        ..., description="Total number of addresses with balance > 0"
    )
    null_address_btc: float = Field(
        ..., description="BTC in UTXOs without decoded address"
    )
    confidence: float = Field(..., description="Data quality score (0.0-1.0)")


class AbsorptionBandResponse(BaseModel):
    """Response model for a single band absorption rate."""

    band: str = Field(..., description="Wallet band name")
    absorption_rate: Optional[float] = Field(
        None, description="Rate of new supply absorbed (None if no historical data)"
    )
    supply_delta_btc: float = Field(..., description="Change in BTC held over window")
    supply_start_btc: float = Field(..., description="BTC held at window start")
    supply_end_btc: float = Field(..., description="BTC held at window end")


class AbsorptionRatesResponse(BaseModel):
    """Response model for absorption rates across all wallet bands."""

    timestamp: str = Field(..., description="ISO timestamp of calculation")
    block_height: int = Field(..., description="Bitcoin block height at calculation")
    window_days: int = Field(..., description="Lookback window in days")
    mined_supply_btc: float = Field(..., description="New BTC mined during window")
    bands: List[AbsorptionBandResponse] = Field(
        ..., description="List of 6 absorption rate metrics"
    )
    dominant_absorber: str = Field(..., description="Band with highest absorption rate")
    retail_absorption: float = Field(
        ..., description="Combined absorption for bands 1-3"
    )
    institutional_absorption: float = Field(
        ..., description="Combined absorption for bands 4-6"
    )
    confidence: float = Field(..., description="Data quality score (0.0-1.0)")
    has_historical_data: bool = Field(
        ..., description="False if baseline snapshot unavailable"
    )


@app.get("/api/metrics/wallet-waves", response_model=WalletWavesResponse)
async def get_wallet_waves():
    """
    Get current wallet waves distribution (spec-025).

    Returns supply distribution across 6 wallet size bands:
    - **shrimp**: < 1 BTC (sub-retail, casual holders)
    - **crab**: 1-10 BTC (retail accumulation target)
    - **fish**: 10-100 BTC (high net worth individuals)
    - **shark**: 100-1,000 BTC (small institutions, funds)
    - **whale**: 1,000-10,000 BTC (major institutions)
    - **humpback**: > 10,000 BTC (exchanges, ETF custodians)

    **Retail vs Institutional:**
    - Retail = shrimp + crab + fish
    - Institutional = shark + whale + humpback

    Performance: <5s query time on ~50M unique addresses.

    Spec: 025-wallet-waves
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        from scripts.metrics.wallet_waves import calculate_wallet_waves

        result = calculate_wallet_waves(conn=conn)

        return WalletWavesResponse(
            timestamp=result.timestamp.isoformat(),
            block_height=result.block_height,
            total_supply_btc=result.total_supply_btc,
            bands=[
                WalletBandResponse(
                    band=b.band.value,
                    supply_btc=b.supply_btc,
                    supply_pct=b.supply_pct,
                    address_count=b.address_count,
                    avg_balance=b.avg_balance,
                )
                for b in result.bands
            ],
            retail_supply_pct=result.retail_supply_pct,
            institutional_supply_pct=result.institutional_supply_pct,
            address_count_total=result.address_count_total,
            null_address_btc=result.null_address_btc,
            confidence=result.confidence,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Wallet Waves: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/wallet-waves/history")
async def get_wallet_waves_history(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Days of history to return (max 365)",
    ),
):
    """
    Get historical wallet waves data (spec-025).

    Returns daily wallet waves snapshots for the specified period.

    Note: This endpoint requires pre-computed historical snapshots.
    Currently returns a placeholder response until snapshot storage is implemented.

    Spec: 025-wallet-waves
    """
    # MVP: Return current snapshot only (historical storage not implemented yet)
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        from scripts.metrics.wallet_waves import calculate_wallet_waves

        result = calculate_wallet_waves(conn=conn)

        # Return single snapshot as list (historical storage TBD)
        return [
            WalletWavesResponse(
                timestamp=result.timestamp.isoformat(),
                block_height=result.block_height,
                total_supply_btc=result.total_supply_btc,
                bands=[
                    WalletBandResponse(
                        band=b.band.value,
                        supply_btc=b.supply_btc,
                        supply_pct=b.supply_pct,
                        address_count=b.address_count,
                        avg_balance=b.avg_balance,
                    )
                    for b in result.bands
                ],
                retail_supply_pct=result.retail_supply_pct,
                institutional_supply_pct=result.institutional_supply_pct,
                address_count_total=result.address_count_total,
                null_address_btc=result.null_address_btc,
                confidence=result.confidence,
            )
        ]

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error calculating Wallet Waves history: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/metrics/absorption-rates", response_model=AbsorptionRatesResponse)
async def get_absorption_rates(
    window: str = Query(
        default="30d",
        description="Lookback window (7d, 30d, or 90d)",
        pattern="^(7d|30d|90d)$",
    ),
):
    """
    Get absorption rates by wallet band (spec-025).

    Returns the rate at which each wallet band absorbs newly mined supply.

    **Window Options:**
    - 7d: 7-day lookback (~3,150 BTC mined, post-2024 halving)
    - 30d: 30-day lookback (~13,500 BTC mined)
    - 90d: 90-day lookback (~40,500 BTC mined)

    **Absorption Rate Interpretation:**
    - Rate > 1.0: Band absorbed more than its share of new supply
    - Rate ~ 0: Band supply unchanged
    - Rate < 0: Band is distributing (reducing holdings)

    **Dominant Absorber:** Identifies which cohort is accumulating most aggressively.

    Note: Requires historical snapshot for comparison. Returns has_historical_data=false
    if baseline is unavailable (first run).

    Spec: 025-wallet-waves
    """
    import duckdb

    # Parse window parameter
    window_days = int(window.rstrip("d"))

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        from scripts.metrics.wallet_waves import calculate_wallet_waves
        from scripts.metrics.absorption_rates import calculate_absorption_rates

        # Calculate current snapshot
        current_snapshot = calculate_wallet_waves(conn=conn)

        # For MVP, we don't have historical snapshots stored
        # Future: Query stored snapshots from `window_days` ago
        historical_snapshot = None

        result = calculate_absorption_rates(
            conn=conn,
            current_snapshot=current_snapshot,
            historical_snapshot=historical_snapshot,
            window_days=window_days,
        )

        return AbsorptionRatesResponse(
            timestamp=result.timestamp.isoformat(),
            block_height=result.block_height,
            window_days=result.window_days,
            mined_supply_btc=result.mined_supply_btc,
            bands=[
                AbsorptionBandResponse(
                    band=b.band.value,
                    absorption_rate=b.absorption_rate,
                    supply_delta_btc=b.supply_delta_btc,
                    supply_start_btc=b.supply_start_btc,
                    supply_end_btc=b.supply_end_btc,
                )
                for b in result.bands
            ],
            dominant_absorber=result.dominant_absorber.value,
            retail_absorption=result.retail_absorption,
            institutional_absorption=result.institutional_absorption,
            confidence=result.confidence,
            has_historical_data=result.has_historical_data,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating Absorption Rates: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Exchange Netflow Response Models (spec-026)
# =============================================================================


class ExchangeNetflowResponse(BaseModel):
    """Exchange Netflow response model (spec-026)."""

    exchange_inflow: float = Field(..., description="BTC flowing into exchanges")
    exchange_outflow: float = Field(..., description="BTC flowing out of exchanges")
    netflow: float = Field(
        ...,
        description="Inflow - Outflow (positive = selling, negative = accumulation)",
    )
    netflow_7d_ma: float = Field(..., description="7-day moving average of netflow")
    netflow_30d_ma: float = Field(..., description="30-day moving average of netflow")
    zone: str = Field(
        ...,
        description="Behavioral zone: strong_outflow|weak_outflow|weak_inflow|strong_inflow",
    )
    window_hours: int = Field(..., description="Lookback window in hours")
    exchange_count: int = Field(..., description="Number of exchanges tracked")
    address_count: int = Field(..., description="Number of exchange addresses tracked")
    current_price_usd: float = Field(..., description="Current BTC price used")
    inflow_usd: float = Field(..., description="USD value of inflow")
    outflow_usd: float = Field(..., description="USD value of outflow")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")
    confidence: float = Field(..., description="Signal confidence (0-1)")


class NetflowHistoryEntry(BaseModel):
    """Daily netflow history entry."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    inflow: float = Field(..., description="Daily inflow BTC")
    outflow: float = Field(..., description="Daily outflow BTC")
    netflow: float = Field(..., description="Daily netflow BTC")


class ExchangeNetflowHistoryResponse(BaseModel):
    """Exchange Netflow history response."""

    days: int = Field(..., description="Number of days requested")
    data: list[NetflowHistoryEntry] = Field(..., description="Daily netflow data")


# =============================================================================
# Binary CDD Response Model (spec-027)
# =============================================================================


class BinaryCDDResponse(BaseModel):
    """Binary CDD response model (spec-027).

    Statistical significance flag for CDD events.
    Transforms noisy CDD data into actionable binary signals.
    """

    cdd_today: float = Field(..., description="Today's total CDD")
    cdd_mean: float = Field(..., description="Mean CDD over lookback window")
    cdd_std: float = Field(..., description="Std dev of CDD over window")
    cdd_zscore: Optional[float] = Field(
        None, description="Z-score (null if insufficient data)"
    )
    cdd_percentile: Optional[float] = Field(None, description="Percentile rank (0-100)")
    binary_cdd: int = Field(
        ..., ge=0, le=1, description="Binary flag (0=noise, 1=significant)"
    )
    threshold_used: float = Field(
        ..., ge=1.0, le=4.0, description="Sigma threshold applied"
    )
    window_days: int = Field(..., ge=30, le=730, description="Lookback window size")
    data_points: int = Field(..., gt=0, description="Available data points")
    insufficient_data: bool = Field(..., description="True if < 30 days history")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")


# =============================================================================
# Exchange Netflow Endpoints (spec-026)
# =============================================================================


# Exchange addresses CSV path
EXCHANGE_ADDRESSES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "exchange_addresses.csv",
)


@app.get("/api/metrics/exchange-netflow", response_model=ExchangeNetflowResponse)
async def get_exchange_netflow(
    window: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Lookback window in hours (1-168)",
    ),
):
    """
    Calculate Exchange Netflow metrics for capital flow tracking.

    Tracks BTC movement to/from known exchange addresses to identify
    selling pressure vs accumulation. Primary indicator for exchange
    deposit/withdrawal behavior.

    **Netflow Formula:** netflow = inflow - outflow
    - **Positive netflow**: BTC flowing into exchanges (selling pressure)
    - **Negative netflow**: BTC flowing out of exchanges (accumulation)

    **Behavioral Zones (based on daily netflow BTC):**
    - **STRONG_OUTFLOW** (< -1000): Heavy accumulation, bullish
    - **WEAK_OUTFLOW** (-1000 to 0): Mild accumulation, neutral-bullish
    - **WEAK_INFLOW** (0 to 1000): Mild selling, neutral-bearish
    - **STRONG_INFLOW** (> 1000): Heavy selling pressure, bearish

    **Key Signals:**
    - Rising 7d MA with positive netflow: Sustained selling
    - Falling 7d MA with negative netflow: Sustained accumulation
    - Strong outflow during dips: Smart money accumulating (bullish)
    - Strong inflow at tops: Distribution phase (bearish)

    **Confidence Rating:** 0.75 (B-C grade metric)
    - Limited to known public exchange addresses
    - Does not include all exchange addresses
    - Some addresses may be misattributed
    """
    import duckdb
    from datetime import datetime

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        # Get current price (average of 1000 most recent spent UTXOs)
        price_result = conn.execute(
            """
            SELECT AVG(spent_price_usd)
            FROM (
                SELECT spent_price_usd
                FROM utxo_lifecycle_full
                WHERE is_spent = TRUE AND spent_price_usd > 0
                ORDER BY spent_timestamp DESC
                LIMIT 1000
            ) recent_spent
            """
        ).fetchone()
        current_price = (
            price_result[0] if price_result and price_result[0] else 100000.0
        )

        from scripts.metrics.exchange_netflow import calculate_exchange_netflow

        result = calculate_exchange_netflow(
            conn=conn,
            window_hours=window,
            current_price_usd=current_price,
            block_height=block_height,
            timestamp=datetime.utcnow(),
            exchange_addresses_path=EXCHANGE_ADDRESSES_PATH,
        )

        return ExchangeNetflowResponse(
            exchange_inflow=result.exchange_inflow,
            exchange_outflow=result.exchange_outflow,
            netflow=result.netflow,
            netflow_7d_ma=result.netflow_7d_ma,
            netflow_30d_ma=result.netflow_30d_ma,
            zone=result.zone.value,
            window_hours=result.window_hours,
            exchange_count=result.exchange_count,
            address_count=result.address_count,
            current_price_usd=result.current_price_usd,
            inflow_usd=result.inflow_usd,
            outflow_usd=result.outflow_usd,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
            confidence=result.confidence,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating exchange netflow: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get(
    "/api/metrics/exchange-netflow/history",
    response_model=ExchangeNetflowHistoryResponse,
)
async def get_exchange_netflow_history(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of historical days to retrieve (1-365)",
    ),
):
    """
    Get historical daily exchange netflow data for charting.

    Returns daily inflow, outflow, and netflow for the specified period.
    Useful for trend analysis and visualization.

    **Response Fields:**
    - **date**: Date (YYYY-MM-DD)
    - **inflow**: Daily BTC inflow to exchanges
    - **outflow**: Daily BTC outflow from exchanges
    - **netflow**: Daily netflow (inflow - outflow)
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        from scripts.metrics.exchange_netflow import (
            load_exchange_addresses,
            get_daily_netflow_history,
        )

        # Load exchange addresses
        load_exchange_addresses(conn, EXCHANGE_ADDRESSES_PATH)

        # Get historical data
        history = get_daily_netflow_history(conn, days=days)

        return ExchangeNetflowHistoryResponse(
            days=days,
            data=[
                NetflowHistoryEntry(
                    date=entry["date"] or "",
                    inflow=entry["inflow"],
                    outflow=entry["outflow"],
                    netflow=entry["netflow"],
                )
                for entry in history
            ],
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error getting exchange netflow history: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Binary CDD Endpoint (spec-027)
# =============================================================================


@app.get("/api/metrics/binary-cdd", response_model=BinaryCDDResponse)
async def get_binary_cdd(
    threshold: float = Query(
        default=2.0,
        ge=1.0,
        le=4.0,
        description="Z-score threshold for binary flag (sigma)",
    ),
    window: int = Query(
        default=365,
        ge=30,
        le=730,
        description="Lookback window in days (30-730)",
    ),
):
    """
    Calculate Binary CDD (Coin Days Destroyed) indicator.

    Transforms noisy CDD data into actionable binary signals based on
    z-score threshold exceeding N-sigma. Filters out normal long-term
    holder activity.

    **Binary CDD Formula:**
    - z = (cdd_today - mean) / std
    - binary_cdd = 1 if z >= threshold, else 0

    **Signal Interpretation:**
    - **binary_cdd=0**: Normal LTH activity (noise)
    - **binary_cdd=1 (z >= 2σ)**: Significant event (97.5th percentile)
    - **binary_cdd=1 (z >= 3σ)**: Extreme event (99.9th percentile)

    **Thresholds:**
    - **1.0σ**: ~85th percentile (more sensitive)
    - **2.0σ**: ~97.5th percentile (default, balanced)
    - **3.0σ**: ~99.9th percentile (conservative, extreme only)
    - **4.0σ**: Very rare events only

    **Use Cases:**
    - Alert trigger for significant LTH movement
    - Filter for trading signals (only act on binary_cdd=1)
    - Combine with other metrics for confluence

    **Data Requirements:**
    - Minimum 30 days of UTXO lifecycle data
    - Returns insufficient_data=true if below threshold
    """
    import duckdb

    conn = None
    try:
        conn = duckdb.connect(UTXO_DB_PATH, read_only=True)

        # Get latest block height
        block_result = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        block_height = block_result[0] if block_result and block_result[0] else 0

        from scripts.metrics.binary_cdd import calculate_binary_cdd

        result = calculate_binary_cdd(
            conn=conn,
            block_height=block_height,
            threshold=threshold,
            window_days=window,
        )

        return BinaryCDDResponse(
            cdd_today=result.cdd_today,
            cdd_mean=result.cdd_mean,
            cdd_std=result.cdd_std,
            cdd_zscore=result.cdd_zscore,
            cdd_percentile=result.cdd_percentile,
            binary_cdd=result.binary_cdd,
            threshold_used=result.threshold_used,
            window_days=result.window_days,
            data_points=result.data_points,
            insufficient_data=result.insufficient_data,
            block_height=result.block_height,
            timestamp=result.timestamp.isoformat(),
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"UTXO lifecycle database not found at {UTXO_DB_PATH}. "
            "Run utxo_lifecycle sync first.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "utxo_lifecycle" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail="UTXO lifecycle table not found. Schema migration pending.",
            )
        logging.error(f"Error calculating binary CDD: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
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
        "spec": "003-mempool-integration-refactor, 004-whale-flow-detection, 005-mempool-whale-realtime, 006-whale-dashboard",
        "endpoints": {
            "latest": "/api/prices/latest",
            "historical": "/api/prices/historical?days=7",
            "comparison": "/api/prices/comparison?days=7",
            "whale_latest": "/api/whale/latest",
            "whale_dashboard": "/whale",
            "performance_monitor": "/monitor",
            "health": "/health",
            "metrics": "/metrics?window=60",
            "docs": "/docs",
        },
    }


# =============================================================================
# GET /whale - Whale Detection Dashboard (spec-006)
# =============================================================================


@app.get("/whale")
async def whale_dashboard():
    """
    Serve the whale detection dashboard HTML page.

    **Public Endpoint:** No authentication required

    Returns:
        HTML page with real-time whale transaction monitoring dashboard
    """
    dashboard_path = FRONTEND_DIR / "whale_dashboard.html"

    if not dashboard_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Whale dashboard not found. Please ensure frontend files are present.",
        )

    return FileResponse(
        path=str(dashboard_path),
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache",  # Always fetch latest version
            "X-Content-Type-Options": "nosniff",
        },
    )


# Alias: /dashboard -> /whale (for backward compatibility)
@app.get("/dashboard")
async def dashboard_alias():
    """Alias for /whale endpoint (backward compatibility)."""
    return await whale_dashboard()


# =============================================================================
# GET /monitor - Performance Monitor Dashboard (T095)
# =============================================================================


@app.get("/monitor")
async def performance_monitor():
    """
    Serve the performance monitoring dashboard HTML page.

    **Public Endpoint:** No authentication required

    Returns:
        HTML page with real-time API and system performance metrics
    """
    monitor_path = FRONTEND_DIR / "performance_monitor.html"

    if not monitor_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Performance monitor not found. Please ensure frontend files are present.",
        )

    return FileResponse(
        path=str(monitor_path),
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache",  # Always fetch latest version
            "X-Content-Type-Options": "nosniff",
        },
    )


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
