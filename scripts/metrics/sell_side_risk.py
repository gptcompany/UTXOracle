"""Sell-side Risk Calculator.

spec-021: Advanced On-Chain Metrics
Implements FR-004: Sell-side Risk Ratio

Ratio of realized profit to market cap. High values indicate aggressive
profit-taking (potential distribution phase).

Formula: Sell-side Risk = Realized Profit (30d) / Market Cap
Realized Profit = Sum((spend_price - creation_price) × btc_value)

Signal Zones:
    < 0.1%: Low distribution (bullish)
    0.1% - 0.3%: Normal profit-taking
    0.3% - 1.0%: Elevated distribution
    > 1.0%: Aggressive distribution (top warning)

Usage:
    from scripts.metrics.sell_side_risk import calculate_sell_side_risk

    result = calculate_sell_side_risk(
        conn=duckdb_conn,
        market_cap_usd=2_000_000_000_000.0,
        block_height=875000,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import duckdb

from scripts.models.metrics_models import SellSideRiskResult

logger = logging.getLogger(__name__)


def calculate_sell_side_risk(
    conn: duckdb.DuckDBPyConnection,
    market_cap_usd: float,
    block_height: int,
    window_days: int = 30,
) -> SellSideRiskResult:
    """Calculate Sell-side Risk ratio.

    Measures the ratio of realized profit to market cap over a rolling window.
    High values indicate aggressive profit-taking (potential distribution).

    Args:
        conn: DuckDB connection with utxo_lifecycle table.
        market_cap_usd: Current market capitalization in USD.
        block_height: Current block height for metadata.
        window_days: Rolling window for profit calculation (default: 30 days).

    Returns:
        SellSideRiskResult with sell-side risk and signal classification.

    Example:
        >>> result = calculate_sell_side_risk(conn, 2e12, 875000)
        >>> result.signal_zone
        'NORMAL'
    """
    logger.debug(
        f"Calculating Sell-side Risk: market_cap=${market_cap_usd:,.0f}, "
        f"block={block_height}, window={window_days}d"
    )

    # Calculate window cutoff
    window_cutoff = datetime.utcnow() - timedelta(days=window_days)
    # Convert to Unix epoch (spent_timestamp is stored as BIGINT seconds)
    window_cutoff_epoch = int(window_cutoff.timestamp())

    # Query: Get realized P/L for UTXOs spent in window
    pnl_query = """
        SELECT
            COALESCE(SUM(CASE
                WHEN spent_price_usd > creation_price_usd
                THEN (spent_price_usd - creation_price_usd) * btc_value
                ELSE 0
            END), 0) AS realized_profit,
            COALESCE(SUM(CASE
                WHEN spent_price_usd < creation_price_usd
                THEN (creation_price_usd - spent_price_usd) * btc_value
                ELSE 0
            END), 0) AS realized_loss,
            COUNT(*) AS spent_count
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
    """

    result = conn.execute(pnl_query, [window_cutoff_epoch]).fetchone()

    realized_profit = float(result[0]) if result else 0.0
    realized_loss = float(result[1]) if result else 0.0
    spent_count = int(result[2]) if result else 0

    net_realized_pnl = realized_profit - realized_loss

    # Calculate Sell-side Risk
    if market_cap_usd > 0:
        sell_side_risk = realized_profit / market_cap_usd
    else:
        sell_side_risk = 0.0

    sell_side_risk_pct = sell_side_risk * 100

    # Classify signal zone
    signal_zone, confidence = _classify_signal_zone(sell_side_risk_pct)

    logger.info(
        f"Sell-side Risk calculated: {sell_side_risk_pct:.4f}%, zone={signal_zone}, "
        f"profit=${realized_profit:,.0f}, loss=${realized_loss:,.0f}"
    )

    return SellSideRiskResult(
        sell_side_risk=sell_side_risk,
        sell_side_risk_pct=sell_side_risk_pct,
        realized_profit_usd=realized_profit,
        realized_loss_usd=realized_loss,
        net_realized_pnl_usd=net_realized_pnl,
        market_cap_usd=market_cap_usd,
        window_days=window_days,
        spent_utxos_in_window=spent_count,
        signal_zone=signal_zone,
        confidence=confidence,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def _classify_signal_zone(sell_side_risk_pct: float) -> tuple[str, float]:
    """Classify signal zone based on Sell-side Risk percentage.

    Thresholds based on historical distribution patterns:
    - < 0.1%: Low profit-taking (bullish)
    - 0.1-0.3%: Normal market activity
    - 0.3-1.0%: Elevated distribution
    - > 1.0%: Aggressive profit-taking (cycle top warning)

    Args:
        sell_side_risk_pct: Sell-side risk as percentage (0-100).

    Returns:
        Tuple of (zone_name, confidence).
    """
    if sell_side_risk_pct < 0.1:
        return "LOW", 0.7
    elif sell_side_risk_pct < 0.3:
        return "NORMAL", 0.6
    elif sell_side_risk_pct < 1.0:
        return "ELEVATED", 0.75
    else:
        return "AGGRESSIVE", 0.85
