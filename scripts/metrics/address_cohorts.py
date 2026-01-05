"""
Address Balance Cohorts Calculator (spec-039).

Calculates cost basis, MVRV, and supply metrics segmented by address balance size.
Three cohorts: whale (>=100 BTC), mid-tier (1-100 BTC), retail (<1 BTC).

Reveals accumulation/distribution patterns and conviction levels by comparing
cost basis and MVRV across cohorts. Whales with lower cost basis than retail
indicates smart money conviction.

Algorithm:
    1. Group UTXOs by address to calculate per-address balance
    2. Classify addresses into cohorts based on total balance
    3. Calculate weighted cost basis for each cohort
    4. Derive MVRV and cross-cohort signals

Cohort Thresholds:
    - RETAIL: < 1 BTC
    - MID_TIER: 1-100 BTC
    - WHALE: >= 100 BTC

Dependencies:
    - DuckDB connection with utxo_lifecycle_full VIEW
    - scripts.models.metrics_models.AddressCohortsResult

Usage:
    >>> from scripts.metrics.address_cohorts import calculate_address_cohorts
    >>> import duckdb
    >>> conn = duckdb.connect("data/utxo_lifecycle.duckdb")
    >>> result = calculate_address_cohorts(
    ...     conn=conn,
    ...     current_block=875000,
    ...     current_price_usd=95000.0
    ... )
    >>> print(f"Whale Cost Basis: ${result.whale.cost_basis:,.2f}")
    >>> print(f"Whale-Retail Spread: ${result.whale_retail_spread:,.2f}")

Spec: spec-039
"""

from datetime import datetime

from scripts.models.metrics_models import (
    AddressCohort,
    CohortMetrics,
    AddressCohortsResult,
)


# Cohort balance thresholds (in BTC)
RETAIL_THRESHOLD = 1.0  # < 1 BTC
WHALE_THRESHOLD = 100.0  # >= 100 BTC


def _classify_cohort(balance: float) -> AddressCohort:
    """Classify address balance into cohort.

    Args:
        balance: Total BTC balance for an address.

    Returns:
        AddressCohort enum value (RETAIL, MID_TIER, or WHALE).

    Examples:
        >>> _classify_cohort(0.5)
        AddressCohort.RETAIL
        >>> _classify_cohort(50.0)
        AddressCohort.MID_TIER
        >>> _classify_cohort(500.0)
        AddressCohort.WHALE
    """
    if balance < RETAIL_THRESHOLD:
        return AddressCohort.RETAIL
    elif balance < WHALE_THRESHOLD:
        return AddressCohort.MID_TIER
    else:
        return AddressCohort.WHALE


def _calculate_mvrv(current_price: float, cost_basis: float) -> float:
    """Calculate Market Value to Realized Value ratio.

    MVRV = current_price / cost_basis

    Args:
        current_price: Current BTC price in USD.
        cost_basis: Weighted average acquisition price.

    Returns:
        MVRV ratio, or 0.0 if cost_basis or current_price is zero or negative.

    Examples:
        >>> _calculate_mvrv(95000.0, 50000.0)
        1.9
        >>> _calculate_mvrv(95000.0, 0.0)
        0.0
        >>> _calculate_mvrv(-100.0, 50000.0)
        0.0
    """
    if cost_basis <= 0 or current_price <= 0:
        return 0.0
    return current_price / cost_basis


def _calculate_cross_cohort_signals(
    whale: CohortMetrics,
    retail: CohortMetrics,
) -> tuple[float, float]:
    """Calculate cross-cohort analysis signals.

    Args:
        whale: Whale cohort metrics.
        retail: Retail cohort metrics.

    Returns:
        Tuple of (whale_retail_spread, whale_retail_mvrv_ratio).
        - whale_retail_spread: whale_cost_basis - retail_cost_basis
        - whale_retail_mvrv_ratio: whale_mvrv / retail_mvrv

    Signal Interpretation:
        - Spread < 0: Whales bought at lower prices (conviction)
        - Spread > 0: Retail bought at lower prices
        - MVRV ratio > 1: Whales more profitable than retail
    """
    # Cost basis spread
    whale_retail_spread = whale.cost_basis - retail.cost_basis

    # MVRV ratio
    if retail.mvrv > 0:
        whale_retail_mvrv_ratio = whale.mvrv / retail.mvrv
    else:
        whale_retail_mvrv_ratio = 0.0

    return whale_retail_spread, whale_retail_mvrv_ratio


def calculate_address_cohorts(
    conn,
    current_block: int,
    current_price_usd: float,
) -> AddressCohortsResult:
    """Calculate address balance cohort metrics.

    Performs two-stage SQL aggregation:
    1. Group UTXOs by address to get per-address balance and cost basis numerator
    2. Classify addresses into cohorts and aggregate metrics

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        current_block: Current Bitcoin block height.
        current_price_usd: Current BTC price for MVRV calculation.

    Returns:
        AddressCohortsResult with per-cohort metrics and cross-cohort signals.

    Example:
        >>> result = calculate_address_cohorts(conn, 875000, 95000.0)
        >>> print(f"Whale supply: {result.whale.supply_btc:,.0f} BTC")
        >>> print(f"Whale-Retail spread: ${result.whale_retail_spread:,.2f}")
    """
    # Two-stage SQL aggregation
    query = """
    WITH address_balances AS (
        SELECT
            address,
            SUM(btc_value) AS balance,
            SUM(creation_price_usd * btc_value) AS cost_numerator,
            SUM(btc_value) AS cost_denominator
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND address IS NOT NULL
          AND creation_price_usd IS NOT NULL
          AND btc_value > 0
        GROUP BY address
    ),
    cohort_classified AS (
        SELECT
            address,
            balance,
            cost_numerator,
            cost_denominator,
            CASE
                WHEN balance < 1 THEN 'retail'
                WHEN balance < 100 THEN 'mid_tier'
                ELSE 'whale'
            END AS cohort
        FROM address_balances
    )
    SELECT
        cohort,
        COALESCE(SUM(cost_numerator) / NULLIF(SUM(cost_denominator), 0), 0) AS cost_basis,
        COALESCE(SUM(balance), 0) AS supply_btc,
        COUNT(DISTINCT address) AS address_count
    FROM cohort_classified
    GROUP BY cohort
    """

    results = conn.execute(query).fetchall()

    # Initialize empty cohort data
    cohort_data = {
        "retail": {"cost_basis": 0.0, "supply_btc": 0.0, "address_count": 0},
        "mid_tier": {"cost_basis": 0.0, "supply_btc": 0.0, "address_count": 0},
        "whale": {"cost_basis": 0.0, "supply_btc": 0.0, "address_count": 0},
    }

    # Populate from query results
    for row in results:
        cohort_name, cost_basis, supply_btc, address_count = row
        if cohort_name in cohort_data:
            cohort_data[cohort_name] = {
                "cost_basis": cost_basis or 0.0,
                "supply_btc": supply_btc or 0.0,
                "address_count": address_count or 0,
            }

    # Calculate totals
    total_supply = sum(c["supply_btc"] for c in cohort_data.values())
    total_addresses = sum(c["address_count"] for c in cohort_data.values())

    # Build CohortMetrics for each cohort
    def build_cohort_metrics(cohort_enum: AddressCohort, data: dict) -> CohortMetrics:
        supply_pct = (
            (data["supply_btc"] / total_supply * 100) if total_supply > 0 else 0.0
        )
        mvrv = _calculate_mvrv(current_price_usd, data["cost_basis"])

        return CohortMetrics(
            cohort=cohort_enum,
            cost_basis=data["cost_basis"],
            supply_btc=data["supply_btc"],
            supply_pct=supply_pct,
            mvrv=mvrv,
            address_count=data["address_count"],
        )

    retail = build_cohort_metrics(AddressCohort.RETAIL, cohort_data["retail"])
    mid_tier = build_cohort_metrics(AddressCohort.MID_TIER, cohort_data["mid_tier"])
    whale = build_cohort_metrics(AddressCohort.WHALE, cohort_data["whale"])

    # Calculate cross-cohort signals
    whale_retail_spread, whale_retail_mvrv_ratio = _calculate_cross_cohort_signals(
        whale, retail
    )

    return AddressCohortsResult(
        timestamp=datetime.utcnow(),
        block_height=current_block,
        current_price_usd=current_price_usd,
        retail=retail,
        mid_tier=mid_tier,
        whale=whale,
        whale_retail_spread=whale_retail_spread,
        whale_retail_mvrv_ratio=whale_retail_mvrv_ratio,
        total_supply_btc=total_supply,
        total_addresses=total_addresses,
    )
