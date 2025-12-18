"""
Wallet Waves Distribution Calculator (spec-025).

Calculates supply distribution across 6 wallet size bands (shrimp to humpback)
using the utxo_lifecycle_full VIEW for address-based balance aggregation.

Key Functions:
- classify_balance_to_band: Classify a balance into a wallet band
- calculate_wallet_waves: Calculate complete distribution snapshot

Usage:
    from scripts.metrics.wallet_waves import calculate_wallet_waves
    import duckdb

    conn = duckdb.connect("data/utxoracle.db", read_only=True)
    result = calculate_wallet_waves(conn, block_height=876543)
    print(f"Retail: {result.retail_supply_pct:.2f}%")
    print(f"Institutional: {result.institutional_supply_pct:.2f}%")
"""

from datetime import datetime, timezone
from typing import Any

from scripts.models.metrics_models import (
    BAND_THRESHOLDS,
    WalletBand,
    WalletBandMetrics,
    WalletWavesResult,
)


def classify_balance_to_band(balance: float) -> WalletBand:
    """Classify a BTC balance into a wallet band.

    Uses the standard 6-band classification (Glassnode-aligned):
    - SHRIMP: < 1 BTC
    - CRAB: 1-10 BTC
    - FISH: 10-100 BTC
    - SHARK: 100-1,000 BTC
    - WHALE: 1,000-10,000 BTC
    - HUMPBACK: > 10,000 BTC

    Args:
        balance: BTC balance to classify.

    Returns:
        WalletBand enum value.

    Raises:
        ValueError: If balance is negative.
    """
    if balance < 0:
        raise ValueError(f"balance must be non-negative, got {balance}")

    for band, (min_btc, max_btc) in BAND_THRESHOLDS.items():
        if min_btc <= balance < max_btc:
            return band

    # Should not reach here if BAND_THRESHOLDS is correctly defined
    return WalletBand.HUMPBACK


def calculate_wallet_waves(
    conn: Any,
    block_height: int | None = None,
    timestamp: datetime | None = None,
) -> WalletWavesResult:
    """Calculate wallet waves distribution snapshot.

    Aggregates unspent UTXOs by address balance and classifies into 6 bands.

    Args:
        conn: DuckDB connection object.
        block_height: Optional block height (defaults to latest).
        timestamp: Optional timestamp (defaults to now).

    Returns:
        WalletWavesResult with complete distribution.

    Raises:
        ValueError: If no UTXO data found.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Query: Aggregate balance per address, then classify into bands
    # This is a two-step aggregation:
    # 1. Sum UTXOs by address
    # 2. Classify addresses into bands and aggregate
    query = """
    WITH address_balances AS (
        SELECT
            address,
            SUM(btc_value) AS balance
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND address IS NOT NULL
        GROUP BY address
        HAVING balance > 0
    )
    SELECT
        CASE
            WHEN balance < 1 THEN 'shrimp'
            WHEN balance < 10 THEN 'crab'
            WHEN balance < 100 THEN 'fish'
            WHEN balance < 1000 THEN 'shark'
            WHEN balance < 10000 THEN 'whale'
            ELSE 'humpback'
        END AS band,
        COUNT(*) AS address_count,
        SUM(balance) AS supply_btc,
        AVG(balance) AS avg_balance
    FROM address_balances
    GROUP BY band
    ORDER BY
        CASE band
            WHEN 'shrimp' THEN 1
            WHEN 'crab' THEN 2
            WHEN 'fish' THEN 3
            WHEN 'shark' THEN 4
            WHEN 'whale' THEN 5
            WHEN 'humpback' THEN 6
        END;
    """

    result = conn.execute(query).fetchall()

    if not result:
        raise ValueError("No UTXO data found in database")

    # Query total supply and null address BTC
    total_query = """
    SELECT
        SUM(btc_value) AS total_supply
    FROM utxo_lifecycle_full
    WHERE is_spent = FALSE;
    """
    total_result = conn.execute(total_query).fetchone()
    total_supply_btc = total_result[0] if total_result and total_result[0] else 0.0

    null_query = """
    SELECT
        COALESCE(SUM(btc_value), 0) AS null_address_btc
    FROM utxo_lifecycle_full
    WHERE is_spent = FALSE AND address IS NULL;
    """
    null_result = conn.execute(null_query).fetchone()
    null_address_btc = null_result[0] if null_result else 0.0

    # Get block height if not provided
    if block_height is None:
        height_query = """
        SELECT MAX(creation_block) FROM utxo_lifecycle_full WHERE is_spent = FALSE;
        """
        height_result = conn.execute(height_query).fetchone()
        block_height = height_result[0] if height_result and height_result[0] else 0

    # Build band metrics dict from query results
    band_data: dict[str, tuple[int, float, float]] = {}
    for row in result:
        band_name, address_count, supply_btc, avg_balance = row
        band_data[band_name] = (address_count, supply_btc, avg_balance)

    # Create WalletBandMetrics for each band (ensure all 6 are present)
    bands: list[WalletBandMetrics] = []
    address_count_total = 0

    for band in WalletBand:
        band_name = band.value
        if band_name in band_data:
            address_count, supply_btc, avg_balance = band_data[band_name]
        else:
            # Band has no data - use zeros
            address_count, supply_btc, avg_balance = 0, 0.0, 0.0

        # Calculate percentage
        supply_pct = (
            (supply_btc / total_supply_btc * 100) if total_supply_btc > 0 else 0.0
        )

        bands.append(
            WalletBandMetrics(
                band=band,
                supply_btc=supply_btc,
                supply_pct=supply_pct,
                address_count=address_count,
                avg_balance=avg_balance,
            )
        )
        address_count_total += address_count

    # Calculate retail vs institutional
    retail_bands = [WalletBand.SHRIMP, WalletBand.CRAB, WalletBand.FISH]
    institutional_bands = [WalletBand.SHARK, WalletBand.WHALE, WalletBand.HUMPBACK]
    retail_supply_pct = sum(b.supply_pct for b in bands if b.band in retail_bands)
    institutional_supply_pct = sum(
        b.supply_pct for b in bands if b.band in institutional_bands
    )

    # Calculate confidence based on data completeness
    # Lower confidence if significant BTC is in null addresses
    if total_supply_btc > 0:
        null_pct = null_address_btc / total_supply_btc
        confidence = max(0.5, 1.0 - null_pct)
    else:
        confidence = 0.0

    return WalletWavesResult(
        timestamp=timestamp,
        block_height=block_height,
        total_supply_btc=total_supply_btc,
        bands=bands,
        retail_supply_pct=retail_supply_pct,
        institutional_supply_pct=institutional_supply_pct,
        address_count_total=address_count_total,
        null_address_btc=null_address_btc,
        confidence=confidence,
    )
