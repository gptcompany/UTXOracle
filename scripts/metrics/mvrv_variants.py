"""
MVRV-Z Score Variants (spec-038 extension).

Provides multiple MVRV-Z calculation methods for cross-validation:
- mvrv_z_1y: 1-year rolling stdev (UTXOracle default)
- mvrv_z_rbn: All-time stdev (RBN/Glassnode compatible)

The difference between formulas:
- 1-year: More responsive to recent volatility, higher Z-scores
- All-time: More stable, lower Z-scores, better cross-cycle comparison

Usage:
    from scripts.metrics.mvrv_variants import calculate_both_mvrv_z

    result = calculate_both_mvrv_z(conn, market_cap, realized_cap)
    print(f"1Y Z-Score: {result['mvrv_z_1y']:.2f}")
    print(f"RBN Z-Score: {result['mvrv_z_rbn']:.2f}")
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class MVRVZVariants:
    """Both MVRV-Z score variants."""

    mvrv_z_1y: float  # 1-year rolling stdev (UTXOracle default)
    mvrv_z_rbn: float  # All-time stdev (RBN compatible)
    history_days_1y: int  # Days used for 1Y calculation
    history_days_all: int  # Total days available
    std_1y: float  # 1-year standard deviation
    std_all: float  # All-time standard deviation


def get_market_cap_history_all_time(
    conn: Optional[duckdb.DuckDBPyConnection],
    max_block_height: Optional[int] = None,
    *,
    questdb_reads: bool = False,
) -> list[float]:
    """Get complete market cap history for all-time stdev.

    Reads from QuestDB ``utxo_snapshots`` when ``questdb_reads`` is True,
    otherwise from the legacy DuckDB connection.
    """
    if questdb_reads:
        from api.questdb_repository import _open_pg_sync

        query = "SELECT market_cap_usd FROM utxo_snapshots"
        params: tuple = ()
        if max_block_height is not None:
            query += " WHERE block_height <= %s"
            params = (max_block_height,)
        query += " ORDER BY block_height DESC"

        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [row[0] for row in rows if row[0] is not None]

    assert conn is not None, "DuckDB conn required when questdb_reads=False"
    query = """
        SELECT market_cap_usd
        FROM utxo_snapshots
    """
    params_list: list[int] = []
    if max_block_height is not None:
        query += " WHERE block_height <= ?"
        params_list.append(max_block_height)
    query += " ORDER BY block_height DESC"

    result = conn.execute(query, params_list).fetchall()
    return [row[0] for row in result if row[0] is not None]


def calculate_mvrv_z_with_stdev(
    market_cap: float,
    realized_cap: float,
    history: list[float],
    variant_name: str = "default",
) -> tuple[float, float]:
    """Calculate MVRV-Z and return both score and stdev.

    Args:
        market_cap: Current market cap in USD.
        realized_cap: Current realized cap in USD.
        history: Market cap history values.
        variant_name: Name for logging.

    Returns:
        Tuple of (mvrv_z, stdev). Returns (0.0, 0.0) on error.
    """
    if len(history) < 30:
        logger.warning(
            f"MVRV-Z {variant_name}: Insufficient history ({len(history)} < 30)"
        )
        return 0.0, 0.0

    try:
        std = statistics.stdev(history)
    except statistics.StatisticsError:
        logger.warning(f"MVRV-Z {variant_name}: Failed to calculate stdev")
        return 0.0, 0.0

    if std == 0:
        logger.warning(f"MVRV-Z {variant_name}: Zero stdev")
        return 0.0, 0.0

    mvrv_z = (market_cap - realized_cap) / std
    return mvrv_z, std


def calculate_both_mvrv_z(
    conn: Optional[duckdb.DuckDBPyConnection],
    market_cap: float,
    realized_cap: float,
    days_1y: int = 365,
    max_block_height: Optional[int] = None,
    *,
    questdb_reads: bool = False,
) -> MVRVZVariants:
    """Calculate both MVRV-Z variants."""
    all_history = get_market_cap_history_all_time(
        conn,
        max_block_height=max_block_height,
        questdb_reads=questdb_reads,
    )

    # 1-year subset
    history_1y = all_history[:days_1y] if len(all_history) >= days_1y else all_history

    # Calculate both variants
    mvrv_z_1y, std_1y = calculate_mvrv_z_with_stdev(
        market_cap, realized_cap, history_1y, "1Y"
    )
    mvrv_z_rbn, std_all = calculate_mvrv_z_with_stdev(
        market_cap, realized_cap, all_history, "RBN"
    )

    logger.info(
        f"MVRV-Z variants: 1Y={mvrv_z_1y:.2f} (std={std_1y:.0f}), "
        f"RBN={mvrv_z_rbn:.2f} (std={std_all:.0f})"
    )

    return MVRVZVariants(
        mvrv_z_1y=mvrv_z_1y,
        mvrv_z_rbn=mvrv_z_rbn,
        history_days_1y=len(history_1y),
        history_days_all=len(all_history),
        std_1y=std_1y,
        std_all=std_all,
    )


def get_mvrv_z_comparison(
    conn: duckdb.DuckDBPyConnection,
    market_cap: Optional[float] = None,
    realized_cap: Optional[float] = None,
) -> dict:
    """Get MVRV-Z comparison for validation.

    If market_cap/realized_cap not provided, fetches from latest snapshot.

    Args:
        conn: DuckDB connection.
        market_cap: Optional market cap override.
        realized_cap: Optional realized cap override.

    Returns:
        Dict with both variants and comparison info.
    """
    # Get latest values if not provided
    if market_cap is None or realized_cap is None:
        result = conn.execute(
            """
            SELECT market_cap_usd, realized_cap_usd
            FROM utxo_snapshots
            ORDER BY block_height DESC
            LIMIT 1
            """
        ).fetchone()

        if not result:
            return {"error": "No snapshot data available"}

        market_cap = result[0]
        realized_cap = result[1]

    variants = calculate_both_mvrv_z(conn, market_cap, realized_cap)

    # Calculate ratio between variants
    ratio = variants.mvrv_z_1y / variants.mvrv_z_rbn if variants.mvrv_z_rbn != 0 else 0

    return {
        "mvrv_z_1y": variants.mvrv_z_1y,
        "mvrv_z_rbn": variants.mvrv_z_rbn,
        "ratio_1y_to_rbn": ratio,
        "std_1y": variants.std_1y,
        "std_all_time": variants.std_all,
        "history_days_1y": variants.history_days_1y,
        "history_days_all": variants.history_days_all,
        "market_cap_usd": market_cap,
        "realized_cap_usd": realized_cap,
        "recommendation": "Use mvrv_z_rbn for RBN validation, mvrv_z_1y for signals",
    }
