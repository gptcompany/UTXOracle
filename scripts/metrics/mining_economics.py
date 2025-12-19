"""Mining Economics module (spec-030).

Implements Hash Ribbons and Mining Pulse indicators for miner stress analysis.

Hash Ribbons:
- 30d/60d MA crossover detection
- Miner capitulation/recovery signals
- Requires external API (mempool.space)

Mining Pulse:
- Real-time block interval analysis
- Hashrate change detection before difficulty adjusts
- Works RPC-only (no external dependencies)
"""

from datetime import datetime
from typing import Optional

from scripts.models.metrics_models import (
    MiningPulseZone,
    HashRibbonsResult,
    MiningPulseResult,
    MiningEconomicsResult,
)


# =============================================================================
# Mining Pulse (US1) - RPC-only
# =============================================================================


def classify_pulse_zone(avg_interval: float) -> MiningPulseZone:
    """Classify mining network status based on average block interval.

    Args:
        avg_interval: Average block interval in seconds

    Returns:
        MiningPulseZone classification

    Zone Thresholds:
        - FAST: < 540s (-10% from 600s target)
        - NORMAL: 540-660s (±10% from target)
        - SLOW: > 660s (+10% from target)
    """
    if avg_interval < 540:
        return MiningPulseZone.FAST
    elif avg_interval <= 660:
        return MiningPulseZone.NORMAL
    else:
        return MiningPulseZone.SLOW


def calculate_mining_pulse(rpc_client, window_blocks: int = 144) -> MiningPulseResult:
    """Calculate Mining Pulse from recent block intervals.

    Analyzes block timestamps to detect hashrate changes before
    difficulty adjusts. Works RPC-only with no external dependencies.

    Args:
        rpc_client: Bitcoin Core RPC client
        window_blocks: Number of blocks to analyze (default 144 = ~1 day)

    Returns:
        MiningPulseResult with interval analysis

    Raises:
        ConnectionError: If RPC connection fails
        ValueError: If window_blocks < 2
    """
    if window_blocks < 2:
        raise ValueError("window_blocks must be at least 2 to calculate intervals")

    # Get tip block
    tip_hash = rpc_client.getbestblockhash()
    tip_block = rpc_client.getblock(tip_hash)
    tip_height = tip_block["height"]

    # Collect block timestamps
    timestamps = []
    for height in range(tip_height - window_blocks + 1, tip_height + 1):
        block_hash = rpc_client.getblockhash(height)
        block = rpc_client.getblock(block_hash)
        timestamps.append(block["time"])

    # Calculate intervals
    intervals = []
    for i in range(1, len(timestamps)):
        interval = timestamps[i] - timestamps[i - 1]
        intervals.append(interval)

    # Calculate metrics
    avg_interval = sum(intervals) / len(intervals) if intervals else 600.0
    deviation_pct = (avg_interval - 600) / 600 * 100
    implied_hashrate_change = -deviation_pct  # Inverse relationship

    # Count fast/slow blocks
    blocks_fast = sum(1 for i in intervals if i < 600)
    blocks_slow = sum(1 for i in intervals if i >= 600)

    # Classify zone
    pulse_zone = classify_pulse_zone(avg_interval)

    return MiningPulseResult(
        avg_block_interval=avg_interval,
        interval_deviation_pct=deviation_pct,
        blocks_fast=blocks_fast,
        blocks_slow=blocks_slow,
        implied_hashrate_change=implied_hashrate_change,
        pulse_zone=pulse_zone,
        window_blocks=window_blocks,
        tip_height=tip_height,
        timestamp=datetime.utcnow(),
    )


# =============================================================================
# Hash Ribbons (US2) - External API
# =============================================================================


def count_capitulation_days(hashrate_data: dict) -> int:
    """Count consecutive days where 30d MA < 60d MA.

    Args:
        hashrate_data: Dict with 'hashrates' list from API

    Returns:
        Number of consecutive capitulation days from most recent
    """
    hashrates = hashrate_data.get("hashrates", [])
    if len(hashrates) < 60:
        return 0

    # Sort by timestamp descending (most recent first)
    sorted_data = sorted(hashrates, key=lambda x: x["timestamp"], reverse=True)

    # Calculate MAs for each day and count streak
    capitulation_days = 0

    for day_offset in range(len(sorted_data) - 59):
        # Get 30d and 60d windows
        data_30d = sorted_data[day_offset : day_offset + 30]
        data_60d = sorted_data[day_offset : day_offset + 60]

        if len(data_30d) < 30 or len(data_60d) < 60:
            break

        ma_30d = sum(d["avgHashrate"] for d in data_30d) / 30
        ma_60d = sum(d["avgHashrate"] for d in data_60d) / 60

        if ma_30d < ma_60d:
            capitulation_days += 1
        else:
            break  # Streak ended

    return capitulation_days


def calculate_hash_ribbons(hashrate_data: dict) -> HashRibbonsResult:
    """Calculate Hash Ribbons from hashrate data.

    Args:
        hashrate_data: Dict with 'hashrates' list and 'currentHashrate'

    Returns:
        HashRibbonsResult with MA crossover analysis
    """
    hashrates = hashrate_data.get("hashrates", [])
    current_hashrate = hashrate_data.get("currentHashrate", 0)

    # Convert to EH/s
    current_eh = current_hashrate / 1e18

    if len(hashrates) < 60:
        # Insufficient data
        return HashRibbonsResult(
            hashrate_current=current_eh,
            hashrate_ma_30d=current_eh,
            hashrate_ma_60d=current_eh,
            ribbon_signal=False,
            capitulation_days=0,
            recovery_signal=False,
            data_source="api",
            timestamp=datetime.utcnow(),
        )

    # Sort by timestamp descending
    sorted_data = sorted(hashrates, key=lambda x: x["timestamp"], reverse=True)

    # Calculate 30d and 60d MAs
    data_30d = sorted_data[:30]
    data_60d = sorted_data[:60]

    ma_30d = sum(d["avgHashrate"] for d in data_30d) / 30 / 1e18
    ma_60d = sum(d["avgHashrate"] for d in data_60d) / 60 / 1e18

    # Detect signals
    ribbon_signal = ma_30d < ma_60d
    capitulation_days = count_capitulation_days(hashrate_data) if ribbon_signal else 0

    # Check for recovery (30d just crossed above 60d)
    # Look at yesterday's data
    if len(sorted_data) >= 61:
        yesterday_30d = sorted_data[1:31]
        yesterday_60d = sorted_data[1:61]
        yesterday_ma_30d = sum(d["avgHashrate"] for d in yesterday_30d) / 30 / 1e18
        yesterday_ma_60d = sum(d["avgHashrate"] for d in yesterday_60d) / 60 / 1e18
        was_stressed = yesterday_ma_30d < yesterday_ma_60d
        recovery_signal = was_stressed and not ribbon_signal
    else:
        recovery_signal = False

    return HashRibbonsResult(
        hashrate_current=current_eh,
        hashrate_ma_30d=ma_30d,
        hashrate_ma_60d=ma_60d,
        ribbon_signal=ribbon_signal,
        capitulation_days=capitulation_days,
        recovery_signal=recovery_signal,
        data_source="api",
        timestamp=datetime.utcnow(),
    )


# =============================================================================
# Combined Mining Economics (US3)
# =============================================================================


def derive_combined_signal(
    ribbons: Optional[HashRibbonsResult], pulse: MiningPulseResult
) -> str:
    """Derive combined signal from Hash Ribbons and Mining Pulse.

    Signal Priority:
    1. recovery - Ribbons recovery signal (bullish)
    2. miner_stress - Ribbons 7+ days OR pulse SLOW
    3. healthy - Pulse FAST or no stress indicators
    4. unknown - No ribbon data and normal pulse

    Args:
        ribbons: HashRibbonsResult (may be None if API unavailable)
        pulse: MiningPulseResult (always available)

    Returns:
        One of: "recovery", "miner_stress", "healthy", "unknown"
    """
    # Check recovery first (highest priority)
    if ribbons and ribbons.recovery_signal:
        return "recovery"

    # Check miner stress from ribbons
    if ribbons and ribbons.ribbon_signal and ribbons.capitulation_days >= 7:
        return "miner_stress"

    # Check miner stress from slow pulse
    if pulse.pulse_zone == MiningPulseZone.SLOW:
        return "miner_stress"

    # Check healthy from fast pulse
    if pulse.pulse_zone == MiningPulseZone.FAST:
        return "healthy"

    # No ribbon data and normal pulse = unknown
    if ribbons is None:
        return "unknown"

    # Default to healthy if ribbons exist but no stress
    return "healthy"


def calculate_mining_economics(
    rpc_client, window_blocks: int = 144
) -> MiningEconomicsResult:
    """Calculate combined Mining Economics view.

    Combines Hash Ribbons (external API) with Mining Pulse (RPC-only)
    for comprehensive miner health assessment.

    Args:
        rpc_client: Bitcoin Core RPC client
        window_blocks: Number of blocks for Mining Pulse analysis

    Returns:
        MiningEconomicsResult with combined analysis
    """
    # Always calculate Mining Pulse (RPC-only)
    pulse = calculate_mining_pulse(rpc_client, window_blocks)

    # Try to get Hash Ribbons (external API)
    ribbons = None
    try:
        from scripts.data.hashrate_fetcher import fetch_hashrate_data

        hashrate_data = fetch_hashrate_data()
        ribbons = calculate_hash_ribbons(hashrate_data)
    except Exception:
        # API unavailable, continue with pulse only
        pass

    # Derive combined signal
    combined_signal = derive_combined_signal(ribbons, pulse)

    return MiningEconomicsResult(
        hash_ribbons=ribbons,
        mining_pulse=pulse,
        combined_signal=combined_signal,
        timestamp=datetime.utcnow(),
    )
