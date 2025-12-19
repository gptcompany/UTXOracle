"""Binary CDD (Coin Days Destroyed) Statistical Significance Indicator.

spec-027: Binary CDD
Implements statistical significance flag for CDD events.

Binary CDD transforms noisy CDD data into actionable binary signals:
- binary_cdd=0: Normal long-term holder activity (noise)
- binary_cdd=1: Significant event (z-score >= threshold sigma)

Z-Score Formula: z = (cdd_today - mean) / std
Binary Flag: 1 if z >= threshold else 0

Default: threshold=2.0 sigma (captures ~5% of extreme events)

Usage:
    from scripts.metrics.binary_cdd import calculate_binary_cdd

    result = calculate_binary_cdd(
        conn=duckdb_conn,
        block_height=875000,
        threshold=2.0,
        window_days=365,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import duckdb
import numpy as np

from scripts.models.metrics_models import BinaryCDDResult

logger = logging.getLogger(__name__)

# Minimum data points required for reliable statistics
MIN_DATA_POINTS = 30


def calculate_binary_cdd(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    threshold: float = 2.0,
    window_days: int = 365,
) -> BinaryCDDResult:
    """Calculate Binary CDD indicator.

    Computes z-score of current CDD against rolling historical baseline
    and returns binary flag (0/1) for significance.

    Args:
        conn: DuckDB connection with utxo_lifecycle_full table.
        block_height: Current block height for metadata.
        threshold: Z-score threshold for binary flag (default: 2.0 sigma).
        window_days: Lookback window in days (default: 365).

    Returns:
        BinaryCDDResult with CDD statistics and binary flag.

    Example:
        >>> result = calculate_binary_cdd(conn, 875000)
        >>> result.binary_cdd
        0  # Normal activity
    """
    logger.debug(
        f"Calculating Binary CDD: block={block_height}, "
        f"threshold={threshold}σ, window={window_days}d"
    )

    # Clamp threshold to valid range [1.0, 4.0]
    threshold = max(1.0, min(4.0, threshold))
    # Clamp window to valid range [30, 730]
    window_days = max(30, min(730, window_days))

    # Calculate window cutoff (using Python datetime for parameter binding)
    window_cutoff = datetime.utcnow() - timedelta(days=window_days)
    # Convert to Unix epoch (spent_timestamp is stored as BIGINT seconds)
    window_cutoff_epoch = int(window_cutoff.timestamp())

    # Query: Get daily CDD values for the lookback window
    daily_cdd_query = """
        SELECT
            DATE(to_timestamp(spent_timestamp)) AS spend_date,
            SUM(COALESCE(age_days, 0) * btc_value) AS daily_cdd
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
        GROUP BY DATE(to_timestamp(spent_timestamp))
        ORDER BY spend_date
    """

    try:
        daily_data = conn.execute(daily_cdd_query, [window_cutoff_epoch]).fetchall()
    except Exception as e:
        logger.error(f"Error querying daily CDD: {e}")
        # Return insufficient data result on error
        return _insufficient_data_result(
            block_height=block_height,
            threshold=threshold,
            window_days=window_days,
        )

    # Extract daily CDD values
    daily_cdd_values = [float(row[1]) for row in daily_data if row[1] is not None]
    data_points = len(daily_cdd_values)

    logger.debug(f"Retrieved {data_points} daily CDD data points")

    # Check for insufficient data
    if data_points < MIN_DATA_POINTS:
        logger.warning(
            f"Insufficient data: {data_points} points < {MIN_DATA_POINTS} minimum"
        )
        return _insufficient_data_result(
            block_height=block_height,
            threshold=threshold,
            window_days=window_days,
            data_points=data_points,
            cdd_today=daily_cdd_values[-1] if daily_cdd_values else 0.0,
        )

    # Calculate statistics using numpy
    cdd_array = np.array(daily_cdd_values)
    cdd_today = cdd_array[-1]  # Most recent day
    cdd_mean = float(np.mean(cdd_array))
    cdd_std = float(np.std(cdd_array, ddof=1))  # Sample std (N-1)

    # Calculate z-score (handle zero std)
    cdd_zscore: Optional[float] = None
    cdd_percentile: Optional[float] = None
    binary_cdd = 0

    if cdd_std > 0:
        cdd_zscore = (cdd_today - cdd_mean) / cdd_std
        # Calculate percentile rank
        cdd_percentile = float(np.sum(cdd_array < cdd_today) / len(cdd_array) * 100)
        # Determine binary flag
        binary_cdd = 1 if cdd_zscore >= threshold else 0
    else:
        # Zero std means all values identical - z-score undefined
        logger.warning("Zero standard deviation - z-score undefined")
        cdd_zscore = None
        cdd_percentile = 50.0  # Median by definition
        binary_cdd = 0

    zscore_str = f"{cdd_zscore:.2f}" if cdd_zscore is not None else "N/A"
    logger.info(
        f"Binary CDD calculated: today={cdd_today:.2f}, mean={cdd_mean:.2f}, "
        f"std={cdd_std:.2f}, z={zscore_str}, binary={binary_cdd}"
    )

    return BinaryCDDResult(
        cdd_today=float(cdd_today),
        cdd_mean=cdd_mean,
        cdd_std=cdd_std,
        cdd_zscore=cdd_zscore,
        cdd_percentile=cdd_percentile,
        binary_cdd=binary_cdd,
        threshold_used=threshold,
        window_days=window_days,
        data_points=data_points,
        insufficient_data=False,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def _insufficient_data_result(
    block_height: int,
    threshold: float,
    window_days: int,
    data_points: int = 0,
    cdd_today: float = 0.0,
) -> BinaryCDDResult:
    """Create a result object for insufficient data case."""
    return BinaryCDDResult(
        cdd_today=cdd_today,
        cdd_mean=0.0,
        cdd_std=0.0,
        cdd_zscore=None,
        cdd_percentile=None,
        binary_cdd=0,
        threshold_used=threshold,
        window_days=window_days,
        data_points=max(1, data_points),  # Minimum 1 to pass validation
        insufficient_data=True,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )
