#!/usr/bin/env python3
"""
Calculate and persist daily metrics from utxo_lifecycle data.

Usage:
    python -m scripts.metrics.calculate_daily_metrics --date 2024-12-27
    python -m scripts.metrics.calculate_daily_metrics --backfill 30  # Last 30 days
    python -m scripts.metrics.calculate_daily_metrics --dry-run

This module aggregates UTXO data into daily metric tables:
- sopr_daily: Spent Output Profit Ratio
- nupl_daily: Net Unrealized Profit/Loss
- mvrv_daily: Market Value to Realized Value
- realized_cap_daily: Daily Realized Cap
- cointime_daily: Liveliness, vaultedness metrics
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import duckdb

from scripts.config import UTXORACLE_DB_PATH

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_blocks_for_date(
    target_date: date, conn: duckdb.DuckDBPyConnection
) -> tuple[int, int]:
    """Get block range for a specific date.

    Args:
        target_date: The date to get blocks for
        conn: DuckDB connection

    Returns:
        (start_block, end_block) tuple
    """
    # Convert date to Unix timestamp range
    start_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp())
    end_ts = start_ts + 86400  # +24 hours

    # Query block_heights table for date range (timestamp is Unix integer)
    result = conn.execute(
        """
        SELECT MIN(height), MAX(height)
        FROM block_heights
        WHERE timestamp >= ? AND timestamp < ?
        """,
        [start_ts, end_ts],
    ).fetchone()

    if result[0] is None:
        raise ValueError(f"No blocks found for date {target_date}")

    return result[0], result[1]


def get_price_for_date(
    target_date: date, conn: duckdb.DuckDBPyConnection
) -> Optional[float]:
    """Get BTC price for a specific date from daily_prices table."""
    result = conn.execute(
        """
        SELECT price_usd
        FROM daily_prices
        WHERE date = ?
        """,
        [target_date],
    ).fetchone()

    return result[0] if result else None


def calculate_daily_realized_cap(
    conn: duckdb.DuckDBPyConnection, as_of_block: int
) -> float:
    """Calculate Realized Cap as of a specific block.

    Realized Cap = Sum of (UTXO value × creation price) for all unspent UTXOs.
    Uses utxo_lifecycle_full which has realized_value_usd pre-computed.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN is_spent = FALSE OR (is_spent = TRUE AND spent_block > ?)
                THEN realized_value_usd
                ELSE 0
            END
        ), 0)
        FROM utxo_lifecycle_full
        WHERE creation_block <= ?
        """,
        [as_of_block, as_of_block],
    ).fetchone()

    return result[0] if result else 0.0


def calculate_daily_sopr(
    conn: duckdb.DuckDBPyConnection, start_block: int, end_block: int
) -> Optional[float]:
    """Calculate SOPR for a block range.

    SOPR = Sum(spent_value_usd) / Sum(realized_value_usd) for UTXOs spent in range.

    If spent_price_usd is not available, we join with block_heights and daily_prices
    to get the price at which the UTXO was spent.
    """
    # First try with pre-computed spent_price_usd
    result = conn.execute(
        """
        SELECT
            COALESCE(SUM(btc_value * spent_price_usd), 0) as total_spent,
            COALESCE(SUM(realized_value_usd), 0) as total_realized
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
        AND spent_block BETWEEN ? AND ?
        AND realized_value_usd > 0
        AND spent_price_usd IS NOT NULL
        """,
        [start_block, end_block],
    ).fetchone()

    if result and result[0] > 0 and result[1] > 0:
        return result[0] / result[1]

    # Fallback: Join with block_heights and daily_prices to get spent price
    # block_heights.timestamp is Unix seconds (INTEGER), needs BIGINT cast for EPOCH_MS
    result = conn.execute(
        """
        SELECT
            COALESCE(SUM(u.btc_value * dp.price_usd), 0) as total_spent,
            COALESCE(SUM(u.realized_value_usd), 0) as total_realized
        FROM utxo_lifecycle_full u
        INNER JOIN block_heights bh ON u.spent_block = bh.height
        INNER JOIN daily_prices dp ON DATE(EPOCH_MS(CAST(bh.timestamp AS BIGINT) * 1000)) = dp.date
        WHERE u.is_spent = TRUE
        AND u.spent_block BETWEEN ? AND ?
        AND u.realized_value_usd > 0
        """,
        [start_block, end_block],
    ).fetchone()

    if result and result[1] > 0:
        return result[0] / result[1]
    return None


def calculate_daily_mvrv(
    market_cap: float, realized_cap: float
) -> tuple[Optional[float], Optional[float]]:
    """Calculate MVRV and MVRV-Z.

    MVRV = Market Cap / Realized Cap
    MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap) [simplified]
    """
    if realized_cap <= 0:
        return None, None

    mvrv = market_cap / realized_cap

    # Simplified MVRV-Z (using 1-sigma approximation)
    # A proper implementation would use historical std dev
    mvrv_z = (
        (market_cap - realized_cap) / (realized_cap * 0.3) if realized_cap > 0 else None
    )

    return mvrv, mvrv_z


def calculate_daily_nupl(market_cap: float, realized_cap: float) -> Optional[float]:
    """Calculate NUPL (Net Unrealized Profit/Loss).

    NUPL = (Market Cap - Realized Cap) / Market Cap
    """
    if market_cap <= 0:
        return None

    return (market_cap - realized_cap) / market_cap


def calculate_cointime_daily(conn: duckdb.DuckDBPyConnection, as_of_block: int) -> dict:
    """Calculate Cointime metrics as of a specific block.

    Returns:
        dict with liveliness, vaultedness, coindays_destroyed, etc.
    """
    # Simplified cointime calculation
    # Full implementation would use coindays_created and coindays_destroyed
    result = conn.execute(
        """
        SELECT
            COUNT(*) as total_utxos,
            SUM(CASE WHEN is_spent = TRUE AND spent_block <= ? THEN 1 ELSE 0 END) as spent_utxos,
            SUM(CASE WHEN is_spent = FALSE OR spent_block > ? THEN 1 ELSE 0 END) as live_utxos
        FROM utxo_lifecycle_full
        WHERE creation_block <= ?
        """,
        [as_of_block, as_of_block, as_of_block],
    ).fetchone()

    if result and result[0] > 0:
        liveliness = result[1] / result[0] if result[0] > 0 else 0
        vaultedness = result[2] / result[0] if result[0] > 0 else 0
        return {
            "liveliness": liveliness,
            "vaultedness": vaultedness,
            "activity_to_vaultedness_ratio": liveliness / vaultedness
            if vaultedness > 0
            else None,
        }

    return {
        "liveliness": None,
        "vaultedness": None,
        "activity_to_vaultedness_ratio": None,
    }


def calculate_daily_metrics(target_date: date, conn: duckdb.DuckDBPyConnection) -> dict:
    """Calculate all metrics for a single day.

    Args:
        target_date: Date to calculate metrics for
        conn: DuckDB connection

    Returns:
        dict with all calculated metrics
    """
    logger.info(f"Calculating metrics for {target_date}...")

    # Get block range for date
    start_block, end_block = get_blocks_for_date(target_date, conn)
    logger.debug(f"  Block range: {start_block} - {end_block}")

    # Get price
    price = get_price_for_date(target_date, conn)
    if price is None:
        logger.warning(f"  No price found for {target_date}")

    # Calculate Realized Cap
    realized_cap = calculate_daily_realized_cap(conn, end_block)

    # Get total supply (approximate from UTXO sum)
    supply_result = conn.execute(
        """
        SELECT COALESCE(SUM(btc_value), 0)
        FROM utxo_lifecycle_full
        WHERE (is_spent = FALSE OR spent_block > ?)
        AND creation_block <= ?
        """,
        [end_block, end_block],
    ).fetchone()
    total_supply = supply_result[0] if supply_result else 0

    # Calculate Market Cap
    market_cap = total_supply * price if price else 0

    # Calculate SOPR
    sopr = calculate_daily_sopr(conn, start_block, end_block)

    # Calculate MVRV
    mvrv, mvrv_z = calculate_daily_mvrv(market_cap, realized_cap)

    # Calculate NUPL
    nupl = calculate_daily_nupl(market_cap, realized_cap)

    # Calculate Cointime
    cointime = calculate_cointime_daily(conn, end_block)

    metrics = {
        "date": target_date,
        "realized_cap": realized_cap,
        "market_cap": market_cap,
        "total_supply": total_supply,
        "price": price,
        "sopr": sopr,
        "mvrv": mvrv,
        "mvrv_z": mvrv_z,
        "nupl": nupl,
        **cointime,
    }

    # Build log message with None-safe formatting
    mvrv_str = f"{mvrv:.3f}" if mvrv is not None else "N/A"
    if sopr is not None:
        logger.info(
            f"  Realized Cap: ${realized_cap / 1e12:.3f}T, MVRV: {mvrv_str}, SOPR: {sopr:.4f}"
        )
    else:
        logger.info(f"  Realized Cap: ${realized_cap / 1e12:.3f}T, MVRV: {mvrv_str}")

    return metrics


def persist_metrics(metrics: dict, conn: duckdb.DuckDBPyConnection) -> None:
    """Persist calculated metrics to respective daily tables.

    Uses INSERT OR REPLACE for upsert behavior.
    """
    target_date = metrics["date"]

    # sopr_daily
    if metrics.get("sopr") is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO sopr_daily (date, sopr)
            VALUES (?, ?)
            """,
            [target_date, metrics["sopr"]],
        )

    # nupl_daily
    if metrics.get("nupl") is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO nupl_daily (date, nupl, market_cap, realized_cap)
            VALUES (?, ?, ?, ?)
            """,
            [
                target_date,
                metrics["nupl"],
                metrics.get("market_cap"),
                metrics.get("realized_cap"),
            ],
        )

    # mvrv_daily
    if metrics.get("mvrv") is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO mvrv_daily (date, mvrv, mvrv_z, market_cap, realized_cap)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                target_date,
                metrics["mvrv"],
                metrics.get("mvrv_z"),
                metrics.get("market_cap"),
                metrics.get("realized_cap"),
            ],
        )

    # realized_cap_daily
    if metrics.get("realized_cap") is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO realized_cap_daily (date, realized_cap, total_supply)
            VALUES (?, ?, ?)
            """,
            [target_date, metrics["realized_cap"], metrics.get("total_supply")],
        )

    # cointime_daily
    if metrics.get("liveliness") is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO cointime_daily (date, liveliness, vaultedness, activity_to_vaultedness_ratio)
            VALUES (?, ?, ?, ?)
            """,
            [
                target_date,
                metrics.get("liveliness"),
                metrics.get("vaultedness"),
                metrics.get("activity_to_vaultedness_ratio"),
            ],
        )

    logger.debug(f"  Persisted metrics for {target_date}")


def backfill_metrics(
    days: int,
    conn: duckdb.DuckDBPyConnection,
    dry_run: bool = False,
    end_date: Optional[date] = None,
) -> int:
    """Backfill metrics for the last N days.

    Args:
        days: Number of days to backfill
        conn: DuckDB connection
        dry_run: If True, only calculate without persisting
        end_date: Optional end date (defaults to yesterday)

    Returns:
        Number of days successfully processed
    """
    if end_date is None:
        end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=days - 1)

    logger.info(f"Backfilling metrics from {start_date} to {end_date} ({days} days)")

    success_count = 0
    current_date = start_date

    while current_date <= end_date:
        try:
            metrics = calculate_daily_metrics(current_date, conn)

            if not dry_run:
                persist_metrics(metrics, conn)

            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to calculate metrics for {current_date}: {e}")

        current_date += timedelta(days=1)

    logger.info(f"Backfill complete: {success_count}/{days} days processed")
    return success_count


def main():
    parser = argparse.ArgumentParser(
        description="Calculate daily metrics from UTXO data"
    )
    parser.add_argument("--date", type=str, help="Date to calculate (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="Number of days to backfill")
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for backfill (YYYY-MM-DD), defaults to yesterday",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Calculate without persisting"
    )
    parser.add_argument("--db-path", type=str, default=str(UTXORACLE_DB_PATH))
    args = parser.parse_args()

    conn = duckdb.connect(args.db_path)

    try:
        if args.backfill:
            end_date = None
            if args.end_date:
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
            backfill_metrics(
                args.backfill, conn, dry_run=args.dry_run, end_date=end_date
            )
        elif args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            metrics = calculate_daily_metrics(target_date, conn)

            if not args.dry_run:
                persist_metrics(metrics, conn)
                logger.info(f"Metrics persisted for {target_date}")
            else:
                logger.info("Dry run - metrics calculated but not persisted")
                for key, value in metrics.items():
                    logger.info(f"  {key}: {value}")
        else:
            # Default: calculate yesterday
            yesterday = date.today() - timedelta(days=1)
            metrics = calculate_daily_metrics(yesterday, conn)

            if not args.dry_run:
                persist_metrics(metrics, conn)
                logger.info(f"Metrics persisted for {yesterday}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
