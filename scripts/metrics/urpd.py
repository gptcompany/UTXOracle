"""URPD (UTXO Realized Price Distribution) Calculator.

spec-021: Advanced On-Chain Metrics
Implements FR-001: UTXO Realized Price Distribution

Calculates the distribution of unspent BTC by acquisition price (cost basis).
Used for identifying support/resistance zones based on where holders
acquired their coins.

Usage:
    from scripts.metrics.urpd import calculate_urpd

    result = calculate_urpd(
        conn=duckdb_conn,
        current_price_usd=100000.0,
        bucket_size_usd=5000.0,
        block_height=875000,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import duckdb

from scripts.models.metrics_models import (
    CostBasisPercentiles,
    URPDBucket,
    URPDResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def calculate_urpd(
    conn: duckdb.DuckDBPyConnection,
    current_price_usd: float,
    bucket_size_usd: float,
    block_height: int,
) -> URPDResult:
    """Calculate UTXO Realized Price Distribution.

    Groups unspent UTXOs into price buckets based on their creation_price_usd
    (cost basis) and calculates the BTC amount and UTXO count in each bucket.

    Args:
        conn: DuckDB connection with utxo_lifecycle table.
        current_price_usd: Current BTC price for profit/loss split calculation.
        bucket_size_usd: Size of each price bucket in USD (e.g., 5000 for $5k buckets).
        block_height: Current block height for metadata.

    Returns:
        URPDResult with bucket distribution and profit/loss split.

    Example:
        >>> result = calculate_urpd(conn, 100000.0, 5000.0, 875000)
        >>> result.dominant_bucket.price_low
        10000.0
        >>> result.supply_below_price_pct
        76.9  # 76.9% of supply in profit
    """
    logger.debug(
        f"Calculating URPD: current_price=${current_price_usd:,.0f}, "
        f"bucket_size=${bucket_size_usd:,.0f}, block={block_height}"
    )

    # Query: Group unspent UTXOs by price bucket
    # FLOOR(price / bucket_size) * bucket_size gives the bucket's lower bound
    # B1 fix: Filter out NULL creation_price_usd to prevent crash
    # B3 fix: Filter out negative creation_price_usd to prevent ValueError in URPDBucket
    query = """
        SELECT
            FLOOR(creation_price_usd / ?) * ? AS price_bucket,
            SUM(btc_value) AS btc_in_bucket,
            COUNT(*) AS utxo_count
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND creation_price_usd IS NOT NULL
          AND creation_price_usd > 0
        GROUP BY price_bucket
        ORDER BY price_bucket DESC
    """

    result = conn.execute(query, [bucket_size_usd, bucket_size_usd]).fetchall()

    # Calculate total supply for percentage calculation
    total_supply = sum(row[1] for row in result)

    # Handle empty result
    if total_supply == 0:
        logger.info("No unspent UTXOs found - returning empty URPD result")
        return URPDResult(
            buckets=[],
            bucket_size_usd=bucket_size_usd,
            total_supply_btc=0.0,
            current_price_usd=current_price_usd,
            supply_above_price_btc=0.0,
            supply_below_price_btc=0.0,
            supply_above_price_pct=0.0,
            supply_below_price_pct=0.0,
            dominant_bucket=None,
            percentiles=None,
            block_height=block_height,
            timestamp=datetime.utcnow(),
        )

    # Build bucket list and track profit/loss split
    buckets: list[URPDBucket] = []
    supply_above = 0.0  # Cost basis > current price (in loss)
    supply_below = 0.0  # Cost basis < current price (in profit)
    max_btc_bucket: URPDBucket | None = None

    for row in result:
        price_low = float(row[0])
        btc_amount = float(row[1])
        utxo_count = int(row[2])
        price_high = price_low + bucket_size_usd
        percentage = (btc_amount / total_supply) * 100

        bucket = URPDBucket(
            price_low=price_low,
            price_high=price_high,
            btc_amount=btc_amount,
            utxo_count=utxo_count,
            percentage=percentage,
        )
        buckets.append(bucket)

        # Track dominant bucket (highest BTC)
        if max_btc_bucket is None or btc_amount > max_btc_bucket.btc_amount:
            max_btc_bucket = bucket

        # Classify profit/loss based on bucket midpoint vs current price
        # If bucket's upper bound <= current price, all supply in bucket is in profit
        # If bucket's lower bound >= current price, all supply in bucket is in loss
        if price_high <= current_price_usd:
            supply_below += btc_amount
        elif price_low >= current_price_usd:
            supply_above += btc_amount
        else:
            # Bucket straddles current price - split proportionally
            # Simplification: treat as in profit if midpoint < current price
            midpoint = (price_low + price_high) / 2
            if midpoint < current_price_usd:
                supply_below += btc_amount
            else:
                supply_above += btc_amount

    supply_above_pct = (supply_above / total_supply) * 100 if total_supply > 0 else 0.0
    supply_below_pct = (supply_below / total_supply) * 100 if total_supply > 0 else 0.0

    # Calculate cost basis percentiles
    percentiles = calculate_cost_basis_percentiles(conn)

    if max_btc_bucket:
        logger.info(
            f"URPD calculated: {len(buckets)} buckets, {total_supply:.2f} BTC total, "
            f"{supply_below_pct:.1f}% in profit, dominant bucket ${max_btc_bucket.price_low:,.0f}"
        )
    else:
        logger.info(
            f"URPD calculated: {len(buckets)} buckets, {total_supply:.2f} BTC total, "
            f"{supply_below_pct:.1f}% in profit, no dominant bucket"
        )

    return URPDResult(
        buckets=buckets,
        bucket_size_usd=bucket_size_usd,
        total_supply_btc=total_supply,
        current_price_usd=current_price_usd,
        supply_above_price_btc=supply_above,
        supply_below_price_btc=supply_below,
        supply_above_price_pct=supply_above_pct,
        supply_below_price_pct=supply_below_pct,
        dominant_bucket=max_btc_bucket,
        percentiles=percentiles,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def calculate_cost_basis_percentiles(
    conn: duckdb.DuckDBPyConnection,
) -> CostBasisPercentiles | None:
    """Calculate cost basis percentiles weighted by BTC value.

    Computes percentiles (p10, p25, p50, p75, p90) of UTXO acquisition prices
    weighted by BTC value. For example, p50 is the price where 50% of the
    total supply (by BTC amount) was acquired below that price.

    Args:
        conn: DuckDB connection with utxo_lifecycle table.

    Returns:
        CostBasisPercentiles or None if no data available.

    Example:
        >>> percentiles = calculate_cost_basis_percentiles(conn)
        >>> percentiles.p50  # Median cost basis
        67000.0
        >>> percentiles.p90  # 90% of supply acquired below this price
        95000.0
    """
    logger.debug("Calculating cost basis percentiles")

    # Query: Get all unspent UTXOs sorted by creation price
    # We'll calculate percentiles client-side for flexibility
    # B3 fix: Filter out negative creation_price_usd to prevent ValueError
    query = """
        SELECT
            creation_price_usd,
            btc_value
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND creation_price_usd IS NOT NULL
          AND creation_price_usd > 0
        ORDER BY creation_price_usd ASC
    """

    result = conn.execute(query).fetchall()

    if not result:
        logger.warning("No unspent UTXOs found for percentile calculation")
        return None

    # Build cumulative distribution
    prices = []
    btc_amounts = []
    total_btc = 0.0

    for row in result:
        price = float(row[0])
        btc = float(row[1])
        prices.append(price)
        btc_amounts.append(btc)
        total_btc += btc

    if total_btc == 0:
        logger.warning("Total BTC is zero, cannot calculate percentiles")
        return None

    # Calculate cumulative BTC
    cumulative_btc = 0.0
    cumulative_pcts = []

    for btc in btc_amounts:
        cumulative_btc += btc
        cumulative_pcts.append(cumulative_btc / total_btc)

    # Find percentile values using linear interpolation
    def find_percentile(target_pct: float) -> float:
        """Find price at target percentile using linear interpolation."""
        for i, pct in enumerate(cumulative_pcts):
            if pct >= target_pct:
                if i == 0:
                    return prices[0]
                # Linear interpolation between i-1 and i
                pct_prev = cumulative_pcts[i - 1]
                pct_curr = pct
                price_prev = prices[i - 1]
                price_curr = prices[i]

                # Interpolate
                if pct_curr == pct_prev:
                    return price_curr
                weight = (target_pct - pct_prev) / (pct_curr - pct_prev)
                return price_prev + weight * (price_curr - price_prev)

        # If we get here, return the highest price
        return prices[-1]

    p10 = find_percentile(0.10)
    p25 = find_percentile(0.25)
    p50 = find_percentile(0.50)
    p75 = find_percentile(0.75)
    p90 = find_percentile(0.90)

    logger.info(
        f"Percentiles calculated: p10=${p10:,.0f}, p25=${p25:,.0f}, "
        f"p50=${p50:,.0f}, p75=${p75:,.0f}, p90=${p90:,.0f}"
    )

    return CostBasisPercentiles(
        p10=p10,
        p25=p25,
        p50=p50,
        p75=p75,
        p90=p90,
    )


def _classify_supply_by_price(
    buckets: list[URPDBucket],
    current_price_usd: float,
) -> tuple[float, float]:
    """Classify supply as above or below current price.

    Helper function for profit/loss split calculation.

    Args:
        buckets: List of URPD buckets.
        current_price_usd: Current BTC price.

    Returns:
        Tuple of (supply_above_btc, supply_below_btc).
    """
    supply_above = 0.0
    supply_below = 0.0

    for bucket in buckets:
        if bucket.price_high <= current_price_usd:
            supply_below += bucket.btc_amount
        elif bucket.price_low >= current_price_usd:
            supply_above += bucket.btc_amount
        else:
            # Bucket straddles - use midpoint
            midpoint = (bucket.price_low + bucket.price_high) / 2
            if midpoint < current_price_usd:
                supply_below += bucket.btc_amount
            else:
                supply_above += bucket.btc_amount

    return supply_above, supply_below


def _find_dominant_bucket(buckets: list[URPDBucket]) -> URPDBucket | None:
    """Find the bucket with the highest BTC amount.

    Args:
        buckets: List of URPD buckets.

    Returns:
        Bucket with maximum BTC, or None if empty.
    """
    if not buckets:
        return None

    return max(buckets, key=lambda b: b.btc_amount)
