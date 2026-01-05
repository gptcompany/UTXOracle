"""
NVT Ratio (Network Value to Transactions) Calculator.

NVT = Market Cap / Daily TX Volume (USD)

Similar to P/E ratio for stocks - measures if network is over/undervalued
relative to its transaction throughput.

Interpretation:
- NVT < 30: Network undervalued, high utility vs valuation
- NVT 30-90: Fair value range
- NVT > 90: Network overvalued, speculation > utility

Usage:
    from scripts.metrics.nvt import calculate_nvt, NVTResult

    result = calculate_nvt(
        market_cap_usd=1_900_000_000_000,  # $1.9T
        tx_volume_usd=50_000_000_000,       # $50B daily volume
    )
    print(f"NVT: {result.nvt_ratio:.1f}")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import duckdb


@dataclass
class NVTResult:
    """NVT ratio calculation result."""

    nvt_ratio: float
    market_cap_usd: float
    tx_volume_usd: float
    signal: str  # "undervalued", "fair", "overvalued"
    date: date
    timestamp: datetime

    @property
    def is_undervalued(self) -> bool:
        return self.nvt_ratio < 30

    @property
    def is_overvalued(self) -> bool:
        return self.nvt_ratio > 90


# NVT thresholds
NVT_UNDERVALUED = 30
NVT_OVERVALUED = 90


def calculate_nvt(
    market_cap_usd: float,
    tx_volume_usd: float,
    target_date: Optional[date] = None,
) -> NVTResult:
    """Calculate NVT ratio.

    Args:
        market_cap_usd: Total market capitalization in USD
        tx_volume_usd: Daily transaction volume in USD
        target_date: Date for the metric (defaults to today)

    Returns:
        NVTResult with ratio and signal

    Raises:
        ValueError: If tx_volume_usd is zero or negative
    """
    if tx_volume_usd <= 0:
        raise ValueError("tx_volume_usd must be positive")

    if market_cap_usd < 0:
        raise ValueError("market_cap_usd must be non-negative")

    nvt_ratio = market_cap_usd / tx_volume_usd

    # Determine signal
    if nvt_ratio < NVT_UNDERVALUED:
        signal = "undervalued"
    elif nvt_ratio > NVT_OVERVALUED:
        signal = "overvalued"
    else:
        signal = "fair"

    return NVTResult(
        nvt_ratio=nvt_ratio,
        market_cap_usd=market_cap_usd,
        tx_volume_usd=tx_volume_usd,
        signal=signal,
        date=target_date or date.today(),
        timestamp=datetime.now(),
    )


def calculate_nvt_from_db(
    conn: duckdb.DuckDBPyConnection,
    target_date: date,
    price_usd: float,
) -> Optional[NVTResult]:
    """Calculate NVT from DuckDB data.

    Uses:
    - circulating_supply from utxo_lifecycle aggregation
    - tx_volume from daily transaction data

    Args:
        conn: DuckDB connection
        target_date: Date to calculate for
        price_usd: BTC price in USD

    Returns:
        NVTResult or None if data unavailable
    """
    # Get circulating supply (total unspent BTC)
    supply_result = conn.execute(
        """
        SELECT COALESCE(SUM(btc_value), 0) AS supply
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
        """
    ).fetchone()

    circulating_supply = supply_result[0] if supply_result else 0

    if circulating_supply <= 0:
        return None

    # Get daily TX volume from block range
    start_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp())
    end_ts = start_ts + 86400

    # Query spent UTXOs for that day as proxy for TX volume
    volume_result = conn.execute(
        """
        SELECT COALESCE(SUM(btc_value), 0) AS volume
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_block IN (
              SELECT height FROM block_heights
              WHERE timestamp >= ? AND timestamp < ?
          )
        """,
        [start_ts, end_ts],
    ).fetchone()

    tx_volume_btc = volume_result[0] if volume_result else 0

    if tx_volume_btc <= 0:
        return None

    # Calculate market cap and TX volume in USD
    market_cap_usd = circulating_supply * price_usd
    tx_volume_usd = tx_volume_btc * price_usd

    return calculate_nvt(market_cap_usd, tx_volume_usd, target_date)
