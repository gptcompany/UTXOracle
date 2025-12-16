"""
NUPL Oscillator Module (spec-022).

Provides zone classification for Net Unrealized Profit/Loss (NUPL) metric
and API integration for CheckOnChain dashboard.

Reuses existing calculate_nupl() from realized_metrics.py and adds:
- Zone classification (CAPITULATION, HOPE_FEAR, OPTIMISM, BELIEF, EUPHORIA)
- NUPLResult dataclass for structured output
- calculate_nupl_signal() orchestrator function

Usage:
    from scripts.metrics.nupl import calculate_nupl_signal, classify_nupl_zone

    result = calculate_nupl_signal(conn, block_height, current_price)
    print(f"NUPL: {result.nupl:.2f}, Zone: {result.zone.value}")
"""

import logging
from datetime import datetime

import duckdb

from scripts.models.metrics_models import NUPLZone, NUPLResult
from scripts.metrics.realized_metrics import (
    calculate_nupl,
    calculate_market_cap,
    calculate_realized_cap,
    get_total_unspent_supply,
)

logger = logging.getLogger(__name__)


def classify_nupl_zone(nupl: float) -> NUPLZone:
    """Classify NUPL value into market cycle zone.

    Zone boundaries follow Glassnode thresholds:
    - CAPITULATION: < 0 (network underwater)
    - HOPE_FEAR: 0 - 0.25 (recovery phase)
    - OPTIMISM: 0.25 - 0.5 (bull building)
    - BELIEF: 0.5 - 0.75 (strong conviction)
    - EUPHORIA: >= 0.75 (extreme greed)

    Args:
        nupl: NUPL value (typically -1 to 1).

    Returns:
        NUPLZone enum member.
    """
    if nupl < 0:
        return NUPLZone.CAPITULATION
    elif nupl < 0.25:
        return NUPLZone.HOPE_FEAR
    elif nupl < 0.5:
        return NUPLZone.OPTIMISM
    elif nupl < 0.75:
        return NUPLZone.BELIEF
    else:
        return NUPLZone.EUPHORIA


def calculate_nupl_signal(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    current_price_usd: float,
    timestamp: datetime | None = None,
) -> NUPLResult:
    """Calculate NUPL with zone classification.

    Orchestrates the NUPL calculation by:
    1. Fetching realized cap from utxo_lifecycle_full VIEW
    2. Calculating market cap from supply × price
    3. Computing NUPL value
    4. Classifying into market cycle zone

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        block_height: Current block height.
        current_price_usd: Current BTC price in USD.
        timestamp: Optional timestamp (defaults to now).

    Returns:
        NUPLResult with zone classification.
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    logger.debug(
        "Calculating NUPL signal for block %d at price $%.2f",
        block_height,
        current_price_usd,
    )

    # Fetch realized cap and supply from database
    realized_cap_usd = calculate_realized_cap(conn)
    total_supply_btc = get_total_unspent_supply(conn)

    logger.debug(
        "Realized Cap: $%.2f, Supply: %.2f BTC",
        realized_cap_usd,
        total_supply_btc,
    )

    # Handle edge case: zero supply (empty UTXO set)
    if total_supply_btc <= 0:
        logger.warning("Zero supply detected - returning neutral NUPL")
        return NUPLResult(
            nupl=0.0,
            zone=NUPLZone.HOPE_FEAR,
            market_cap_usd=0.0,
            realized_cap_usd=0.0,
            unrealized_profit_usd=0.0,
            pct_supply_in_profit=0.0,
            block_height=block_height,
            timestamp=timestamp,
            confidence=0.0,  # Low confidence for edge case
        )

    # Calculate market cap and NUPL
    market_cap_usd = calculate_market_cap(total_supply_btc, current_price_usd)
    nupl = calculate_nupl(market_cap_usd, realized_cap_usd)

    # Calculate unrealized profit
    unrealized_profit_usd = market_cap_usd - realized_cap_usd

    # Classify zone
    zone = classify_nupl_zone(nupl)

    # Calculate % supply in profit (approximation based on NUPL)
    # In reality this would query cost basis vs current price per UTXO
    # For now, use NUPL as proxy: NUPL 0.5 ~ 75% in profit
    if market_cap_usd > 0:
        pct_supply_in_profit = max(
            0.0, min(100.0, 50.0 + (nupl * 50.0))
        )  # Linear approximation
    else:
        pct_supply_in_profit = 0.0

    # Confidence based on data quality
    # Higher confidence if we have significant supply and reasonable values
    if total_supply_btc > 1000 and realized_cap_usd > 0:
        confidence = 0.85  # High confidence
    elif total_supply_btc > 100:
        confidence = 0.70  # Medium confidence
    else:
        confidence = 0.50  # Low confidence - sparse data

    result = NUPLResult(
        nupl=nupl,
        zone=zone,
        market_cap_usd=market_cap_usd,
        realized_cap_usd=realized_cap_usd,
        unrealized_profit_usd=unrealized_profit_usd,
        pct_supply_in_profit=pct_supply_in_profit,
        block_height=block_height,
        timestamp=timestamp,
        confidence=confidence,
    )

    logger.info(
        "NUPL signal: %.4f (%s) at block %d",
        nupl,
        zone.value,
        block_height,
    )

    return result
