"""
Absorption Rates Calculator (spec-025).

Calculates the rate at which each wallet band absorbs newly mined supply.
Requires comparing two wallet waves snapshots (current vs historical).

Key Functions:
- calculate_mined_supply: Calculate new BTC mined in a time window
- calculate_absorption_rates: Calculate absorption rates across all bands

Usage:
    from scripts.metrics.absorption_rates import calculate_absorption_rates
    from scripts.metrics.wallet_waves import calculate_wallet_waves
    import duckdb

    conn = duckdb.connect("data/utxoracle.db", read_only=True)
    current = calculate_wallet_waves(conn, block_height=876543)
    historical = calculate_wallet_waves(conn, block_height=876543 - 144*30)

    result = calculate_absorption_rates(
        conn=conn,
        current_snapshot=current,
        historical_snapshot=historical,
        window_days=30
    )
    print(f"Dominant absorber: {result.dominant_absorber.value}")
"""

from datetime import datetime, timezone
from typing import Any, Optional

from scripts.models.metrics_models import (
    AbsorptionRateMetrics,
    AbsorptionRatesResult,
    WalletBand,
    WalletWavesResult,
)


# Bitcoin block reward constants
BLOCK_REWARD_BTC = 3.125  # Post-halving April 2024 (halving #4)
BLOCKS_PER_DAY = 144  # Average


def calculate_mined_supply(window_days: int) -> float:
    """Calculate new BTC mined during a time window.

    Uses current block reward (3.125 BTC post-2024 halving) and average block rate (144/day).

    Args:
        window_days: Number of days in window.

    Returns:
        Total BTC mined during window.

    Raises:
        ValueError: If window_days is not positive.
    """
    if window_days <= 0:
        raise ValueError(f"window_days must be positive, got {window_days}")

    return BLOCK_REWARD_BTC * BLOCKS_PER_DAY * window_days


def calculate_absorption_rates(
    conn: Any,
    current_snapshot: WalletWavesResult,
    historical_snapshot: Optional[WalletWavesResult],
    window_days: int,
    timestamp: Optional[datetime] = None,
) -> AbsorptionRatesResult:
    """Calculate absorption rates across all wallet bands.

    Compares current snapshot to historical snapshot and calculates
    how much of newly mined supply each band absorbed.

    Args:
        conn: DuckDB connection (unused currently, for future extensions).
        current_snapshot: Current wallet waves distribution.
        historical_snapshot: Historical snapshot (None if unavailable).
        window_days: Lookback window in days.
        timestamp: Optional timestamp (defaults to now).

    Returns:
        AbsorptionRatesResult with rates for all bands.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    mined_supply_btc = calculate_mined_supply(window_days)
    has_historical_data = historical_snapshot is not None

    # Build band metrics
    band_metrics: list[AbsorptionRateMetrics] = []
    max_absorption_rate: float | None = None
    dominant_absorber = WalletBand.SHRIMP  # Default

    for band in WalletBand:
        # Get current supply for this band
        current_band = next((b for b in current_snapshot.bands if b.band == band), None)
        current_supply = current_band.supply_btc if current_band else 0.0

        if has_historical_data:
            # Get historical supply for this band
            historical_band = next(
                (b for b in historical_snapshot.bands if b.band == band), None
            )
            historical_supply = historical_band.supply_btc if historical_band else 0.0

            # Calculate delta and absorption rate
            supply_delta = current_supply - historical_supply

            if mined_supply_btc > 0:
                absorption_rate = supply_delta / mined_supply_btc
            else:
                absorption_rate = 0.0

            # Track dominant absorber
            if absorption_rate is not None:
                if max_absorption_rate is None or absorption_rate > max_absorption_rate:
                    max_absorption_rate = absorption_rate
                    dominant_absorber = band
        else:
            # No historical data - deltas are unknown
            historical_supply = 0.0
            supply_delta = 0.0
            absorption_rate = None

        band_metrics.append(
            AbsorptionRateMetrics(
                band=band,
                absorption_rate=absorption_rate,
                supply_delta_btc=supply_delta,
                supply_start_btc=historical_supply if has_historical_data else 0.0,
                supply_end_btc=current_supply,
            )
        )

    # Calculate retail vs institutional absorption
    retail_bands = [WalletBand.SHRIMP, WalletBand.CRAB, WalletBand.FISH]
    institutional_bands = [WalletBand.SHARK, WalletBand.WHALE, WalletBand.HUMPBACK]

    if has_historical_data and mined_supply_btc > 0:
        retail_delta = sum(
            b.supply_delta_btc for b in band_metrics if b.band in retail_bands
        )
        institutional_delta = sum(
            b.supply_delta_btc for b in band_metrics if b.band in institutional_bands
        )
        retail_absorption = retail_delta / mined_supply_btc
        institutional_absorption = institutional_delta / mined_supply_btc
    else:
        retail_absorption = 0.0
        institutional_absorption = 0.0

    # Calculate confidence based on data availability
    confidence = 0.85 if has_historical_data else 0.3

    return AbsorptionRatesResult(
        timestamp=timestamp,
        block_height=current_snapshot.block_height,
        window_days=window_days,
        mined_supply_btc=mined_supply_btc,
        bands=band_metrics,
        dominant_absorber=dominant_absorber,
        retail_absorption=retail_absorption,
        institutional_absorption=institutional_absorption,
        confidence=confidence,
        has_historical_data=has_historical_data,
    )
