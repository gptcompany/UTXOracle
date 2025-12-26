#!/usr/bin/env python3
"""
Puell Multiple Calculation (spec-033, T003)

Puell Multiple measures daily miner revenue relative to its 365-day average.
Used as a cycle indicator - high values suggest overheating, low values suggest capitulation.

Formula:
    Daily Miner Revenue = (Block Subsidy + Fees) × BTC Price
    Puell Multiple = Daily Revenue / 365d MA(Daily Revenue)

Zone Classification:
    > 3.5: OVERHEATED (potential cycle top)
    0.5 - 3.5: FAIR_VALUE (normal range)
    < 0.5: CAPITULATION (potential cycle bottom)

Data Sources:
    - Block subsidy: Calculated from block height
    - Transaction fees: electrs API or Bitcoin Core RPC
    - BTC price: UTXOracle daily calculation or utxo_snapshots table
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from enum import Enum


class PuellZone(str, Enum):
    """Puell Multiple zone classification."""

    OVERHEATED = "overheated"  # > 3.5 - potential cycle top
    FAIR_VALUE = "fair_value"  # 0.5 - 3.5 - normal range
    CAPITULATION = "capitulation"  # < 0.5 - potential cycle bottom


@dataclass
class PuellMultipleResult:
    """Result of Puell Multiple calculation."""

    date: datetime
    puell_multiple: float
    zone: PuellZone

    # Component values for transparency
    daily_revenue_usd: float
    ma_365d_revenue_usd: float
    block_subsidy_btc: float
    total_fees_btc: float
    btc_price_usd: float

    # Metadata
    blocks_counted: int
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.strftime("%Y-%m-%d")
            if isinstance(self.date, datetime)
            else str(self.date),
            "puell_multiple": round(self.puell_multiple, 4),
            "zone": self.zone.value,
            "daily_revenue_usd": round(self.daily_revenue_usd, 2),
            "ma_365d_revenue_usd": round(self.ma_365d_revenue_usd, 2),
            "block_subsidy_btc": round(self.block_subsidy_btc, 8),
            "total_fees_btc": round(self.total_fees_btc, 8),
            "btc_price_usd": round(self.btc_price_usd, 2),
            "blocks_counted": self.blocks_counted,
            "confidence": round(self.confidence, 4),
        }


# =============================================================================
# Block Subsidy Calculation
# =============================================================================


def get_block_subsidy(block_height: int) -> float:
    """
    Calculate block subsidy in BTC for a given block height.

    Bitcoin halving occurs every 210,000 blocks:
    - Blocks 0-209,999: 50 BTC
    - Blocks 210,000-419,999: 25 BTC
    - Blocks 420,000-629,999: 12.5 BTC
    - Blocks 630,000-839,999: 6.25 BTC
    - Blocks 840,000+: 3.125 BTC (after April 2024 halving)

    Args:
        block_height: Bitcoin block height

    Returns:
        Block subsidy in BTC

    Raises:
        ValueError: If block_height is negative
    """
    if block_height < 0:
        raise ValueError(f"block_height must be non-negative, got {block_height}")

    halvings = block_height // 210_000
    # Initial subsidy is 50 BTC, halves every 210,000 blocks
    subsidy = 50.0 / (2**halvings)
    return subsidy


def get_blocks_per_day() -> int:
    """Return expected blocks per day (144 at 10-minute target)."""
    return 144


# =============================================================================
# Zone Classification
# =============================================================================


def classify_puell_zone(puell_value: float) -> PuellZone:
    """
    Classify Puell Multiple value into a zone.

    Args:
        puell_value: Puell Multiple value

    Returns:
        PuellZone classification
    """
    if puell_value > 3.5:
        return PuellZone.OVERHEATED
    elif puell_value >= 0.5:
        return PuellZone.FAIR_VALUE
    else:
        return PuellZone.CAPITULATION


# =============================================================================
# Puell Multiple Calculation
# =============================================================================


def calculate_puell_multiple(
    daily_revenue_usd: float,
    ma_365d_revenue_usd: float,
) -> float:
    """
    Calculate Puell Multiple from daily revenue and 365d moving average.

    Args:
        daily_revenue_usd: Daily miner revenue in USD (must be non-negative)
        ma_365d_revenue_usd: 365-day moving average of daily revenue (must be positive)

    Returns:
        Puell Multiple value (ratio), or 0.0 if inputs are invalid
    """
    # Guard against invalid inputs
    if ma_365d_revenue_usd <= 0:
        return 0.0
    if daily_revenue_usd < 0:
        # Negative revenue is not valid in this context
        return 0.0
    return daily_revenue_usd / ma_365d_revenue_usd


def calculate_daily_miner_revenue(
    block_subsidy_btc: float,
    total_fees_btc: float,
    btc_price_usd: float,
    blocks_in_day: int = 144,
) -> float:
    """
    Calculate daily miner revenue in USD.

    Args:
        block_subsidy_btc: Block subsidy per block in BTC
        total_fees_btc: Total fees collected across all blocks in BTC
        btc_price_usd: BTC price in USD
        blocks_in_day: Number of blocks in the day

    Returns:
        Daily miner revenue in USD
    """
    subsidy_revenue_btc = block_subsidy_btc * blocks_in_day
    total_revenue_btc = subsidy_revenue_btc + total_fees_btc
    return total_revenue_btc * btc_price_usd


# =============================================================================
# Data Fetching (requires electrs or RPC)
# =============================================================================


def fetch_daily_fees_btc(
    target_date: datetime,
    electrs_url: str = "http://localhost:3001",
) -> tuple[float, int]:
    """
    Fetch total transaction fees for a day from electrs API.

    Args:
        target_date: Date to fetch fees for
        electrs_url: electrs HTTP API URL

    Returns:
        Tuple of (total_fees_btc, blocks_counted)
    """
    # TODO: Implement electrs API call to get block fees
    # For each block in the day:
    #   GET /api/block/{hash} -> totalFees (in satoshis)
    # Sum all fees and convert to BTC
    return 0.0, 0


def fetch_btc_price_for_date(target_date: datetime) -> Optional[float]:
    """
    Fetch BTC price for a specific date from UTXOracle or utxo_snapshots.

    Args:
        target_date: Date to fetch price for

    Returns:
        BTC price in USD or None if not available
    """
    # TODO: Implement using DuckDB utxo_snapshots table or UTXOracle calculation
    return None


def fetch_historical_revenues(
    end_date: datetime,
    days: int = 365,
) -> list[float]:
    """
    Fetch historical daily miner revenues for calculating moving average.

    Args:
        end_date: End date (inclusive)
        days: Number of days of history to fetch

    Returns:
        List of daily revenues in USD (oldest to newest)
    """
    # TODO: Implement using DuckDB cointime_metrics table or calculate from blocks
    return []


# =============================================================================
# Main Calculation Function
# =============================================================================


def get_puell_multiple(
    target_date: datetime | date,
    block_height: Optional[int] = None,
    btc_price_usd: Optional[float] = None,
) -> Optional[PuellMultipleResult]:
    """
    Calculate Puell Multiple for a specific date.

    Args:
        target_date: Date to calculate for
        block_height: Optional block height (for subsidy calculation)
        btc_price_usd: Optional pre-fetched BTC price

    Returns:
        PuellMultipleResult or None if calculation fails
    """
    if isinstance(target_date, date) and not isinstance(target_date, datetime):
        target_date = datetime.combine(target_date, datetime.min.time())

    # Get BTC price
    if btc_price_usd is None:
        btc_price_usd = fetch_btc_price_for_date(target_date)
        if btc_price_usd is None:
            return None

    # Get block subsidy (estimate if no block height provided)
    # For estimation, use approximate block height based on date
    if block_height is None:
        # Genesis block was Jan 3, 2009
        # Approximate: ~144 blocks per day
        days_since_genesis = (target_date - datetime(2009, 1, 3)).days
        block_height = days_since_genesis * 144

    subsidy_btc = get_block_subsidy(block_height)

    # Fetch daily fees
    total_fees_btc, blocks_counted = fetch_daily_fees_btc(target_date)

    # Calculate daily revenue
    daily_revenue = calculate_daily_miner_revenue(
        block_subsidy_btc=subsidy_btc,
        total_fees_btc=total_fees_btc,
        btc_price_usd=btc_price_usd,
        blocks_in_day=blocks_counted or 144,
    )

    # Fetch historical revenues for MA calculation
    historical_revenues = fetch_historical_revenues(target_date, days=365)

    if len(historical_revenues) < 365:
        # Insufficient history - use what we have or return low confidence
        if len(historical_revenues) == 0:
            ma_365d = daily_revenue  # Fallback to current value
            confidence = 0.0
        else:
            ma_365d = sum(historical_revenues) / len(historical_revenues)
            confidence = len(historical_revenues) / 365.0
    else:
        ma_365d = sum(historical_revenues) / 365.0
        confidence = 1.0

    # Calculate Puell Multiple
    puell = calculate_puell_multiple(daily_revenue, ma_365d)
    zone = classify_puell_zone(puell)

    return PuellMultipleResult(
        date=target_date,
        puell_multiple=puell,
        zone=zone,
        daily_revenue_usd=daily_revenue,
        ma_365d_revenue_usd=ma_365d,
        block_subsidy_btc=subsidy_btc,
        total_fees_btc=total_fees_btc,
        btc_price_usd=btc_price_usd,
        blocks_counted=blocks_counted or 144,
        confidence=confidence,
    )
