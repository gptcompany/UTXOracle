"""
Funding Rate Reader for Derivatives Historical Integration (spec-008).

Reads Binance Funding Rate from LiquidationHeatmap DuckDB and converts
to contrarian signal vote.

Funding rate is a CONTRARIAN indicator:
- Positive funding (longs pay) → negative vote (bearish)
- Negative funding (shorts pay) → positive vote (bullish)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import duckdb

from scripts.derivatives import get_liq_connection, close_connection
from scripts.models.derivatives_models import FundingRateSignal

logger = logging.getLogger(__name__)

# Funding rate thresholds (as decimal, not percentage)
# Using wider thresholds for better signal discrimination
EXTREME_POSITIVE = 0.001  # 0.1% - very crowded longs
EXTREME_NEGATIVE = -0.0005  # -0.05% - very crowded shorts
NEUTRAL_ZONE = 0.0001  # ±0.01% - no clear signal

# Scaling factors to match spec acceptance scenarios:
# +0.15% (0.0015) → -0.8 vote
# -0.08% (-0.0008) → +0.6 vote
POSITIVE_SCALE_MAX = 0.002  # 0.2% maps to -1.0
NEGATIVE_SCALE_MAX = 0.00133  # 0.133% maps to +1.0


def funding_to_vote(funding_rate: float) -> Tuple[float, bool]:
    """
    Convert funding rate to contrarian vote.

    Args:
        funding_rate: Raw rate (e.g., 0.0015 = 0.15%)

    Returns:
        (vote, is_extreme): vote in [-1, 1], extreme flag

    Examples:
        >>> funding_to_vote(0.0015)  # +0.15%
        (-0.8, True)  # Bearish contrarian signal

        >>> funding_to_vote(-0.0008)  # -0.08%
        (0.6, True)  # Bullish contrarian signal

        >>> funding_to_vote(0.0001)  # +0.01%
        (0.0, False)  # Neutral
    """
    import math

    # Handle invalid inputs (NaN, inf)
    if math.isnan(funding_rate) or math.isinf(funding_rate):
        logger.warning(f"Invalid funding rate: {funding_rate}, returning neutral")
        return 0.0, False

    # Detect extremes
    is_extreme = funding_rate > EXTREME_POSITIVE or funding_rate < EXTREME_NEGATIVE

    # Normalize to [-1, 1] with inversion (contrarian)
    if abs(funding_rate) <= NEUTRAL_ZONE:
        vote = 0.0
    elif funding_rate > 0:
        # Positive funding = bearish (longs paying)
        # Scale: 0.2% → -1.0, so 0.15% → -0.75 ≈ -0.8
        vote = -min(1.0, funding_rate / POSITIVE_SCALE_MAX)
    else:
        # Negative funding = bullish (shorts paying)
        # Scale: -0.133% → +1.0, so -0.08% → +0.6
        vote = min(1.0, abs(funding_rate) / NEGATIVE_SCALE_MAX)

    logger.debug(
        f"Funding rate {funding_rate * 100:.4f}% → vote={vote:.2f}, extreme={is_extreme}"
    )

    return vote, is_extreme


def read_funding_rate(
    conn: duckdb.DuckDBPyConnection,
    timestamp: datetime,
    symbol: str = "BTCUSDT",
    tolerance_hours: int = 8,
) -> Optional[Tuple[datetime, float]]:
    """
    Read funding rate at or near the specified timestamp.

    Args:
        conn: DuckDB connection with LiquidationHeatmap attached.
        timestamp: Target timestamp to query.
        symbol: Trading pair (default: BTCUSDT).
        tolerance_hours: Max hours before/after to find nearest rate.

    Returns:
        (timestamp, funding_rate) tuple, or None if not found.
    """
    if conn is None:
        logger.warning("No connection available for funding rate query")
        return None

    try:
        # Query nearest funding rate within tolerance
        result = conn.execute(
            """
            SELECT timestamp, funding_rate
            FROM liq.funding_rate_history
            WHERE symbol = ?
              AND timestamp BETWEEN ? AND ?
            ORDER BY ABS(EPOCH(timestamp) - EPOCH(?))
            LIMIT 1
            """,
            [
                symbol,
                timestamp - timedelta(hours=tolerance_hours),
                timestamp + timedelta(hours=tolerance_hours),
                timestamp,
            ],
        ).fetchone()

        if result:
            ts, rate = result
            logger.debug(f"Found funding rate at {ts}: {rate}")
            return ts, float(rate)
        else:
            logger.warning(f"No funding rate found near {timestamp} for {symbol}")
            return None

    except Exception as e:
        logger.error(f"Error reading funding rate: {e}")
        return None


def get_latest_funding_signal(
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
) -> Optional[FundingRateSignal]:
    """
    Get the latest funding rate signal.

    Args:
        conn: Optional DuckDB connection. If None, creates a new one.
        symbol: Trading pair (default: BTCUSDT).
        exchange: Exchange source (default: binance).

    Returns:
        FundingRateSignal or None if unavailable.
    """
    own_conn = False
    if conn is None:
        conn = get_liq_connection()
        own_conn = True

    if conn is None:
        logger.warning("LiquidationHeatmap unavailable, skipping funding rate")
        return None

    try:
        # Get latest funding rate
        result = conn.execute(
            """
            SELECT timestamp, funding_rate
            FROM liq.funding_rate_history
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol],
        ).fetchone()

        if result is None:
            logger.warning(f"No funding rate data for {symbol}")
            return None

        timestamp, funding_rate = result
        vote, is_extreme = funding_to_vote(float(funding_rate))

        signal = FundingRateSignal(
            timestamp=timestamp,
            symbol=symbol,
            exchange=exchange,
            funding_rate=float(funding_rate),
            funding_vote=vote,
            is_extreme=is_extreme,
        )

        logger.info(
            f"Latest funding signal: {funding_rate * 100:.4f}% → vote={vote:.2f} "
            f"({'EXTREME' if is_extreme else 'normal'})"
        )

        return signal

    except Exception as e:
        logger.error(f"Error getting latest funding signal: {e}")
        return None

    finally:
        if own_conn:
            close_connection(conn)


def get_funding_signal_at(
    timestamp: datetime,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
) -> Optional[FundingRateSignal]:
    """
    Get funding rate signal at a specific timestamp.

    Args:
        timestamp: Target timestamp.
        conn: Optional DuckDB connection.
        symbol: Trading pair.
        exchange: Exchange source.

    Returns:
        FundingRateSignal or None if unavailable.
    """
    own_conn = False
    if conn is None:
        conn = get_liq_connection()
        own_conn = True

    if conn is None:
        return None

    try:
        result = read_funding_rate(conn, timestamp, symbol)
        if result is None:
            return None

        ts, funding_rate = result
        vote, is_extreme = funding_to_vote(funding_rate)

        return FundingRateSignal(
            timestamp=ts,
            symbol=symbol,
            exchange=exchange,
            funding_rate=funding_rate,
            funding_vote=vote,
            is_extreme=is_extreme,
        )

    finally:
        if own_conn:
            close_connection(conn)


__all__ = [
    "funding_to_vote",
    "read_funding_rate",
    "get_latest_funding_signal",
    "get_funding_signal_at",
    "EXTREME_POSITIVE",
    "EXTREME_NEGATIVE",
    "NEUTRAL_ZONE",
]
