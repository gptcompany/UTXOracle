"""
Derivatives Historical Integration Module (spec-008).

Provides integration with LiquidationHeatmap DuckDB for:
- Funding Rate signals (contrarian indicator)
- Open Interest signals (leverage context)
- Enhanced 4-component Monte Carlo fusion

Uses DuckDB ATTACH for zero-copy cross-database queries.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)

# Configuration from environment
DEFAULT_LIQ_DB_PATH = (
    "/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb"
)
LIQ_DB_PATH = os.getenv("LIQUIDATION_HEATMAP_DB_PATH", DEFAULT_LIQ_DB_PATH)
DERIVATIVES_ENABLED = os.getenv("DERIVATIVES_ENABLED", "true").lower() == "true"

# Retry configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 0.5  # seconds


class DerivativesConnectionError(Exception):
    """Raised when LiquidationHeatmap database is unavailable."""

    pass


def get_liq_connection(
    db_path: Optional[str] = None, max_retries: int = MAX_RETRIES
) -> Optional[duckdb.DuckDBPyConnection]:
    """
    Get a connection to LiquidationHeatmap DuckDB with READ_ONLY ATTACH.

    Uses exponential backoff retry (max 3 attempts) for lock contention.

    Args:
        db_path: Optional path override. Defaults to LIQUIDATION_HEATMAP_DB_PATH env var.
        max_retries: Maximum number of connection attempts.

    Returns:
        DuckDB connection with LiquidationHeatmap attached as 'liq', or None if unavailable.
    """
    if not DERIVATIVES_ENABLED:
        logger.info("Derivatives integration disabled via DERIVATIVES_ENABLED=false")
        return None

    path = db_path or LIQ_DB_PATH
    if not Path(path).exists():
        logger.warning(f"LiquidationHeatmap database not found: {path}")
        return None

    last_error = None
    for attempt in range(max_retries):
        try:
            conn = duckdb.connect()
            conn.execute(f"ATTACH '{path}' AS liq (READ_ONLY)")
            logger.debug(f"Connected to LiquidationHeatmap (attempt {attempt + 1})")
            return conn
        except duckdb.IOException as e:
            last_error = e
            if "lock" in str(e).lower() and attempt < max_retries - 1:
                delay = BASE_RETRY_DELAY * (2**attempt)
                logger.warning(
                    f"LiquidationHeatmap locked, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                logger.error(f"Failed to connect to LiquidationHeatmap: {e}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error connecting to LiquidationHeatmap: {e}")
            return None

    logger.error(f"Max retries exceeded for LiquidationHeatmap: {last_error}")
    return None


def check_data_freshness(conn: duckdb.DuckDBPyConnection) -> dict:
    """
    Check the freshness of derivatives data in LiquidationHeatmap.

    Args:
        conn: DuckDB connection with LiquidationHeatmap attached.

    Returns:
        Dictionary with freshness info:
        - funding_latest: Latest funding rate timestamp
        - oi_latest: Latest OI timestamp
        - funding_age_hours: Age of funding data in hours
        - oi_age_minutes: Age of OI data in minutes
        - is_stale: True if data is older than threshold
    """
    from datetime import datetime, timezone

    result = {
        "funding_latest": None,
        "oi_latest": None,
        "funding_age_hours": None,
        "oi_age_minutes": None,
        "is_stale": True,
    }

    try:
        # Get latest funding rate timestamp
        funding_result = conn.execute(
            """
            SELECT MAX(timestamp) as latest
            FROM liq.funding_rate_history
            WHERE symbol = 'BTCUSDT'
            """
        ).fetchone()

        if funding_result and funding_result[0]:
            result["funding_latest"] = funding_result[0]
            age = datetime.now(timezone.utc) - funding_result[0].replace(
                tzinfo=timezone.utc
            )
            result["funding_age_hours"] = age.total_seconds() / 3600

        # Get latest OI timestamp
        oi_result = conn.execute(
            """
            SELECT MAX(timestamp) as latest
            FROM liq.open_interest_history
            WHERE symbol = 'BTCUSDT'
            """
        ).fetchone()

        if oi_result and oi_result[0]:
            result["oi_latest"] = oi_result[0]
            age = datetime.now(timezone.utc) - oi_result[0].replace(tzinfo=timezone.utc)
            result["oi_age_minutes"] = age.total_seconds() / 60

        # Consider stale if OI is older than 1 hour or funding older than 24 hours
        result["is_stale"] = (
            result["oi_age_minutes"] is None
            or result["oi_age_minutes"] > 60
            or result["funding_age_hours"] is None
            or result["funding_age_hours"] > 24
        )

        if result["is_stale"]:
            logger.warning(
                f"Derivatives data is stale: "
                f"funding={result['funding_age_hours']:.1f}h, "
                f"OI={result['oi_age_minutes']:.1f}min"
                if result["oi_age_minutes"]
                else "OI data missing"
            )
        else:
            logger.info(
                f"Derivatives data fresh: "
                f"funding={result['funding_age_hours']:.1f}h ago, "
                f"OI={result['oi_age_minutes']:.1f}min ago"
            )

    except Exception as e:
        logger.error(f"Error checking data freshness: {e}")

    return result


def close_connection(conn: Optional[duckdb.DuckDBPyConnection]) -> None:
    """Safely close a DuckDB connection."""
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")


__all__ = [
    "get_liq_connection",
    "check_data_freshness",
    "close_connection",
    "DerivativesConnectionError",
    "DERIVATIVES_ENABLED",
    "LIQ_DB_PATH",
]
