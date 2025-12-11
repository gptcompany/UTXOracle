"""Supply Profit/Loss Calculator.

spec-021: Advanced On-Chain Metrics
Implements FR-002: Supply Profit/Loss Distribution

Calculates the breakdown of circulating supply by profit/loss status,
with STH/LTH cohort segmentation. Used for market phase detection
and sentiment analysis.

Usage:
    from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

    result = calculate_supply_profit_loss(
        conn=duckdb_conn,
        current_price_usd=100000.0,
        block_height=875000,
    )

Market Phases:
    EUPHORIA: >95% in profit (cycle top warning)
    BULL: 80-95% in profit
    TRANSITION: 50-80% in profit
    CAPITULATION: <50% in profit (accumulation zone)
"""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb

from scripts.models.metrics_models import SupplyProfitLossResult

logger = logging.getLogger(__name__)

# STH/LTH threshold in days (155 days = ~5 months)
STH_THRESHOLD_DAYS = 155


def calculate_supply_profit_loss(
    conn: duckdb.DuckDBPyConnection,
    current_price_usd: float,
    block_height: int,
    sth_threshold_days: int = STH_THRESHOLD_DAYS,
) -> SupplyProfitLossResult:
    """Calculate supply breakdown by profit/loss status.

    Classifies each unspent UTXO as in profit, loss, or breakeven based on
    its creation price vs current price. Also segments by STH/LTH cohort.

    Args:
        conn: DuckDB connection with utxo_lifecycle table.
        current_price_usd: Current BTC price for comparison.
        block_height: Current block height for metadata.
        sth_threshold_days: Days threshold for STH/LTH classification (default: 155).

    Returns:
        SupplyProfitLossResult with profit/loss breakdown and market phase.

    Example:
        >>> result = calculate_supply_profit_loss(conn, 100000.0, 875000)
        >>> result.pct_in_profit
        72.5  # 72.5% of supply in profit
        >>> result.market_phase
        'BULL'
    """
    logger.debug(
        f"Calculating Supply P/L: current_price=${current_price_usd:,.0f}, "
        f"block={block_height}, sth_threshold={sth_threshold_days}d"
    )

    # Query: Aggregate unspent UTXOs by profit/loss status and cohort
    # Note: We use age_days if available, otherwise fallback to cohort field
    # B2 fix: Filter out NULL creation_price_usd (cannot determine profit/loss)
    query = """
        WITH classified_utxos AS (
            SELECT
                btc_value,
                creation_price_usd,
                COALESCE(age_days, 0) AS age_days,
                CASE
                    WHEN creation_price_usd < ? THEN 'PROFIT'
                    WHEN creation_price_usd > ? THEN 'LOSS'
                    ELSE 'BREAKEVEN'
                END AS profit_status,
                CASE
                    WHEN COALESCE(age_days, 0) < ? THEN 'STH'
                    ELSE 'LTH'
                END AS holder_cohort
            FROM utxo_lifecycle
            WHERE is_spent = FALSE
              AND creation_price_usd IS NOT NULL
        )
        SELECT
            profit_status,
            holder_cohort,
            SUM(btc_value) AS btc_total,
            COUNT(*) AS utxo_count
        FROM classified_utxos
        GROUP BY profit_status, holder_cohort
    """

    result = conn.execute(
        query, [current_price_usd, current_price_usd, sth_threshold_days]
    ).fetchall()

    # Initialize accumulators
    supply_in_profit = 0.0
    supply_in_loss = 0.0
    supply_breakeven = 0.0
    sth_in_profit = 0.0
    sth_in_loss = 0.0
    lth_in_profit = 0.0
    lth_in_loss = 0.0

    # Process results
    for row in result:
        profit_status = row[0]
        holder_cohort = row[1]
        btc_total = float(row[2])

        # Aggregate by profit status
        if profit_status == "PROFIT":
            supply_in_profit += btc_total
            if holder_cohort == "STH":
                sth_in_profit += btc_total
            else:
                lth_in_profit += btc_total
        elif profit_status == "LOSS":
            supply_in_loss += btc_total
            if holder_cohort == "STH":
                sth_in_loss += btc_total
            else:
                lth_in_loss += btc_total
        else:  # BREAKEVEN
            supply_breakeven += btc_total
            # Count breakeven as profit for cohort calculation
            if holder_cohort == "STH":
                sth_in_profit += btc_total
            else:
                lth_in_profit += btc_total

    # Calculate totals
    total_supply = supply_in_profit + supply_in_loss + supply_breakeven
    sth_total = sth_in_profit + sth_in_loss
    lth_total = lth_in_profit + lth_in_loss

    # Handle empty result
    if total_supply == 0:
        logger.info("No unspent UTXOs found - returning empty Supply P/L result")
        return SupplyProfitLossResult(
            current_price_usd=current_price_usd,
            total_supply_btc=0.0,
            supply_in_profit_btc=0.0,
            supply_in_loss_btc=0.0,
            supply_breakeven_btc=0.0,
            pct_in_profit=0.0,
            pct_in_loss=0.0,
            sth_in_profit_btc=0.0,
            sth_in_loss_btc=0.0,
            sth_pct_in_profit=0.0,
            lth_in_profit_btc=0.0,
            lth_in_loss_btc=0.0,
            lth_pct_in_profit=0.0,
            market_phase="CAPITULATION",
            signal_strength=0.0,
            block_height=block_height,
            timestamp=datetime.utcnow(),
        )

    # Calculate percentages
    pct_in_profit = (supply_in_profit / total_supply) * 100
    pct_in_loss = (supply_in_loss / total_supply) * 100
    sth_pct_in_profit = (sth_in_profit / sth_total) * 100 if sth_total > 0 else 0.0
    lth_pct_in_profit = (lth_in_profit / lth_total) * 100 if lth_total > 0 else 0.0

    # Determine market phase
    market_phase = _classify_market_phase(pct_in_profit)

    # Calculate signal strength (higher at extremes)
    signal_strength = _calculate_signal_strength(pct_in_profit)

    logger.info(
        f"Supply P/L calculated: {total_supply:.2f} BTC total, "
        f"{pct_in_profit:.1f}% in profit, phase={market_phase}"
    )

    return SupplyProfitLossResult(
        current_price_usd=current_price_usd,
        total_supply_btc=total_supply,
        supply_in_profit_btc=supply_in_profit,
        supply_in_loss_btc=supply_in_loss,
        supply_breakeven_btc=supply_breakeven,
        pct_in_profit=pct_in_profit,
        pct_in_loss=pct_in_loss,
        sth_in_profit_btc=sth_in_profit,
        sth_in_loss_btc=sth_in_loss,
        sth_pct_in_profit=sth_pct_in_profit,
        lth_in_profit_btc=lth_in_profit,
        lth_in_loss_btc=lth_in_loss,
        lth_pct_in_profit=lth_pct_in_profit,
        market_phase=market_phase,
        signal_strength=signal_strength,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def _classify_market_phase(pct_in_profit: float) -> str:
    """Classify market phase based on percentage of supply in profit.

    Thresholds based on historical Bitcoin cycle analysis:
    - EUPHORIA (>95%): Historically precedes cycle tops
    - BULL (80-95%): Strong uptrend, healthy market
    - TRANSITION (50-80%): Uncertain, could go either way
    - CAPITULATION (<50%): Historically precedes cycle bottoms

    Args:
        pct_in_profit: Percentage of supply in profit (0-100).

    Returns:
        Market phase string.
    """
    if pct_in_profit >= 95.0:
        return "EUPHORIA"
    elif pct_in_profit >= 80.0:
        return "BULL"
    elif pct_in_profit >= 50.0:
        return "TRANSITION"
    else:
        return "CAPITULATION"


def _calculate_signal_strength(pct_in_profit: float) -> float:
    """Calculate signal strength based on extremity of profit/loss.

    Signal is stronger at extremes (euphoria/capitulation) where
    reversals are more likely.

    Args:
        pct_in_profit: Percentage of supply in profit (0-100).

    Returns:
        Signal strength (0.0 to 1.0).
    """
    # Distance from neutral (50%)
    distance_from_neutral = abs(pct_in_profit - 50.0)

    # Normalize: 0% distance = 0.0 strength, 50% distance = 1.0 strength
    # Use sigmoid-like scaling for smoother response
    strength = min(1.0, distance_from_neutral / 50.0)

    # Boost strength at extreme levels
    if pct_in_profit >= 95.0 or pct_in_profit <= 5.0:
        strength = min(1.0, strength + 0.2)
    elif pct_in_profit >= 90.0 or pct_in_profit <= 10.0:
        strength = min(1.0, strength + 0.1)

    return strength
