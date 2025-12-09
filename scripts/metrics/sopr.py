"""
SOPR Module - Spent Output Profit Ratio (spec-016)

Calculates SOPR (Spent Output Profit Ratio) with STH/LTH split for
Bitcoin on-chain analysis.

SOPR = spend_price / creation_price
- SOPR > 1: Coins sold at profit
- SOPR < 1: Coins sold at loss
- SOPR = 1: Break-even point

STH/LTH Classification:
- STH (Short-Term Holders): < 155 days (configurable)
- LTH (Long-Term Holders): >= 155 days (configurable)

Signals:
- sth_capitulation: STH-SOPR < 1.0 for 3+ days (bullish contrarian)
- sth_breakeven_cross: STH-SOPR crosses 1.0 from below
- lth_distribution: LTH-SOPR > 3.0 (cycle top warning)

Academic Reference:
- Omole & Enke (2024): 82.44% directional accuracy with SOPR features

Usage:
    from scripts.metrics.sopr import calculate_output_sopr, calculate_block_sopr
    from scripts.metrics.sopr import detect_sopr_signals, BlockSOPR

    # Individual output
    output = calculate_output_sopr(
        creation_price=50000.0,
        spend_price=100000.0,
        btc_value=1.0,
        age_days=30
    )

    # Block aggregation
    block_sopr = calculate_block_sopr(
        outputs=[output1, output2, ...],
        block_height=800000,
        block_hash="...",
        timestamp=datetime.now()
    )

    # Signal detection
    signals = detect_sopr_signals(window=[block1, block2, ...])
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# =============================================================================
# Configuration
# =============================================================================


def get_sth_threshold() -> int:
    """Get STH threshold from environment (default: 155 days)."""
    return int(os.getenv("SOPR_STH_THRESHOLD_DAYS", "155"))


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SpentOutputSOPR:
    """
    Individual spent output with SOPR calculation.

    Attributes:
        creation_price: USD price when UTXO was created
        spend_price: USD price when UTXO was spent
        btc_value: BTC amount of the output
        age_days: Days between creation and spend
        sopr: Calculated SOPR (spend_price / creation_price)
        cohort: "STH" or "LTH" based on age
        profit_loss: "PROFIT", "LOSS", or "BREAKEVEN"
        is_valid: True if both prices are positive
    """

    creation_price: float
    spend_price: float
    btc_value: float
    age_days: int
    sopr: float = 0.0
    cohort: str = ""
    profit_loss: str = ""
    is_valid: bool = False


@dataclass
class BlockSOPR:
    """
    Aggregated SOPR metrics for a block.

    Attributes:
        block_height: Bitcoin block height
        block_hash: Block hash
        timestamp: Block timestamp
        aggregate_sopr: BTC-weighted average SOPR for all valid outputs
        sth_sopr: BTC-weighted average SOPR for STH outputs only
        lth_sopr: BTC-weighted average SOPR for LTH outputs only
        total_outputs: Total spent outputs in block
        valid_outputs: Outputs with valid SOPR (both prices > 0)
        sth_outputs: Count of STH outputs
        lth_outputs: Count of LTH outputs
        total_btc_moved: Total BTC in valid outputs
        sth_btc_moved: BTC in STH outputs
        lth_btc_moved: BTC in LTH outputs
        profit_outputs: Outputs with SOPR > 1.01
        loss_outputs: Outputs with SOPR < 0.99
        breakeven_outputs: Outputs with 0.99 <= SOPR <= 1.01
        profit_ratio: profit_outputs / valid_outputs
        is_valid: True if valid_outputs >= min_samples
        min_samples: Minimum sample threshold (default: 100)
    """

    block_height: int
    block_hash: str
    timestamp: datetime
    aggregate_sopr: float
    sth_sopr: Optional[float]
    lth_sopr: Optional[float]
    total_outputs: int
    valid_outputs: int
    sth_outputs: int
    lth_outputs: int
    total_btc_moved: float
    sth_btc_moved: float
    lth_btc_moved: float
    profit_outputs: int
    loss_outputs: int
    breakeven_outputs: int
    profit_ratio: float
    is_valid: bool
    min_samples: int = 100

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "block_hash": self.block_hash,
            "timestamp": (
                self.timestamp.isoformat()
                if hasattr(self.timestamp, "isoformat")
                else str(self.timestamp)
            ),
            "aggregate_sopr": self.aggregate_sopr,
            "sth_sopr": self.sth_sopr,
            "lth_sopr": self.lth_sopr,
            "total_outputs": self.total_outputs,
            "valid_outputs": self.valid_outputs,
            "sth_outputs": self.sth_outputs,
            "lth_outputs": self.lth_outputs,
            "total_btc_moved": self.total_btc_moved,
            "sth_btc_moved": self.sth_btc_moved,
            "lth_btc_moved": self.lth_btc_moved,
            "profit_outputs": self.profit_outputs,
            "loss_outputs": self.loss_outputs,
            "breakeven_outputs": self.breakeven_outputs,
            "profit_ratio": self.profit_ratio,
            "is_valid": self.is_valid,
            "min_samples": self.min_samples,
        }


# =============================================================================
# Pure Functions
# =============================================================================


def classify_cohort(age_days: int) -> str:
    """
    Classify output as STH or LTH based on age.

    Args:
        age_days: Days between UTXO creation and spend

    Returns:
        "STH" if age < threshold (155 days), "LTH" otherwise
    """
    threshold = get_sth_threshold()
    return "STH" if age_days < threshold else "LTH"


def classify_profit_loss(sopr: float) -> str:
    """
    Classify profit/loss based on SOPR value.

    Args:
        sopr: SOPR ratio value

    Returns:
        "PROFIT" if > 1.01, "LOSS" if < 0.99, "BREAKEVEN" otherwise
    """
    if sopr > 1.01:
        return "PROFIT"
    elif sopr < 0.99:
        return "LOSS"
    else:
        return "BREAKEVEN"


def calculate_output_sopr(
    creation_price: float,
    spend_price: float,
    btc_value: float,
    age_days: int,
) -> SpentOutputSOPR:
    """
    Calculate SOPR for a single spent output.

    SOPR = spend_price / creation_price

    Args:
        creation_price: USD price when UTXO was created
        spend_price: USD price when UTXO was spent
        btc_value: BTC amount of the output
        age_days: Days between creation and spend

    Returns:
        SpentOutputSOPR with calculated fields

    Examples:
        >>> output = calculate_output_sopr(50000.0, 100000.0, 1.0, 30)
        >>> output.sopr
        2.0
        >>> output.cohort
        'STH'
        >>> output.profit_loss
        'PROFIT'
    """
    import math

    # Validate prices - must be positive finite numbers
    # Note: NaN comparisons always return False, so we need explicit isnan/isinf checks
    def is_valid_price(price: float) -> bool:
        return price > 0 and not math.isnan(price) and not math.isinf(price)

    if not is_valid_price(creation_price) or not is_valid_price(spend_price):
        return SpentOutputSOPR(
            creation_price=creation_price,
            spend_price=spend_price,
            btc_value=btc_value,
            age_days=age_days,
            sopr=0.0,
            cohort=classify_cohort(age_days),
            profit_loss="",
            is_valid=False,
        )

    # Calculate SOPR
    sopr = spend_price / creation_price

    return SpentOutputSOPR(
        creation_price=creation_price,
        spend_price=spend_price,
        btc_value=btc_value,
        age_days=age_days,
        sopr=sopr,
        cohort=classify_cohort(age_days),
        profit_loss=classify_profit_loss(sopr),
        is_valid=True,
    )


def weighted_average(outputs: list[SpentOutputSOPR]) -> Optional[float]:
    """
    Calculate BTC-weighted average SOPR.

    Formula: sum(sopr_i * btc_i) / sum(btc_i)

    Args:
        outputs: List of SpentOutputSOPR objects

    Returns:
        Weighted average or None if no valid outputs or zero total BTC

    Examples:
        >>> outputs = [
        ...     calculate_output_sopr(50000, 100000, 1.0, 30),  # SOPR=2.0, 1 BTC
        ...     calculate_output_sopr(100000, 50000, 3.0, 30),  # SOPR=0.5, 3 BTC
        ... ]
        >>> weighted_average(outputs)  # (2.0*1 + 0.5*3) / 4 = 0.875
        0.875
    """
    if not outputs:
        return None

    total_value = sum(o.btc_value for o in outputs)
    if total_value == 0:
        return None

    return sum(o.sopr * o.btc_value for o in outputs) / total_value


def calculate_block_sopr(
    outputs: list[SpentOutputSOPR],
    block_height: int,
    block_hash: str,
    timestamp: datetime,
    min_samples: int = 100,
) -> BlockSOPR:
    """
    Aggregate individual outputs into block SOPR.

    Calculates BTC-weighted average SOPR for the entire block,
    split by STH/LTH cohorts.

    Args:
        outputs: List of SpentOutputSOPR for the block
        block_height: Bitcoin block height
        block_hash: Block hash
        timestamp: Block timestamp
        min_samples: Minimum outputs for valid SOPR (default: 100)

    Returns:
        BlockSOPR with aggregated metrics
    """
    # Filter valid outputs
    valid = [o for o in outputs if o.is_valid]
    sth = [o for o in valid if o.cohort == "STH"]
    lth = [o for o in valid if o.cohort == "LTH"]

    # Count profit/loss
    profit = [o for o in valid if o.profit_loss == "PROFIT"]
    loss = [o for o in valid if o.profit_loss == "LOSS"]
    breakeven = [o for o in valid if o.profit_loss == "BREAKEVEN"]

    return BlockSOPR(
        block_height=block_height,
        block_hash=block_hash,
        timestamp=timestamp,
        aggregate_sopr=weighted_average(valid) or 0.0,
        sth_sopr=weighted_average(sth),
        lth_sopr=weighted_average(lth),
        total_outputs=len(outputs),
        valid_outputs=len(valid),
        sth_outputs=len(sth),
        lth_outputs=len(lth),
        total_btc_moved=sum(o.btc_value for o in valid),
        sth_btc_moved=sum(o.btc_value for o in sth),
        lth_btc_moved=sum(o.btc_value for o in lth),
        profit_outputs=len(profit),
        loss_outputs=len(loss),
        breakeven_outputs=len(breakeven),
        profit_ratio=len(profit) / len(valid) if valid else 0.0,
        is_valid=len(valid) >= min_samples,
        min_samples=min_samples,
    )


def detect_sopr_signals(
    window: list[BlockSOPR],
    capitulation_days: int = 3,
    distribution_threshold: float = 3.0,
) -> dict:
    """
    Detect SOPR patterns from rolling window.

    Signals:
    - sth_capitulation: STH-SOPR < 1.0 for consecutive days (bullish)
    - sth_breakeven_cross: STH-SOPR crosses 1.0 from below
    - lth_distribution: LTH-SOPR > 3.0 (bearish cycle top warning)

    Signal Priority:
    1. LTH distribution overrides other signals (bearish)
    2. STH capitulation is strongest bullish signal
    3. Breakeven cross is moderate bullish signal

    Args:
        window: List of BlockSOPR (most recent last)
        capitulation_days: Days for capitulation signal (default: 3)
        distribution_threshold: LTH-SOPR threshold (default: 3.0)

    Returns:
        Dict with signal flags and sopr_vote (-1 to +1)
    """
    signals = {
        "sth_capitulation": False,
        "sth_breakeven_cross": False,
        "lth_distribution": False,
        "sopr_vote": 0.0,
    }

    if not window:
        return signals

    # Get recent STH-SOPR values (last N days)
    recent_sth = [
        b.sth_sopr for b in window[-capitulation_days:] if b.sth_sopr is not None
    ]

    # Check for STH capitulation (all below 1.0)
    if len(recent_sth) >= capitulation_days and all(s < 1.0 for s in recent_sth):
        signals["sth_capitulation"] = True
        signals["sopr_vote"] = 0.7  # Bullish contrarian

    # Check for breakeven cross (SOPR crosses 1.0 from below)
    # Detect if current STH-SOPR is above 1.0 and any recent value was below 1.0
    if len(window) >= 2:
        sth_values = [b.sth_sopr for b in window if b.sth_sopr is not None]
        if len(sth_values) >= 2:
            curr_sth = sth_values[-1]
            # Check if current is above 1.0 and any previous was below 1.0
            if curr_sth >= 1.0 and any(v < 1.0 for v in sth_values[:-1]):
                signals["sth_breakeven_cross"] = True
                if not signals["sth_capitulation"]:
                    signals["sopr_vote"] = 0.5  # Moderately bullish

    # Check for LTH distribution
    recent_lth = [b.lth_sopr for b in window[-7:] if b.lth_sopr is not None]
    if recent_lth and max(recent_lth) > distribution_threshold:
        signals["lth_distribution"] = True
        signals["sopr_vote"] = -0.7  # Bearish (overrides bullish)

    return signals


# =============================================================================
# Rolling Window Analysis
# =============================================================================


def analyze_rolling_window(
    blocks: list[BlockSOPR],
    window_size: int = 7,
) -> dict:
    """
    Analyze SOPR trends over a rolling window.

    Args:
        blocks: List of BlockSOPR sorted by time (oldest first)
        window_size: Number of blocks per window (default: 7 days)

    Returns:
        Dict with trend analysis:
        - sth_sopr_mean: Average STH-SOPR over window
        - sth_sopr_trend: "RISING", "FALLING", or "STABLE"
        - lth_sopr_mean: Average LTH-SOPR over window
        - consecutive_below_1: Days with STH-SOPR < 1.0
        - consecutive_above_1: Days with STH-SOPR > 1.0
    """
    if not blocks:
        return {
            "sth_sopr_mean": None,
            "sth_sopr_trend": "STABLE",
            "lth_sopr_mean": None,
            "consecutive_below_1": 0,
            "consecutive_above_1": 0,
        }

    # Get window
    window = blocks[-window_size:] if len(blocks) >= window_size else blocks

    # Extract STH/LTH SOPR values
    sth_values = [b.sth_sopr for b in window if b.sth_sopr is not None]
    lth_values = [b.lth_sopr for b in window if b.lth_sopr is not None]

    # Calculate means
    sth_mean = sum(sth_values) / len(sth_values) if sth_values else None
    lth_mean = sum(lth_values) / len(lth_values) if lth_values else None

    # Determine STH trend (simple slope)
    trend = "STABLE"
    if len(sth_values) >= 3:
        first_half = sum(sth_values[: len(sth_values) // 2]) / (len(sth_values) // 2)
        second_half = sum(sth_values[len(sth_values) // 2 :]) / (
            len(sth_values) - len(sth_values) // 2
        )
        diff = second_half - first_half
        if diff > 0.05:
            trend = "RISING"
        elif diff < -0.05:
            trend = "FALLING"

    # Count consecutive periods
    consecutive_below = 0
    consecutive_above = 0
    for val in reversed(sth_values):
        if val < 1.0:
            consecutive_below += 1
            if consecutive_above > 0:
                break
        else:
            consecutive_above += 1
            if consecutive_below > 0:
                break

    return {
        "sth_sopr_mean": sth_mean,
        "sth_sopr_trend": trend,
        "lth_sopr_mean": lth_mean,
        "consecutive_below_1": consecutive_below,
        "consecutive_above_1": consecutive_above,
    }
