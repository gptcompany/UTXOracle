"""
Exchange Netflow Module (spec-026).

Tracks BTC movement to/from known exchange addresses to identify selling pressure
vs accumulation. Primary indicator for exchange deposit/withdrawal behavior.

Key Signals:
- Positive netflow: BTC flowing into exchanges (selling pressure)
- Negative netflow: BTC flowing out of exchanges (accumulation)
- Rising 7d MA with positive netflow: Sustained selling
- Falling 7d MA with negative netflow: Sustained accumulation

Zone Classification:
- STRONG_OUTFLOW: < -1000 BTC/day (heavy accumulation, bullish)
- WEAK_OUTFLOW: -1000 to 0 (mild accumulation, neutral-bullish)
- WEAK_INFLOW: 0 to 1000 (mild selling, neutral-bearish)
- STRONG_INFLOW: > 1000 BTC/day (heavy selling pressure, bearish)

Usage:
    from scripts.metrics.exchange_netflow import (
        calculate_exchange_netflow,
        classify_netflow_zone,
        load_exchange_addresses,
    )

    addresses = load_exchange_addresses(conn, "data/exchange_addresses.csv")
    result = calculate_exchange_netflow(conn, window_hours=24, ...)
    print(f"Netflow: {result.netflow:.2f} BTC, Zone: {result.zone.value}")
"""

import csv
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import duckdb

from scripts.models.metrics_models import NetflowZone, ExchangeNetflowResult

logger = logging.getLogger(__name__)

# Zone thresholds in BTC/day
ZONE_THRESHOLD_STRONG_OUTFLOW = -1000.0  # < -1000 = STRONG_OUTFLOW
ZONE_THRESHOLD_NEUTRAL = 0.0  # < 0 = WEAK_OUTFLOW, >= 0 = WEAK_INFLOW
ZONE_THRESHOLD_STRONG_INFLOW = 1000.0  # >= 1000 = STRONG_INFLOW


def classify_netflow_zone(netflow_btc_per_day: float) -> NetflowZone:
    """Classify netflow into behavioral zone.

    Zone boundaries based on exchange flow analysis:
    - STRONG_OUTFLOW: < -1000 BTC/day (heavy accumulation, bullish)
    - WEAK_OUTFLOW: -1000 to 0 (mild accumulation, neutral-bullish)
    - WEAK_INFLOW: 0 to 1000 (mild selling, neutral-bearish)
    - STRONG_INFLOW: >= 1000 BTC/day (heavy selling pressure, bearish)

    Args:
        netflow_btc_per_day: Daily netflow (inflow - outflow).
            Positive = selling pressure, negative = accumulation.

    Returns:
        NetflowZone enum member.

    Raises:
        ValueError: If netflow_btc_per_day is NaN or infinite.
    """
    if math.isnan(netflow_btc_per_day) or math.isinf(netflow_btc_per_day):
        raise ValueError(
            f"netflow_btc_per_day must be finite, got {netflow_btc_per_day}"
        )

    if netflow_btc_per_day < ZONE_THRESHOLD_STRONG_OUTFLOW:
        return NetflowZone.STRONG_OUTFLOW
    elif netflow_btc_per_day < ZONE_THRESHOLD_NEUTRAL:
        return NetflowZone.WEAK_OUTFLOW
    elif netflow_btc_per_day < ZONE_THRESHOLD_STRONG_INFLOW:
        return NetflowZone.WEAK_INFLOW
    else:
        return NetflowZone.STRONG_INFLOW


def load_exchange_addresses(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
) -> dict[str, dict]:
    """Load exchange addresses from CSV into DuckDB table.

    Creates or replaces the exchange_addresses table and returns a dict
    mapping address -> {exchange_name, type}.

    Args:
        conn: DuckDB connection.
        csv_path: Path to CSV file with columns: exchange_name, address, type.

    Returns:
        Dict mapping address -> {exchange_name, type}.
        Returns empty dict if file not found.
    """
    path = Path(csv_path)
    if not path.exists():
        logger.warning("Exchange addresses file not found: %s", csv_path)
        return {}

    try:
        # Read CSV and create lookup table
        addresses = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                addresses[row["address"]] = {
                    "exchange_name": row["exchange_name"],
                    "type": row["type"],
                }

        # Validate minimum address count
        if len(addresses) < 1000:
            logger.warning(
                "Low exchange address count: %d (expected >1000). "
                "Run: python -m scripts.bootstrap.scrape_exchange_addresses",
                len(addresses),
            )

        # Create/replace DuckDB table with bulk COPY
        conn.execute(
            """
            CREATE OR REPLACE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )

        # Bulk insert using COPY (much faster for 13K+ rows)
        conn.execute(f"COPY exchange_addresses FROM '{path}' (HEADER, DELIMITER ',')")

        # Log exchange distribution
        exchange_counts = conn.execute(
            "SELECT exchange_name, COUNT(*) FROM exchange_addresses GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
        ).fetchall()
        top_exchanges = ", ".join(f"{ex}: {cnt}" for ex, cnt in exchange_counts)
        logger.info(
            "Loaded %d exchange addresses from %s (top: %s)",
            len(addresses),
            csv_path,
            top_exchanges,
        )
        return addresses

    except Exception as e:
        logger.error("Error loading exchange addresses: %s", e)
        return {}


def calculate_exchange_inflow(
    conn: duckdb.DuckDBPyConnection,
    window_start_timestamp: int,
) -> float:
    """Calculate exchange inflow (BTC received by exchanges).

    Inflow = UTXOs created at exchange addresses within the window.
    When someone sends BTC to an exchange, a UTXO is created at an exchange address.

    Args:
        conn: DuckDB connection with utxo_lifecycle_full and exchange_addresses.
        window_start_timestamp: Unix timestamp for window start.

    Returns:
        Total BTC inflow within the window.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(u.btc_value), 0) AS inflow
        FROM utxo_lifecycle_full u
        JOIN exchange_addresses e ON u.address = e.address
        WHERE u.creation_timestamp >= ?
        """,
        [window_start_timestamp],
    ).fetchone()

    return float(result[0]) if result else 0.0


def calculate_exchange_outflow(
    conn: duckdb.DuckDBPyConnection,
    window_start_timestamp: int,
) -> float:
    """Calculate exchange outflow (BTC sent from exchanges).

    Outflow = UTXOs spent from exchange addresses within the window.
    When an exchange sends BTC out, it spends UTXOs from its addresses.

    Args:
        conn: DuckDB connection with utxo_lifecycle_full and exchange_addresses.
        window_start_timestamp: Unix timestamp for window start.

    Returns:
        Total BTC outflow within the window.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(u.btc_value), 0) AS outflow
        FROM utxo_lifecycle_full u
        JOIN exchange_addresses e ON u.address = e.address
        WHERE u.is_spent = TRUE
          AND u.spent_timestamp >= ?
        """,
        [window_start_timestamp],
    ).fetchone()

    return float(result[0]) if result else 0.0


def calculate_moving_average(daily_values: list[float], window: int) -> float:
    """Calculate simple moving average using the FIRST N values.

    Args:
        daily_values: List of daily values (expected newest-first from history query).
        window: Window size for moving average.

    Returns:
        Moving average of the first `window` values (most recent days).
        Returns 0.0 if no data.
    """
    if not daily_values:
        return 0.0

    if len(daily_values) < window:
        return sum(daily_values) / len(daily_values)

    # Use first N values (newest days when data is ordered DESC)
    return sum(daily_values[:window]) / window


def get_daily_netflow_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 30,
) -> list[dict]:
    """Get daily netflow history for charting.

    Args:
        conn: DuckDB connection with utxo_lifecycle_full and exchange_addresses.
        days: Number of historical days to retrieve.

    Returns:
        List of dicts with {date, netflow, inflow, outflow} for each day.
    """
    # Get daily aggregates
    result = conn.execute(
        """
        WITH daily_inflow AS (
            SELECT
                DATE(TO_TIMESTAMP(u.creation_timestamp)) AS day,
                COALESCE(SUM(u.btc_value), 0) AS inflow
            FROM utxo_lifecycle_full u
            JOIN exchange_addresses e ON u.address = e.address
            WHERE u.creation_timestamp >= EPOCH(NOW()) - ? * 86400
            GROUP BY DATE(TO_TIMESTAMP(u.creation_timestamp))
        ),
        daily_outflow AS (
            SELECT
                DATE(TO_TIMESTAMP(u.spent_timestamp)) AS day,
                COALESCE(SUM(u.btc_value), 0) AS outflow
            FROM utxo_lifecycle_full u
            JOIN exchange_addresses e ON u.address = e.address
            WHERE u.is_spent = TRUE
              AND u.spent_timestamp >= EPOCH(NOW()) - ? * 86400
            GROUP BY DATE(TO_TIMESTAMP(u.spent_timestamp))
        )
        SELECT
            COALESCE(i.day, o.day) AS day,
            COALESCE(i.inflow, 0) AS inflow,
            COALESCE(o.outflow, 0) AS outflow,
            COALESCE(i.inflow, 0) - COALESCE(o.outflow, 0) AS netflow
        FROM daily_inflow i
        FULL OUTER JOIN daily_outflow o ON i.day = o.day
        ORDER BY day DESC
        LIMIT ?
        """,
        [days, days, days],
    ).fetchall()

    history = []
    for row in result:
        history.append(
            {
                "date": str(row[0]) if row[0] else None,
                "inflow": float(row[1]),
                "outflow": float(row[2]),
                "netflow": float(row[3]),
            }
        )

    return history


def calculate_exchange_netflow(
    conn: duckdb.DuckDBPyConnection,
    window_hours: int = 24,
    current_price_usd: float = 0.0,
    block_height: int = 0,
    timestamp: Optional[datetime] = None,
    exchange_addresses_path: Optional[str] = None,
) -> ExchangeNetflowResult:
    """Calculate exchange netflow metrics.

    Queries UTXOs at exchange addresses to calculate:
    - exchange_inflow: BTC received by exchanges (sell pressure)
    - exchange_outflow: BTC sent from exchanges (accumulation)
    - netflow: inflow - outflow (positive = selling, negative = accumulation)
    - netflow_7d_ma: 7-day moving average of daily netflow
    - netflow_30d_ma: 30-day moving average of daily netflow

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        window_hours: Lookback window in hours (default 24).
        current_price_usd: Current BTC price for USD calculations.
        block_height: Current block height.
        timestamp: Optional timestamp (defaults to now).
        exchange_addresses_path: Path to CSV file with exchange addresses.
            If None, assumes exchange_addresses table already exists.

    Returns:
        ExchangeNetflowResult with zone classification.
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    logger.debug(
        "Calculating exchange netflow for block %d, window %d hours",
        block_height,
        window_hours,
    )

    # Load exchange addresses if path provided
    if exchange_addresses_path:
        load_exchange_addresses(conn, exchange_addresses_path)

    # Check if exchange_addresses table exists
    table_check = conn.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'exchange_addresses'
        """
    ).fetchone()

    if not table_check or table_check[0] == 0:
        logger.warning("exchange_addresses table not found")
        return _empty_result(window_hours, current_price_usd, block_height, timestamp)

    # Get exchange count and address count
    counts = conn.execute(
        """
        SELECT
            COUNT(DISTINCT exchange_name) AS exchange_count,
            COUNT(*) AS address_count
        FROM exchange_addresses
        """
    ).fetchone()

    exchange_count = int(counts[0]) if counts else 0
    address_count = int(counts[1]) if counts else 0

    if address_count == 0:
        logger.warning("No exchange addresses loaded")
        return _empty_result(window_hours, current_price_usd, block_height, timestamp)

    # Calculate window start timestamp
    window_start = int((timestamp - timedelta(hours=window_hours)).timestamp())

    # Calculate inflow and outflow
    inflow = calculate_exchange_inflow(conn, window_start)
    outflow = calculate_exchange_outflow(conn, window_start)
    netflow = inflow - outflow

    logger.debug(
        "Exchange netflow: inflow=%.2f, outflow=%.2f, netflow=%.2f",
        inflow,
        outflow,
        netflow,
    )

    # Get historical data for moving averages
    history = get_daily_netflow_history(conn, days=30)
    daily_netflows = [h["netflow"] for h in history]

    # Calculate moving averages
    netflow_7d_ma = calculate_moving_average(daily_netflows, window=7)
    netflow_30d_ma = calculate_moving_average(daily_netflows, window=30)

    # Classify zone based on daily rate
    # Convert to daily if window is not 24h
    daily_netflow = netflow * (24 / window_hours) if window_hours > 0 else 0.0
    zone = classify_netflow_zone(daily_netflow)

    # Calculate USD values
    inflow_usd = inflow * current_price_usd
    outflow_usd = outflow * current_price_usd

    # Determine confidence based on data quality
    if inflow == 0 and outflow == 0:
        confidence = 0.0  # No activity in window
    elif address_count < 5:
        confidence = 0.5  # Low address coverage
    else:
        confidence = 0.75  # B-C grade metric (limited address coverage)

    result = ExchangeNetflowResult(
        exchange_inflow=inflow,
        exchange_outflow=outflow,
        netflow=netflow,
        netflow_7d_ma=netflow_7d_ma,
        netflow_30d_ma=netflow_30d_ma,
        zone=zone,
        window_hours=window_hours,
        exchange_count=exchange_count,
        address_count=address_count,
        current_price_usd=current_price_usd,
        inflow_usd=inflow_usd,
        outflow_usd=outflow_usd,
        block_height=block_height,
        timestamp=timestamp,
        confidence=confidence,
    )

    logger.info(
        "Exchange netflow: inflow=%.2f, outflow=%.2f, netflow=%.2f BTC, "
        "zone=%s, 7d_ma=%.2f, confidence=%.2f",
        inflow,
        outflow,
        netflow,
        zone.value,
        netflow_7d_ma,
        confidence,
    )

    return result


def _empty_result(
    window_hours: int,
    current_price_usd: float,
    block_height: int,
    timestamp: datetime,
) -> ExchangeNetflowResult:
    """Create an empty result for edge cases."""
    return ExchangeNetflowResult(
        exchange_inflow=0.0,
        exchange_outflow=0.0,
        netflow=0.0,
        netflow_7d_ma=0.0,
        netflow_30d_ma=0.0,
        zone=NetflowZone.WEAK_INFLOW,
        window_hours=window_hours,
        exchange_count=0,
        address_count=0,
        current_price_usd=current_price_usd,
        inflow_usd=0.0,
        outflow_usd=0.0,
        block_height=block_height,
        timestamp=timestamp,
        confidence=0.0,
    )
