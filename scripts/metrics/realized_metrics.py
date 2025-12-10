"""Realized Metrics Module.

This module calculates realized-value based metrics from UTXO lifecycle data:
- Realized Cap: Sum of UTXO values at creation price
- MVRV: Market Value to Realized Value ratio
- NUPL: Net Unrealized Profit/Loss

These are Tier A metrics with high predictive value for market analysis.

Spec: spec-017
Created: 2025-12-09
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import duckdb

if TYPE_CHECKING:
    from scripts.models.metrics_models import UTXOSetSnapshot

logger = logging.getLogger(__name__)

# =============================================================================
# TTL Cache for API Performance (T063)
# =============================================================================

# Cache TTL in seconds (5 minutes - shorter than 10-min cron interval)
CACHE_TTL_SECONDS = 300

# Simple module-level cache for frequently accessed data
_snapshot_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str) -> Any | None:
    """Get value from cache if not expired."""
    if key in _snapshot_cache:
        timestamp, value = _snapshot_cache[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
        # Expired, remove from cache
        del _snapshot_cache[key]
    return None


def _set_cached(key: str, value: Any) -> None:
    """Set value in cache with current timestamp."""
    _snapshot_cache[key] = (time.time(), value)


def clear_cache() -> None:
    """Clear all cached data. Call after sync operations."""
    _snapshot_cache.clear()
    logger.debug("Realized metrics cache cleared")


def calculate_realized_cap(conn: duckdb.DuckDBPyConnection) -> float:
    """Calculate Realized Cap from unspent UTXOs.

    Realized Cap = Sum of (UTXO_value × creation_price) for all unspent UTXOs.

    Args:
        conn: DuckDB connection.

    Returns:
        Realized Cap in USD.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(realized_value_usd), 0)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
        """,
    ).fetchone()

    return result[0] if result else 0.0


def calculate_market_cap(total_supply_btc: float, current_price_usd: float) -> float:
    """Calculate Market Cap.

    Market Cap = Total Supply × Current Price.

    Args:
        total_supply_btc: Total BTC supply.
        current_price_usd: Current BTC price in USD.

    Returns:
        Market Cap in USD.

    Raises:
        ValueError: If price is negative.
    """
    # B7 fix: Guard against negative price values
    if current_price_usd < 0:
        raise ValueError(f"Invalid negative price: {current_price_usd}")
    return total_supply_btc * current_price_usd


def calculate_mvrv(market_cap_usd: float, realized_cap_usd: float) -> float:
    """Calculate MVRV ratio.

    MVRV = Market Cap / Realized Cap

    Interpretation:
    - MVRV > 3.7: Historically indicates market tops
    - MVRV < 1.0: Market trading below aggregate cost basis (capitulation)
    - MVRV = 1.0: Market at cost basis

    Args:
        market_cap_usd: Market Cap in USD.
        realized_cap_usd: Realized Cap in USD.

    Returns:
        MVRV ratio.
    """
    if realized_cap_usd <= 0:
        return 0.0
    return market_cap_usd / realized_cap_usd


def calculate_nupl(market_cap_usd: float, realized_cap_usd: float) -> float:
    """Calculate NUPL (Net Unrealized Profit/Loss).

    NUPL = (Market Cap - Realized Cap) / Market Cap

    Interpretation:
    - NUPL > 0.75: Euphoria/Greed (historically indicates tops)
    - NUPL 0.5-0.75: Belief/Denial
    - NUPL 0.25-0.5: Optimism/Anxiety
    - NUPL 0-0.25: Hope/Fear
    - NUPL < 0: Capitulation (historically indicates bottoms)

    Args:
        market_cap_usd: Market Cap in USD.
        realized_cap_usd: Realized Cap in USD.

    Returns:
        NUPL value (-1 to 1 range typically).
    """
    if market_cap_usd <= 0:
        return 0.0
    return (market_cap_usd - realized_cap_usd) / market_cap_usd


def get_total_unspent_supply(conn: duckdb.DuckDBPyConnection) -> float:
    """Get total BTC supply in unspent UTXOs.

    Args:
        conn: DuckDB connection.

    Returns:
        Total BTC in unspent UTXOs.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(btc_value), 0)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
        """,
    ).fetchone()

    return result[0] if result else 0.0


def create_snapshot(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    timestamp: datetime,
    current_price_usd: float,
    hodl_waves: dict[str, float] | None = None,
) -> UTXOSetSnapshot:
    """Create a point-in-time snapshot of UTXO set metrics.

    Args:
        conn: DuckDB connection.
        block_height: Current block height.
        timestamp: Current block timestamp.
        current_price_usd: Current BTC price in USD.
        hodl_waves: Optional pre-calculated HODL waves.

    Returns:
        UTXOSetSnapshot with all metrics.
    """
    from scripts.metrics.utxo_lifecycle import get_sth_lth_supply, get_supply_by_cohort
    from scripts.models.metrics_models import AgeCohortsConfig, UTXOSetSnapshot

    # Calculate supply metrics
    total_supply = get_total_unspent_supply(conn)
    sth_supply, lth_supply = get_sth_lth_supply(conn, block_height)

    # Calculate supply by cohort
    config = AgeCohortsConfig()
    supply_by_cohort = get_supply_by_cohort(conn, block_height, config)

    # Calculate realized metrics
    realized_cap = calculate_realized_cap(conn)
    market_cap = calculate_market_cap(total_supply, current_price_usd)
    mvrv = calculate_mvrv(market_cap, realized_cap)
    nupl = calculate_nupl(market_cap, realized_cap)

    # Calculate HODL waves if not provided
    if hodl_waves is None:
        hodl_waves = {}
        if total_supply > 0:
            for cohort, btc in supply_by_cohort.items():
                hodl_waves[cohort] = (btc / total_supply) * 100

    snapshot = UTXOSetSnapshot(
        block_height=block_height,
        timestamp=timestamp,
        total_supply_btc=total_supply,
        sth_supply_btc=sth_supply,
        lth_supply_btc=lth_supply,
        supply_by_cohort=supply_by_cohort,
        realized_cap_usd=realized_cap,
        market_cap_usd=market_cap,
        mvrv=mvrv,
        nupl=nupl,
        hodl_waves=hodl_waves,
    )

    # Save snapshot to database
    save_snapshot(conn, snapshot)

    return snapshot


def save_snapshot(conn: duckdb.DuckDBPyConnection, snapshot: UTXOSetSnapshot) -> None:
    """Save a snapshot to the database.

    Automatically clears the snapshot cache to ensure fresh data.

    Args:
        conn: DuckDB connection.
        snapshot: UTXOSetSnapshot to save.
    """
    # Clear cache to ensure fresh data on next read
    clear_cache()

    conn.execute(
        """
        INSERT INTO utxo_snapshots (
            block_height, timestamp,
            total_supply_btc, sth_supply_btc, lth_supply_btc,
            realized_cap_usd, market_cap_usd, mvrv, nupl,
            hodl_waves_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (block_height) DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            total_supply_btc = EXCLUDED.total_supply_btc,
            sth_supply_btc = EXCLUDED.sth_supply_btc,
            lth_supply_btc = EXCLUDED.lth_supply_btc,
            realized_cap_usd = EXCLUDED.realized_cap_usd,
            market_cap_usd = EXCLUDED.market_cap_usd,
            mvrv = EXCLUDED.mvrv,
            nupl = EXCLUDED.nupl,
            hodl_waves_json = EXCLUDED.hodl_waves_json
        """,
        [
            snapshot.block_height,
            snapshot.timestamp,
            snapshot.total_supply_btc,
            snapshot.sth_supply_btc,
            snapshot.lth_supply_btc,
            snapshot.realized_cap_usd,
            snapshot.market_cap_usd,
            snapshot.mvrv,
            snapshot.nupl,
            json.dumps(snapshot.hodl_waves),
        ],
    )


def load_snapshot(
    conn: duckdb.DuckDBPyConnection, block_height: int
) -> UTXOSetSnapshot | None:
    """Load a snapshot from the database.

    Args:
        conn: DuckDB connection.
        block_height: Block height of the snapshot.

    Returns:
        UTXOSetSnapshot or None if not found.
    """
    from scripts.models.metrics_models import UTXOSetSnapshot

    result = conn.execute(
        """
        SELECT block_height, timestamp,
               total_supply_btc, sth_supply_btc, lth_supply_btc,
               realized_cap_usd, market_cap_usd, mvrv, nupl,
               hodl_waves_json
        FROM utxo_snapshots
        WHERE block_height = ?
        """,
        [block_height],
    ).fetchone()

    if result is None:
        return None

    hodl_waves = json.loads(result[9]) if result[9] else {}

    return UTXOSetSnapshot(
        block_height=result[0],
        timestamp=result[1],
        total_supply_btc=result[2],
        sth_supply_btc=result[3],
        lth_supply_btc=result[4],
        supply_by_cohort={},  # Not stored in DB, calculate if needed
        realized_cap_usd=result[5],
        market_cap_usd=result[6],
        mvrv=result[7],
        nupl=result[8],
        hodl_waves=hodl_waves,
    )


def get_latest_snapshot(conn: duckdb.DuckDBPyConnection) -> UTXOSetSnapshot | None:
    """Get the most recent snapshot (with TTL caching).

    Uses a 5-minute cache to reduce database queries for API requests.
    Cache is automatically invalidated after TTL expires.

    Args:
        conn: DuckDB connection.

    Returns:
        Most recent UTXOSetSnapshot or None.
    """
    # Check cache first
    cached = _get_cached("latest_snapshot")
    if cached is not None:
        logger.debug("Cache hit for latest_snapshot")
        return cached

    # Cache miss - query database
    result = conn.execute(
        """
        SELECT block_height FROM utxo_snapshots
        ORDER BY block_height DESC LIMIT 1
        """,
    ).fetchone()

    if result is None:
        return None

    snapshot = load_snapshot(conn, result[0])

    # Cache the result
    if snapshot is not None:
        _set_cached("latest_snapshot", snapshot)
        logger.debug(f"Cached latest_snapshot (block {snapshot.block_height})")

    return snapshot
