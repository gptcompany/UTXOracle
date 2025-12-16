"""
STH/LTH Cost Basis Calculator (spec-023).

Calculates weighted average cost basis for Short-Term Holders (STH) and
Long-Term Holders (LTH) cohorts. Cost basis represents the average acquisition
price weighted by BTC value, providing key support/resistance levels.

Formula:
    Cost Basis = SUM(creation_price_usd × btc_value) / SUM(btc_value)
               = SUM(realized_value_usd) / SUM(btc_value)

Cohort Boundaries:
    - STH: UTXOs created < 155 days ago (22,320 blocks)
    - LTH: UTXOs created >= 155 days ago

Signal Interpretation:
    - Price < STH Cost Basis: STH underwater → capitulation risk
    - Price > LTH Cost Basis: LTH in profit → distribution risk
    - STH Cost Basis: Key short-term support level
    - LTH Cost Basis: Macro support level

Dependencies:
    - DuckDB connection with utxo_lifecycle_full VIEW
    - scripts.models.metrics_models.CostBasisResult

Usage:
    >>> from scripts.metrics.cost_basis import calculate_cost_basis_signal
    >>> import duckdb
    >>> conn = duckdb.connect("data/utxo_lifecycle.duckdb")
    >>> result = calculate_cost_basis_signal(
    ...     conn=conn,
    ...     current_block=875000,
    ...     current_price_usd=95000.0
    ... )
    >>> print(f"STH Cost Basis: ${result.sth_cost_basis:,.2f}")
"""

from datetime import datetime
from typing import Optional

from scripts.models.metrics_models import CostBasisResult


# STH/LTH threshold in blocks (155 days × 144 blocks/day)
STH_THRESHOLD_BLOCKS = 155 * 144  # 22,320 blocks


def calculate_sth_cost_basis(
    conn,
    current_block: int,
) -> dict:
    """Calculate weighted average cost basis for Short-Term Holders.

    STH = UTXOs created within the last 155 days (22,320 blocks).

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        current_block: Current Bitcoin block height.

    Returns:
        Dict with 'sth_cost_basis' and 'sth_supply_btc'.
        Returns 0.0 for both if no matching UTXOs found.
    """
    cutoff_block = current_block - STH_THRESHOLD_BLOCKS

    result = conn.execute(
        """
        SELECT
            COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS sth_cost_basis,
            COALESCE(SUM(btc_value), 0) AS sth_supply_btc
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND creation_block > ?
          AND creation_price_usd IS NOT NULL
          AND btc_value > 0
        """,
        [cutoff_block],
    ).fetchone()

    return {
        "sth_cost_basis": result[0] if result else 0.0,
        "sth_supply_btc": result[1] if result else 0.0,
    }


def calculate_lth_cost_basis(
    conn,
    current_block: int,
) -> dict:
    """Calculate weighted average cost basis for Long-Term Holders.

    LTH = UTXOs created more than 155 days ago (>22,320 blocks).

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        current_block: Current Bitcoin block height.

    Returns:
        Dict with 'lth_cost_basis' and 'lth_supply_btc'.
        Returns 0.0 for both if no matching UTXOs found.
    """
    cutoff_block = current_block - STH_THRESHOLD_BLOCKS

    result = conn.execute(
        """
        SELECT
            COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS lth_cost_basis,
            COALESCE(SUM(btc_value), 0) AS lth_supply_btc
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND creation_block <= ?
          AND creation_price_usd IS NOT NULL
          AND btc_value > 0
        """,
        [cutoff_block],
    ).fetchone()

    return {
        "lth_cost_basis": result[0] if result else 0.0,
        "lth_supply_btc": result[1] if result else 0.0,
    }


def calculate_total_cost_basis(conn) -> dict:
    """Calculate weighted average cost basis for all unspent UTXOs.

    This is the overall realized price (similar to realized cap / supply).

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.

    Returns:
        Dict with 'total_cost_basis'.
        Returns 0.0 if no matching UTXOs found.
    """
    result = conn.execute(
        """
        SELECT
            COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS total_cost_basis
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
          AND creation_price_usd IS NOT NULL
          AND btc_value > 0
        """
    ).fetchone()

    return {
        "total_cost_basis": result[0] if result else 0.0,
    }


def calculate_cost_basis_mvrv(
    current_price_usd: float,
    cost_basis: float,
) -> float:
    """Calculate MVRV ratio from price and cost basis.

    MVRV = current_price / cost_basis

    Args:
        current_price_usd: Current BTC price in USD.
        cost_basis: Weighted average acquisition price.

    Returns:
        MVRV ratio. Returns 0.0 if cost_basis is 0 (avoids division by zero).
    """
    if cost_basis <= 0:
        return 0.0
    return current_price_usd / cost_basis


def calculate_cost_basis_signal(
    conn,
    current_block: int,
    current_price_usd: float,
    timestamp: Optional[datetime] = None,
) -> CostBasisResult:
    """Calculate complete cost basis signal with MVRV ratios.

    Orchestrates the calculation of STH/LTH cost basis and derives
    cohort-specific MVRV ratios for market positioning signals.

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        current_block: Current Bitcoin block height.
        current_price_usd: Current BTC price in USD.
        timestamp: Calculation timestamp (defaults to now).

    Returns:
        CostBasisResult with all metrics populated.

    Example:
        >>> result = calculate_cost_basis_signal(conn, 875000, 95000.0)
        >>> print(f"STH MVRV: {result.sth_mvrv:.2f}")
        >>> if result.sth_mvrv < 1.0:
        ...     print("STH underwater - capitulation risk")
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    # Calculate cohort cost basis
    sth_data = calculate_sth_cost_basis(conn, current_block)
    lth_data = calculate_lth_cost_basis(conn, current_block)
    total_data = calculate_total_cost_basis(conn)

    # Calculate MVRV ratios
    sth_mvrv = calculate_cost_basis_mvrv(current_price_usd, sth_data["sth_cost_basis"])
    lth_mvrv = calculate_cost_basis_mvrv(current_price_usd, lth_data["lth_cost_basis"])

    # Calculate confidence based on data availability
    total_supply = sth_data["sth_supply_btc"] + lth_data["lth_supply_btc"]
    if (
        total_supply > 0
        and sth_data["sth_cost_basis"] > 0
        and lth_data["lth_cost_basis"] > 0
    ):
        confidence = 0.85  # High confidence - full data available
    elif total_supply > 0:
        confidence = 0.5  # Medium confidence - partial data
    else:
        confidence = 0.0  # No confidence - no data

    return CostBasisResult(
        sth_cost_basis=sth_data["sth_cost_basis"],
        lth_cost_basis=lth_data["lth_cost_basis"],
        total_cost_basis=total_data["total_cost_basis"],
        sth_mvrv=sth_mvrv,
        lth_mvrv=lth_mvrv,
        sth_supply_btc=sth_data["sth_supply_btc"],
        lth_supply_btc=lth_data["lth_supply_btc"],
        current_price_usd=current_price_usd,
        block_height=current_block,
        timestamp=timestamp,
        confidence=confidence,
    )
