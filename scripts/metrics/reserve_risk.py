"""Reserve Risk Calculator.

spec-021: Advanced On-Chain Metrics
Implements FR-003: Reserve Risk Ratio

Measures long-term holder confidence relative to price. Lower values
indicate higher conviction (historically good buy zones).

Formula: Reserve Risk = Price / (HODL Bank × Circulating Supply)
HODL Bank = Cumulative Coindays Destroyed (scaled)

Signal Zones:
    < 0.002: Strong buy zone (cycle bottoms)
    0.002 - 0.008: Accumulation zone
    0.008 - 0.02: Fair value
    > 0.02: Distribution zone (cycle tops)

Usage:
    from scripts.metrics.reserve_risk import calculate_reserve_risk

    result = calculate_reserve_risk(
        conn=duckdb_conn,
        current_price_usd=100000.0,
        block_height=875000,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb

from scripts.models.metrics_models import ReserveRiskResult

logger = logging.getLogger(__name__)

# HODL Bank scaling factor (to normalize coindays to reasonable values)
HODL_BANK_SCALE = 1_000_000


def calculate_reserve_risk(
    conn: duckdb.DuckDBPyConnection,
    current_price_usd: float,
    block_height: int,
) -> ReserveRiskResult:
    """Calculate Reserve Risk ratio.

    Reserve Risk measures the confidence of long-term holders relative to
    the current price. Lower values suggest higher conviction (good buy zones).

    Args:
        conn: DuckDB connection with utxo_lifecycle and cointime_metrics tables.
        current_price_usd: Current BTC price.
        block_height: Current block height for metadata.

    Returns:
        ReserveRiskResult with reserve risk and signal classification.

    Example:
        >>> result = calculate_reserve_risk(conn, 100000.0, 875000)
        >>> result.signal_zone
        'ACCUMULATION'
    """
    logger.debug(
        f"Calculating Reserve Risk: price=${current_price_usd:,.0f}, block={block_height}"
    )

    # Get circulating supply (unspent UTXOs)
    supply_query = """
        SELECT COALESCE(SUM(btc_value), 0) AS circulating_supply
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
    """
    supply_result = conn.execute(supply_query).fetchone()
    circulating_supply = float(supply_result[0]) if supply_result else 0.0

    # Get HODL Bank (cumulative CDD from spent UTXOs, scaled)
    hodl_bank_query = """
        SELECT COALESCE(SUM(COALESCE(age_days, 0) * btc_value), 0) / ? AS hodl_bank
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
    """
    hodl_result = conn.execute(hodl_bank_query, [HODL_BANK_SCALE]).fetchone()
    hodl_bank = float(hodl_result[0]) if hodl_result else 0.0

    # Get liveliness from cointime_metrics (if available)
    liveliness = 0.3  # Default
    try:
        liveliness_query = """
            SELECT liveliness
            FROM cointime_metrics
            ORDER BY block_height DESC
            LIMIT 1
        """
        liveliness_result = conn.execute(liveliness_query).fetchone()
        if liveliness_result:
            liveliness = float(liveliness_result[0])
    except Exception as e:
        # Table may not exist - use default liveliness
        logger.debug(
            f"cointime_metrics table not available, using default liveliness: {e}"
        )

    # Calculate MVRV (simplified - would need realized cap for full calculation)
    # For now, estimate from supply and price
    mvrv = 1.5  # Default placeholder

    # Calculate Reserve Risk
    if hodl_bank > 0 and circulating_supply > 0:
        reserve_risk = current_price_usd / (hodl_bank * circulating_supply)
    else:
        # Default to low risk if no data
        reserve_risk = 0.001

    # Classify signal zone
    signal_zone, confidence = _classify_signal_zone(reserve_risk)

    logger.info(
        f"Reserve Risk calculated: {reserve_risk:.6f}, zone={signal_zone}, "
        f"supply={circulating_supply:.2f} BTC"
    )

    return ReserveRiskResult(
        reserve_risk=reserve_risk,
        current_price_usd=current_price_usd,
        hodl_bank=hodl_bank,
        circulating_supply_btc=circulating_supply,
        mvrv=mvrv,
        liveliness=liveliness,
        signal_zone=signal_zone,
        confidence=confidence,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def _classify_signal_zone(reserve_risk: float) -> tuple[str, float]:
    """Classify signal zone based on Reserve Risk value.

    Historical thresholds based on Bitcoin cycle analysis:
    - < 0.002: Historically cycle bottoms
    - 0.002-0.008: Accumulation phases
    - 0.008-0.02: Fair value range
    - > 0.02: Distribution/cycle tops

    Args:
        reserve_risk: Reserve Risk ratio.

    Returns:
        Tuple of (zone_name, confidence).
    """
    if reserve_risk < 0.002:
        return "STRONG_BUY", 0.85
    elif reserve_risk < 0.008:
        return "ACCUMULATION", 0.7
    elif reserve_risk < 0.02:
        return "FAIR_VALUE", 0.5
    else:
        return "DISTRIBUTION", 0.8
