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
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

import duckdb

from scripts.config import UTXORACLE_DB_PATH

# spec-061 T023: dual-write to QuestDB. Imported at module level so tests can
# patch these symbols at scripts.metrics.calculate_daily_metrics.save_*.
# Strangler-fig per research.md R5: QuestDB write failure logs but does not
# raise; DuckDB remains the source of truth during the transition.
from api.questdb_repository import (
    _open_pg_sync,
    save_mvrv_daily,
    save_nupl_daily,
    save_realized_cap_daily,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_blocks_for_date(
    target_date: date,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    questdb_reads: bool = False,
) -> tuple[int, int]:
    """Get block range for a specific date.

    Args:
        target_date: The date to get blocks for
        conn: DuckDB connection
        questdb_reads: Read block_heights from QuestDB instead of DuckDB

    Returns:
        (start_block, end_block) tuple
    """
    # Convert date to Unix timestamp range
    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = start_dt + timedelta(days=1)

    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT MIN(height), MAX(height)
                    FROM block_heights
                    WHERE ts >= %s AND ts < %s
                    """,
                    (start_dt, end_dt),
                )
                result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # Query block_heights table for date range (timestamp is Unix integer)
        result = conn.execute(
            """
            SELECT MIN(height), MAX(height)
            FROM block_heights
            WHERE timestamp >= ? AND timestamp < ?
            """,
            [start_ts, end_ts],
        ).fetchone()


    if result is None or result[0] is None or result[1] is None:
        raise ValueError(f"No blocks found for date {target_date}")

    return int(result[0]), int(result[1])


def get_price_for_date(
    target_date: date,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    questdb_reads: bool = False,
) -> Optional[float]:
    """Get BTC price for a specific date from daily_prices table."""
    if questdb_reads:
        target_ts = datetime.combine(target_date, datetime.min.time())
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT price_usd
                    FROM daily_prices
                    WHERE date = %s
                    ORDER BY fetched_at DESC
                    LIMIT 1
                    """,
                    (target_ts,),
                )
                result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
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
    conn: Optional[duckdb.DuckDBPyConnection],
    as_of_block: int,
    *,
    questdb_reads: bool = False,
) -> float:
    """Calculate Realized Cap as of a specific block.

    Realized Cap = Sum of (UTXO value × creation price) for all unspent UTXOs.
    Uses utxo_lifecycle (QuestDB SSOT) or utxo_lifecycle_full (legacy DuckDB).
    """
    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(
                        CASE
                            WHEN is_spent = FALSE OR (is_spent = TRUE AND spent_block > %s)
                            THEN realized_value_usd
                            ELSE 0
                        END
                    ), 0)
                    FROM utxo_lifecycle
                    WHERE creation_block <= %s
                    """,
                    (as_of_block, as_of_block),
                )
                result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
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

    return float(result[0]) if result and result[0] is not None else 0.0


def calculate_daily_sopr(
    conn: Optional[duckdb.DuckDBPyConnection],
    start_block: int,
    end_block: int,
    *,
    questdb_reads: bool = False,
) -> Optional[float]:
    """Calculate SOPR for a block range.

    SOPR = Sum(spent_value_usd) / Sum(realized_value_usd) for UTXOs spent in range.

    If spent_price_usd is not available, we join with block_heights and daily_prices
    to get the price at which the UTXO was spent.
    """
    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(btc_value * spent_price_usd), 0) AS total_spent,
                        COALESCE(SUM(realized_value_usd), 0) AS total_realized
                    FROM utxo_lifecycle
                    WHERE is_spent = TRUE
                      AND spent_block BETWEEN %s AND %s
                      AND realized_value_usd > 0
                      AND spent_price_usd IS NOT NULL
                    """,
                    (start_block, end_block),
                )
                result = cur.fetchone()
                if (
                    result
                    and result[0] is not None
                    and result[1] is not None
                    and float(result[0]) > 0
                    and float(result[1]) > 0
                ):
                    return float(result[0]) / float(result[1])

                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(u.btc_value * dp.price_usd), 0) AS total_spent,
                        COALESCE(SUM(u.realized_value_usd), 0) AS total_realized
                    FROM utxo_lifecycle u
                    JOIN block_heights bh ON u.spent_block = bh.height
                    JOIN daily_prices dp ON cast(bh.ts AS DATE) = cast(dp.date AS DATE)
                    WHERE u.is_spent = TRUE
                      AND u.spent_block BETWEEN %s AND %s
                      AND u.realized_value_usd > 0
                    """,
                    (start_block, end_block),
                )
                result = cur.fetchone()
        if (
            result
            and result[1] is not None
            and float(result[1]) > 0
        ):
            return float(result[0]) / float(result[1])
        return None

    # Legacy DuckDB path
    assert conn is not None, "DuckDB conn required when questdb_reads=False"
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
    conn: Optional[duckdb.DuckDBPyConnection],
    market_cap: float,
    realized_cap: float,
    as_of_block: Optional[int] = None,
    *,
    questdb_reads: bool = False,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calculate MVRV, MVRV-Z (simplified), and MVRV-Z (RBN).

    MVRV = Market Cap / Realized Cap
    MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap) [simplified]
    MVRV-Z (RBN) = (Market Cap - Realized Cap) / StdDev(All-time Market Cap)
    """
    if realized_cap <= 0:
        return None, None, None

    mvrv = market_cap / realized_cap

    # Simplified MVRV-Z (using 1-sigma approximation)
    # A proper implementation would use historical std dev
    mvrv_z = (
        (market_cap - realized_cap) / (realized_cap * 0.3) if realized_cap > 0 else None
    )

    from scripts.metrics.mvrv_variants import calculate_both_mvrv_z

    variants = calculate_both_mvrv_z(
        conn,
        market_cap,
        realized_cap,
        max_block_height=as_of_block,
        questdb_reads=questdb_reads,
    )
    mvrv_z_rbn = (
        variants.mvrv_z_rbn
        if (variants.mvrv_z_rbn != 0.0 or variants.std_all != 0.0)
        else None
    )

    return mvrv, mvrv_z, mvrv_z_rbn


def calculate_daily_nupl(market_cap: float, realized_cap: float) -> Optional[float]:
    """Calculate NUPL (Net Unrealized Profit/Loss).

    NUPL = (Market Cap - Realized Cap) / Market Cap
    """
    if market_cap <= 0:
        return None

    return (market_cap - realized_cap) / market_cap


def calculate_cointime_daily(
    conn: Optional[duckdb.DuckDBPyConnection],
    as_of_block: int,
    *,
    questdb_reads: bool = False,
) -> dict:
    """Calculate Cointime metrics as of a specific block.

    Uses coinblocks formula per Cointime Economics (spec-018):
    - Liveliness = cumulative_coinblocks_destroyed / cumulative_coinblocks_created
    - Vaultedness = 1 - Liveliness
    """
    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(btc_value * COALESCE(age_blocks, spent_block - creation_block)), 0)
                    FROM utxo_lifecycle
                    WHERE is_spent = TRUE
                      AND spent_block <= %s
                      AND creation_block > 0
                    """,
                    (as_of_block,),
                )
                destroyed_result = cur.fetchone()
                cur.execute(
                    """
                    SELECT COALESCE(SUM(btc_value * (%s - creation_block)), 0)
                    FROM utxo_lifecycle
                    WHERE creation_block <= %s
                      AND creation_block > 0
                    """,
                    (as_of_block, as_of_block),
                )
                created_result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
        # Coinblocks destroyed: sum of (btc_value * age at spending) for all spent UTXOs
        destroyed_result = conn.execute(
            """
            SELECT COALESCE(SUM(btc_value * COALESCE(age_blocks, spent_block - creation_block)), 0)
            FROM utxo_lifecycle_full
            WHERE is_spent = TRUE
            AND spent_block <= ?
            AND creation_block > 0
            """,
            [as_of_block],
        ).fetchone()

        # Coinblocks created: sum of (btc_value * age) for all UTXOs existing at as_of_block
        created_result = conn.execute(
            """
            SELECT COALESCE(SUM(btc_value * (? - creation_block)), 0)
            FROM utxo_lifecycle_full
            WHERE creation_block <= ?
            AND creation_block > 0
            """,
            [as_of_block, as_of_block],
        ).fetchone()

    coinblocks_destroyed = (
        float(destroyed_result[0]) if destroyed_result and destroyed_result[0] is not None else 0.0
    )
    coinblocks_created = (
        float(created_result[0]) if created_result and created_result[0] is not None else 0.0
    )

    if coinblocks_created > 0:
        liveliness = min(1.0, max(0.0, coinblocks_destroyed / coinblocks_created))
        vaultedness = 1.0 - liveliness
        return {
            "liveliness": liveliness,
            "vaultedness": vaultedness,
            "activity_to_vaultedness_ratio": liveliness / vaultedness
            if vaultedness > 0
            else None,
            "coinblocks_destroyed": coinblocks_destroyed,
            "coinblocks_created": coinblocks_created,
        }

    return {
        "liveliness": None,
        "vaultedness": None,
        "activity_to_vaultedness_ratio": None,
        "coinblocks_destroyed": None,
        "coinblocks_created": None,
    }


def calculate_daily_metrics(
    target_date: date,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    questdb_reads: bool = False,
) -> dict:
    """Calculate all metrics for a single day.

    Args:
        target_date: Date to calculate metrics for
        conn: DuckDB connection

    Returns:
        dict with all calculated metrics
    """
    logger.info(f"Calculating metrics for {target_date}...")

    # Get block range for date
    start_block, end_block = get_blocks_for_date(
        target_date,
        conn,
        questdb_reads=questdb_reads,
    )
    logger.debug(f"  Block range: {start_block} - {end_block}")

    # Get price
    price = get_price_for_date(target_date, conn, questdb_reads=questdb_reads)
    if price is None:
        logger.warning(f"  No price found for {target_date}")

    # Calculate Realized Cap
    realized_cap = calculate_daily_realized_cap(
        conn, end_block, questdb_reads=questdb_reads
    )

    # Get total supply (approximate from UTXO sum)
    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(btc_value), 0)
                    FROM utxo_lifecycle
                    WHERE (is_spent = FALSE OR spent_block > %s)
                      AND creation_block <= %s
                    """,
                    (end_block, end_block),
                )
                supply_result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
        supply_result = conn.execute(
            """
            SELECT COALESCE(SUM(btc_value), 0)
            FROM utxo_lifecycle_full
            WHERE (is_spent = FALSE OR spent_block > ?)
            AND creation_block <= ?
            """,
            [end_block, end_block],
        ).fetchone()
    total_supply = (
        float(supply_result[0])
        if supply_result and supply_result[0] is not None
        else 0.0
    )

    # Calculate Market Cap
    market_cap = total_supply * price if price else 0

    # Calculate SOPR
    sopr = calculate_daily_sopr(
        conn, start_block, end_block, questdb_reads=questdb_reads
    )

    # Calculate MVRV
    mvrv, mvrv_z, mvrv_z_rbn = calculate_daily_mvrv(
        conn,
        market_cap,
        realized_cap,
        as_of_block=end_block,
        questdb_reads=questdb_reads,
    )

    # Calculate NUPL
    nupl = calculate_daily_nupl(market_cap, realized_cap)

    # Calculate Cointime
    cointime = calculate_cointime_daily(
        conn, end_block, questdb_reads=questdb_reads
    )

    metrics = {
        "date": target_date,
        "realized_cap": realized_cap,
        "market_cap": market_cap,
        "total_supply": total_supply,
        "price": price,
        "sopr": sopr,
        "mvrv": mvrv,
        "mvrv_z": mvrv_z,
        "mvrv_z_rbn": mvrv_z_rbn,
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


def persist_metrics(metrics: dict, conn: Optional[duckdb.DuckDBPyConnection]) -> None:
    """Persist calculated metrics to respective daily tables.

    Uses INSERT OR REPLACE for upsert behavior. Requires a non-None DuckDB
    connection; the QuestDB-only write path goes through `_persist_to_questdb`
    via `persist_metrics_for_target(..., questdb_only=True)`.
    """
    assert conn is not None, (
        "DuckDB conn required for persist_metrics; "
        "use persist_metrics_for_target(..., questdb_only=True) for QuestDB-only writes"
    )
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
        mvrv_daily_columns = {
            row[1] for row in conn.execute("PRAGMA table_info('mvrv_daily')").fetchall()
        }

        if "mvrv_z_rbn" in mvrv_daily_columns:
            conn.execute(
                """
                INSERT OR REPLACE INTO mvrv_daily (date, mvrv, mvrv_z, mvrv_z_rbn, market_cap, realized_cap)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    target_date,
                    metrics["mvrv"],
                    metrics.get("mvrv_z"),
                    metrics.get("mvrv_z_rbn"),
                    metrics.get("market_cap"),
                    metrics.get("realized_cap"),
                ],
            )
        else:
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

    # spec-061 T023: dual-write to QuestDB after DuckDB writes complete.
    # Strangler-fig per research.md R5: failure logged, not raised.
    _persist_to_questdb(metrics)


def _persist_to_questdb(metrics: dict) -> int:
    """Mirror the three daily aggregates into QuestDB for the consumer contract.

    Failure isolated per call so a transient QuestDB issue does not block
    the DuckDB write that already succeeded (research.md R5). The endpoint
    reads ONLY from QuestDB; if writes silently fail, the affected stream
    goes STALE and the consumer sees the truth - no silent success.

    Returns the count of rows successfully written (0..3) for FR-011 logging.
    """
    target_date = metrics["date"]
    ts = datetime(target_date.year, target_date.month, target_date.day)
    rows_written = 0

    if metrics.get("mvrv") is not None:
        try:
            save_mvrv_daily(
                ts,
                float(metrics["mvrv"]),
                mvrv_z=metrics.get("mvrv_z"),
                market_cap=metrics.get("market_cap"),
                realized_cap=metrics.get("realized_cap"),
            )
            rows_written += 1
        except Exception as exc:
            logger.error("QuestDB save_mvrv_daily failed for %s: %s", target_date, exc)

    if metrics.get("nupl") is not None:
        try:
            save_nupl_daily(
                ts,
                float(metrics["nupl"]),
                market_cap=metrics.get("market_cap"),
                realized_cap=metrics.get("realized_cap"),
            )
            rows_written += 1
        except Exception as exc:
            logger.error("QuestDB save_nupl_daily failed for %s: %s", target_date, exc)

    if metrics.get("realized_cap") is not None:
        try:
            save_realized_cap_daily(
                ts,
                float(metrics["realized_cap"]),
                total_supply=metrics.get("total_supply"),
            )
            rows_written += 1
        except Exception as exc:
            logger.error(
                "QuestDB save_realized_cap_daily failed for %s: %s", target_date, exc
            )

    return rows_written


def _post_discord_failure(target_date: date, exc: BaseException) -> None:
    """FR-012: Discord webhook notification on failure only.

    Posts a one-line summary on failure. Webhook errors are swallowed -- they
    MUST NOT mask the original aggregator exception.
    """
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook or webhook.startswith("ENC[") or webhook.startswith("encrypted:"):
        return
    summary = str(exc).splitlines()[0] if str(exc) else ""
    if len(summary) > 200:
        summary = summary[:197] + "..."
    payload = json.dumps(
        {
            "content": (
                f":rotating_light: UTXOracle aggregator failed for "
                f"{target_date.isoformat()}: {type(exc).__name__} - {summary}"
            )
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read(0)
    except (urllib.error.URLError, OSError, TimeoutError) as webhook_exc:
        logger.warning(
            "Discord webhook post failed for %s (suppressed): %s",
            target_date,
            webhook_exc,
        )


def _run_single_date(
    target_date: date,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    dry_run: bool,
    questdb_only: bool,
    questdb_reads: bool,
) -> int:
    """FR-011 single-date wrapper.

    Measures wall-clock duration, counts metric rows written, emits ONE INFO
    log on success and ONE ERROR log + Discord webhook on failure (FR-012).
    Returns the count of rows written (0 when dry-run).
    """
    started = time.monotonic()
    try:
        metrics = calculate_daily_metrics(
            target_date, conn, questdb_reads=questdb_reads
        )
        if dry_run:
            logger.info(
                "spec-062 dry-run complete: date=%s duration_s=%.2f rows_written=0",
                target_date.isoformat(),
                time.monotonic() - started,
            )
            return 0
        rows_written = 0
        if questdb_only:
            rows_written = _persist_to_questdb(metrics)
        else:
            persist_metrics(metrics, conn)
            rows_written = _persist_to_questdb(metrics)
        logger.info(
            "spec-062 aggregator success: date=%s duration_s=%.2f rows_written=%d",
            target_date.isoformat(),
            time.monotonic() - started,
            rows_written,
        )
        return rows_written
    except Exception as exc:
        logger.error(
            "spec-062 aggregator failure: date=%s duration_s=%.2f exc=%s",
            target_date.isoformat(),
            time.monotonic() - started,
            type(exc).__name__,
            exc_info=True,
        )
        _post_discord_failure(target_date, exc)
        raise


def persist_metrics_for_target(
    metrics: dict,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    questdb_only: bool = False,
) -> None:
    """Persist metrics for the selected operational target.

    The live wave1 materializer can hold an exclusive DuckDB writer lock for
    long periods. The scheduled spec-061 consumer surface only needs QuestDB
    rows, so ``--questdb-only`` lets the timer read DuckDB in read-only mode
    and update the QuestDB contract tables without disturbing that writer.
    """
    if questdb_only:
        _persist_to_questdb(metrics)
        logger.info("QuestDB-only metrics mirrored for %s", metrics["date"])
        return

    persist_metrics(metrics, conn)


def backfill_metrics(
    days: int,
    conn: Optional[duckdb.DuckDBPyConnection],
    dry_run: bool = False,
    end_date: Optional[date] = None,
    questdb_only: bool = False,
    questdb_reads: bool = False,
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
            metrics = calculate_daily_metrics(
                current_date,
                conn,
                questdb_reads=questdb_reads,
            )

            if not dry_run:
                persist_metrics_for_target(metrics, conn, questdb_only=questdb_only)

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
    parser.add_argument(
        "--questdb-only",
        action="store_true",
        help="Persist only QuestDB contract tables; open DuckDB read-only",
    )
    parser.add_argument(
        "--questdb-reads",
        action="store_true",
        help="Read block_heights and daily_prices from QuestDB",
    )
    parser.add_argument(
        "--recalculate", action="store_true", help="Recalculate entire history"
    )
    parser.add_argument("--db-path", type=str, default=str(UTXORACLE_DB_PATH))
    args = parser.parse_args()

    # spec-062: when --questdb-reads --questdb-only, no DuckDB connection is
    # ever needed: reads come from QuestDB and writes target QuestDB only.
    duckdb_free = args.questdb_reads and args.questdb_only
    conn: Optional[duckdb.DuckDBPyConnection] = (
        None
        if duckdb_free
        else duckdb.connect(args.db_path, read_only=args.questdb_only or args.dry_run)
    )

    try:
        if args.recalculate:
            if duckdb_free:
                with _open_pg_sync() as qdb:
                    with qdb.cursor() as cur:
                        cur.execute("SELECT count(*) FROM daily_prices")
                        row = cur.fetchone()
                        total_days = int(row[0]) if row else 0
            else:
                assert conn is not None
                result = conn.execute("SELECT count(*) FROM daily_prices").fetchone()
                total_days = result[0] if result else 0
            if total_days > 0:
                logger.info(f"Recalculating {total_days} days of metrics")
                backfill_metrics(
                    total_days,
                    conn,
                    dry_run=args.dry_run,
                    questdb_only=args.questdb_only,
                    questdb_reads=args.questdb_reads,
                )
            else:
                logger.warning("No daily prices found to recalculate")
        elif args.backfill:
            end_date = None
            if args.end_date:
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
            backfill_metrics(
                args.backfill,
                conn,
                dry_run=args.dry_run,
                end_date=end_date,
                questdb_only=args.questdb_only,
                questdb_reads=args.questdb_reads,
            )
        elif args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            _run_single_date(
                target_date,
                conn,
                dry_run=args.dry_run,
                questdb_only=args.questdb_only,
                questdb_reads=args.questdb_reads,
            )
        else:
            # Default: calculate yesterday
            yesterday = date.today() - timedelta(days=1)
            _run_single_date(
                yesterday,
                conn,
                dry_run=args.dry_run,
                questdb_only=args.questdb_only,
                questdb_reads=args.questdb_reads,
            )
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
