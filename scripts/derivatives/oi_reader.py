"""
Open Interest Reader for Derivatives Historical Integration (spec-008).

Reads Open Interest from LiquidationHeatmap DuckDB and converts to
context-aware signal based on whale direction.

OI is a CONTEXT-AWARE indicator:
- Rising OI + accumulation → confirming (bullish)
- Rising OI + distribution → diverging (bearish, potential squeeze)
- Falling OI → deleveraging (neutral)
"""

import logging
from datetime import datetime, timedelta
from typing import Literal, Optional, Tuple

import duckdb

from scripts.derivatives import get_liq_connection, close_connection
from scripts.models.derivatives_models import OpenInterestSignal

logger = logging.getLogger(__name__)

# OI change thresholds
SIGNIFICANT_CHANGE = 0.02  # 2% - meaningful change
DELEVERAGE_THRESHOLD = -0.01  # -1% - considered deleveraging
NEUTRAL_ZONE = 0.01  # ±1% - no clear signal

# Scaling factors for vote calculation
MAX_OI_CHANGE = 0.10  # 10% change maps to full vote


def calculate_oi_change(current_oi: float, previous_oi: float) -> float:
    """
    Calculate OI percentage change.

    Args:
        current_oi: Current OI value in USD.
        previous_oi: Previous OI value in USD.

    Returns:
        Percentage change as decimal (0.05 = 5%).
    """
    import math

    # Handle invalid inputs (NaN, inf, zero/negative previous)
    if (
        math.isnan(current_oi)
        or math.isnan(previous_oi)
        or math.isinf(current_oi)
        or math.isinf(previous_oi)
        or previous_oi <= 0
    ):
        return 0.0
    return (current_oi - previous_oi) / previous_oi


def oi_to_vote(
    oi_change: float, whale_direction: str
) -> Tuple[float, Literal["confirming", "diverging", "deleveraging", "neutral"]]:
    """
    Convert OI change to context-aware vote.

    Args:
        oi_change: OI percentage change (e.g., 0.05 = +5%).
        whale_direction: Whale signal direction ("ACCUMULATION", "DISTRIBUTION", "NEUTRAL").

    Returns:
        (vote, context): vote in [-1, 1], context string.

    Examples:
        >>> oi_to_vote(0.05, "ACCUMULATION")
        (0.5, "confirming")  # Rising OI + accumulation = bullish

        >>> oi_to_vote(0.05, "DISTRIBUTION")
        (-0.3, "diverging")  # Rising OI + distribution = potential squeeze

        >>> oi_to_vote(-0.03, "ACCUMULATION")
        (0.0, "deleveraging")  # Falling OI = neutral
    """
    import math

    # Handle invalid inputs (NaN, inf)
    if math.isnan(oi_change) or math.isinf(oi_change):
        logger.warning(f"Invalid OI change: {oi_change}, returning neutral")
        return 0.0, "neutral"

    # Falling OI = deleveraging (always neutral)
    if oi_change < DELEVERAGE_THRESHOLD:
        logger.debug(f"OI change {oi_change * 100:.2f}% → deleveraging")
        return 0.0, "deleveraging"

    # Neutral zone
    if abs(oi_change) < NEUTRAL_ZONE:
        logger.debug(f"OI change {oi_change * 100:.2f}% → neutral")
        return 0.0, "neutral"

    # Rising OI - context matters
    if oi_change >= SIGNIFICANT_CHANGE:
        # Scale: 5% change = 0.5 normalized, 10% = 1.0
        normalized_change = min(1.0, oi_change / MAX_OI_CHANGE)

        if whale_direction == "ACCUMULATION":
            # Rising OI + accumulation = confirming (bullish)
            # 5% OI change → 0.5 vote (direct mapping)
            vote = normalized_change
            logger.debug(
                f"OI +{oi_change * 100:.2f}% + ACCUMULATION → vote={vote:.2f} (confirming)"
            )
            return vote, "confirming"

        elif whale_direction == "DISTRIBUTION":
            # Rising OI + distribution = diverging (potential squeeze, bearish)
            # 5% OI change → -0.3 vote (scaled down)
            vote = -normalized_change * 0.6  # 0.5 * 0.6 = 0.3
            logger.debug(
                f"OI +{oi_change * 100:.2f}% + DISTRIBUTION → vote={vote:.2f} (diverging)"
            )
            return vote, "diverging"

        else:  # NEUTRAL
            # Rising OI + neutral whale = slight bullish bias
            vote = normalized_change * 0.2
            logger.debug(
                f"OI +{oi_change * 100:.2f}% + NEUTRAL → vote={vote:.2f} (neutral)"
            )
            return vote, "neutral"

    # Moderate change (1-2%), not significant enough
    logger.debug(f"OI change {oi_change * 100:.2f}% → neutral (moderate)")
    return 0.0, "neutral"


def read_oi_at_timestamp(
    conn: duckdb.DuckDBPyConnection,
    timestamp: datetime,
    symbol: str = "BTCUSDT",
    window_hours: int = 1,
) -> Optional[Tuple[datetime, float, float]]:
    """
    Read OI at a specific timestamp and calculate change from window_hours ago.

    Args:
        conn: DuckDB connection with LiquidationHeatmap attached.
        timestamp: Target timestamp to query.
        symbol: Trading pair (default: BTCUSDT).
        window_hours: Hours ago for change calculation.

    Returns:
        (timestamp, current_oi, previous_oi) tuple, or None if not found.
    """
    if conn is None:
        logger.warning("No connection available for OI query")
        return None

    try:
        # Get current OI
        current_result = conn.execute(
            """
            SELECT timestamp, open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, timestamp],
        ).fetchone()

        if current_result is None:
            logger.warning(f"No OI data found at or before {timestamp}")
            return None

        current_ts, current_oi = current_result

        # Get previous OI (window_hours ago)
        previous_result = conn.execute(
            """
            SELECT timestamp, open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, timestamp - timedelta(hours=window_hours)],
        ).fetchone()

        if previous_result is None:
            logger.warning(f"No previous OI data found for {window_hours}h window")
            # Return current OI with 0 previous (will result in 0% change)
            return current_ts, float(current_oi), 0.0

        _, previous_oi = previous_result

        logger.debug(
            f"OI at {current_ts}: {current_oi:,.0f} USD, "
            f"{window_hours}h ago: {previous_oi:,.0f} USD"
        )

        return current_ts, float(current_oi), float(previous_oi)

    except Exception as e:
        logger.error(f"Error reading OI: {e}")
        return None


def get_latest_oi_signal(
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    whale_direction: str = "NEUTRAL",
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
    window_hours: int = 1,
) -> Optional[OpenInterestSignal]:
    """
    Get the latest open interest signal.

    Args:
        conn: Optional DuckDB connection. If None, creates a new one.
        whale_direction: Current whale signal direction.
        symbol: Trading pair (default: BTCUSDT).
        exchange: Exchange source (default: binance).
        window_hours: Hours for change calculation.

    Returns:
        OpenInterestSignal or None if unavailable.
    """
    own_conn = False
    if conn is None:
        conn = get_liq_connection()
        own_conn = True

    if conn is None:
        logger.warning("LiquidationHeatmap unavailable, skipping OI")
        return None

    try:
        # Get latest OI data
        result = conn.execute(
            """
            SELECT timestamp, open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol],
        ).fetchone()

        if result is None:
            logger.warning(f"No OI data for {symbol}")
            return None

        current_ts, current_oi = result

        # Get OI from window_hours ago
        previous_result = conn.execute(
            """
            SELECT open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, current_ts - timedelta(hours=window_hours)],
        ).fetchone()

        # Handle None values from DB (NULL columns)
        previous_oi = (
            previous_result[0]
            if previous_result and previous_result[0] is not None
            else current_oi
        )

        # Get 24h ago for oi_change_24h
        oi_24h_result = conn.execute(
            """
            SELECT open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, current_ts - timedelta(hours=24)],
        ).fetchone()

        # Handle None values from DB (NULL columns)
        oi_24h_ago = (
            oi_24h_result[0]
            if oi_24h_result and oi_24h_result[0] is not None
            else current_oi
        )

        # Calculate changes
        oi_change_1h = calculate_oi_change(float(current_oi), float(previous_oi))
        oi_change_24h = calculate_oi_change(float(current_oi), float(oi_24h_ago))

        # Get vote and context
        vote, context = oi_to_vote(oi_change_1h, whale_direction)

        signal = OpenInterestSignal(
            timestamp=current_ts,
            symbol=symbol,
            exchange=exchange,
            oi_value=float(current_oi),
            oi_change_1h=oi_change_1h,
            oi_change_24h=oi_change_24h,
            oi_vote=vote,
            context=context,
        )

        logger.info(
            f"Latest OI signal: {current_oi / 1e9:.2f}B USD, "
            f"1h change={oi_change_1h * 100:+.2f}%, "
            f"vote={vote:.2f} ({context})"
        )

        return signal

    except Exception as e:
        logger.error(f"Error getting latest OI signal: {e}")
        return None

    finally:
        if own_conn:
            close_connection(conn)


def get_oi_signal_at(
    timestamp: datetime,
    whale_direction: str = "NEUTRAL",
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
    window_hours: int = 1,
) -> Optional[OpenInterestSignal]:
    """
    Get OI signal at a specific timestamp.

    Args:
        timestamp: Target timestamp.
        whale_direction: Current whale signal direction.
        conn: Optional DuckDB connection.
        symbol: Trading pair.
        exchange: Exchange source.
        window_hours: Hours for change calculation.

    Returns:
        OpenInterestSignal or None if unavailable.
    """
    own_conn = False
    if conn is None:
        conn = get_liq_connection()
        own_conn = True

    if conn is None:
        return None

    try:
        result = read_oi_at_timestamp(conn, timestamp, symbol, window_hours)
        if result is None:
            return None

        ts, current_oi, previous_oi = result
        oi_change_1h = calculate_oi_change(current_oi, previous_oi)

        # Get 24h change
        oi_24h_result = conn.execute(
            """
            SELECT open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, timestamp - timedelta(hours=24)],
        ).fetchone()

        # Handle None values from DB (NULL columns)
        oi_24h_ago = (
            oi_24h_result[0]
            if oi_24h_result and oi_24h_result[0] is not None
            else current_oi
        )
        oi_change_24h = calculate_oi_change(current_oi, float(oi_24h_ago))

        vote, context = oi_to_vote(oi_change_1h, whale_direction)

        return OpenInterestSignal(
            timestamp=ts,
            symbol=symbol,
            exchange=exchange,
            oi_value=current_oi,
            oi_change_1h=oi_change_1h,
            oi_change_24h=oi_change_24h,
            oi_vote=vote,
            context=context,
        )

    finally:
        if own_conn:
            close_connection(conn)


__all__ = [
    "calculate_oi_change",
    "oi_to_vote",
    "read_oi_at_timestamp",
    "get_latest_oi_signal",
    "get_oi_signal_at",
    "SIGNIFICANT_CHANGE",
    "DELEVERAGE_THRESHOLD",
    "NEUTRAL_ZONE",
]
