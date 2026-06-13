#!/usr/bin/env python3
"""Materialize the Nautilus URPD scalar feature surface.

The serving table is QuestDB `urpd_features_daily`. Calculations read the
DuckDB UTXO lifecycle surface point-in-time and write one scalar row per target
timestamp so consumers do not scan `utxo_lifecycle_full` at runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

import duckdb

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.questdb_repository import QuestDBRepository
from scripts.config.database import UTXORACLE_DB_PATH
from scripts.metrics.urpd import _point_in_time_predicates, _utxo_lifecycle_columns
from scripts.metrics.urpd_features import calculate_urpd_features_signal
from scripts.models.metrics_models import URPDFeaturesResult

logger = logging.getLogger("materialize_urpd_features")

URPD_FEATURE_SCHEMA_VERSION = "urpd_features_daily.v1"
REQUIRED_URPD_FEATURE_FIELDS = (
    "ts",
    "availability_timestamp",
    "block_height",
    "current_price_usd",
    "bucket_size_usd",
    "total_supply_btc",
    "supply_below_price_pct",
    "supply_above_price_pct",
    "top_bucket_concentration",
    "dominant_bucket_distance_pct",
    "distribution_entropy",
    "confidence",
    "schema_version",
)


def _setup_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    ).fetchone()
    return bool(row and row[0])


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_block_height_for_timestamp(
    conn: duckdb.DuckDBPyConnection,
    target_ts: datetime,
) -> int:
    """Return the latest known block height at or before target_ts."""
    target_ts = _coerce_utc(target_ts)
    target_epoch = int(target_ts.timestamp())

    if _table_exists(conn, "block_heights"):
        row = conn.execute(
            """
            SELECT height
            FROM block_heights
            WHERE timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [target_epoch],
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])

    row = conn.execute(
        """
        SELECT max(creation_block)
        FROM utxo_lifecycle_full
        WHERE creation_block IS NOT NULL
        """
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def resolve_price_for_timestamp(
    conn: duckdb.DuckDBPyConnection,
    target_ts: datetime,
) -> tuple[float | None, str, date | None]:
    """Return the latest daily BTC/USD price available at or before target_ts."""
    target_ts = _coerce_utc(target_ts)

    if not _table_exists(conn, "daily_prices"):
        return None, "daily_prices_unavailable", None

    row = conn.execute(
        """
        SELECT date, price_usd
        FROM daily_prices
        WHERE date <= ?
          AND price_usd IS NOT NULL
          AND price_usd > 0
        ORDER BY date DESC
        LIMIT 1
        """,
        [target_ts.date()],
    ).fetchone()
    if not row:
        return None, "daily_prices_missing", None

    return float(row[1]), "daily_prices", row[0]


def _block_timestamp(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
) -> datetime | None:
    if block_height <= 0 or not _table_exists(conn, "block_heights"):
        return None
    row = conn.execute(
        "SELECT timestamp FROM block_heights WHERE height = ? LIMIT 1",
        [block_height],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return datetime.fromtimestamp(int(row[0]), tz=timezone.utc)


def build_source_health(
    conn: duckdb.DuckDBPyConnection,
    *,
    target_ts: datetime,
    block_height: int,
    current_price_usd: float | None,
    price_source: str,
    price_date: date | None,
) -> dict:
    """Summarize upstream completeness and freshness for a materialized row."""
    target_ts = _coerce_utc(target_ts)
    columns = _utxo_lifecycle_columns(conn)
    predicates, params = _point_in_time_predicates(columns, block_height)
    where_clause = " AND ".join(predicates) if predicates else "TRUE"

    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS visible_utxos,
            COALESCE(SUM(btc_value), 0.0) AS visible_supply_btc,
            SUM(CASE WHEN creation_price_usd IS NULL OR creation_price_usd <= 0 THEN 1 ELSE 0 END)
                AS missing_creation_price_utxos,
            SUM(CASE WHEN creation_price_usd IS NOT NULL AND creation_price_usd > 0 THEN 1 ELSE 0 END)
                AS priced_utxos,
            COALESCE(SUM(CASE WHEN creation_price_usd IS NOT NULL AND creation_price_usd > 0 THEN btc_value ELSE 0.0 END), 0.0)
                AS priced_supply_btc,
            MAX(creation_block) AS latest_creation_block
        FROM utxo_lifecycle_full
        WHERE {where_clause}
        """,
        params,
    ).fetchone()

    visible_utxos = int(row[0] or 0)
    missing_creation_price_utxos = int(row[2] or 0)
    priced_utxos = int(row[3] or 0)
    visible_supply_btc = float(row[1] or 0.0)
    priced_supply_btc = float(row[4] or 0.0)
    coverage_pct = (priced_utxos / visible_utxos * 100.0) if visible_utxos else None
    latest_block_ts = _block_timestamp(conn, block_height)
    source_freshness_seconds = (
        max((target_ts - latest_block_ts).total_seconds(), 0.0)
        if latest_block_ts is not None
        else None
    )

    has_current_price = current_price_usd is not None and current_price_usd > 0
    if block_height <= 0:
        status = "unavailable"
    elif visible_utxos == 0:
        status = "empty"
    elif priced_utxos == 0 or not has_current_price:
        status = "degraded"
    elif missing_creation_price_utxos > 0:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "source": "utxo_lifecycle_full",
        "price_source": price_source,
        "price_date": price_date.isoformat() if price_date else None,
        "has_current_price": has_current_price,
        "block_height": block_height,
        "latest_creation_block": int(row[5]) if row and row[5] is not None else None,
        "visible_utxos": visible_utxos,
        "visible_supply_btc": visible_supply_btc,
        "priced_utxos": priced_utxos,
        "priced_supply_btc": priced_supply_btc,
        "missing_creation_price_utxos": missing_creation_price_utxos,
        "creation_price_coverage_pct": coverage_pct,
        "source_freshness_seconds": source_freshness_seconds,
        "schema_version": URPD_FEATURE_SCHEMA_VERSION,
    }


async def materialize_urpd_features_row(
    repo: QuestDBRepository,
    conn: duckdb.DuckDBPyConnection,
    target_ts: datetime,
    *,
    bucket_size_usd: float = 5000.0,
    dry_run: bool = False,
) -> URPDFeaturesResult:
    """Calculate and optionally persist one URPD feature row."""
    target_ts = _coerce_utc(target_ts)
    availability_ts = datetime.now(timezone.utc)
    block_height = resolve_block_height_for_timestamp(conn, target_ts)
    current_price_usd, price_source, price_date = resolve_price_for_timestamp(
        conn,
        target_ts,
    )
    source_health = build_source_health(
        conn,
        target_ts=target_ts,
        block_height=block_height,
        current_price_usd=current_price_usd,
        price_source=price_source,
        price_date=price_date,
    )

    result = calculate_urpd_features_signal(
        conn=conn,
        current_price_usd=current_price_usd,
        current_block=block_height,
        bucket_size_usd=bucket_size_usd,
        timestamp=target_ts,
        availability_timestamp=availability_ts,
        schema_version=URPD_FEATURE_SCHEMA_VERSION,
        source_health=source_health,
    )

    if dry_run:
        logger.info("Dry run URPD feature row: %s", json.dumps(result.to_dict(), sort_keys=True))
        return result

    if not repo.save_urpd_features(result):
        repo.abort_ingestion()
        raise RuntimeError(f"Failed to write urpd_features_daily row for {target_ts.isoformat()}")

    return result


def iter_backfill_timestamps(start_day: date, end_day: date) -> Iterable[datetime]:
    """Yield daily UTC materialization timestamps, inclusive."""
    current = start_day
    while current <= end_day:
        yield _utc_start(current)
        current += timedelta(days=1)


async def run(
    *,
    db_path: Path,
    target_ts: datetime | None,
    start_date: date | None,
    end_date: date | None,
    backfill_days: int | None,
    bucket_size_usd: float,
    dry_run: bool,
) -> list[URPDFeaturesResult]:
    if not db_path.exists() and str(db_path) != ":memory:":
        raise FileNotFoundError(f"DuckDB database not found: {db_path}")

    if backfill_days is not None:
        if backfill_days <= 0:
            raise ValueError("--backfill-days must be positive")
        end_date = end_date or datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=backfill_days - 1)

    if start_date and not end_date:
        end_date = start_date
    if end_date and not start_date:
        start_date = end_date

    if start_date and end_date and start_date > end_date:
        raise ValueError("--start-date must be <= --end-date")

    targets = (
        list(iter_backfill_timestamps(start_date, end_date))
        if start_date and end_date
        else [target_ts or datetime.now(timezone.utc)]
    )

    conn = duckdb.connect(str(db_path), read_only=True)
    conn.execute("SET max_memory='8GB'")
    repo = QuestDBRepository()
    results: list[URPDFeaturesResult] = []

    try:
        if not dry_run:
            await repo.initialize()

        for row_ts in targets:
            result = await materialize_urpd_features_row(
                repo,
                conn,
                row_ts,
                bucket_size_usd=bucket_size_usd,
                dry_run=dry_run,
            )
            results.append(result)
            logger.info(
                "Materialized URPD features ts=%s block=%s confidence=%.2f status=%s",
                result.timestamp.isoformat(),
                result.block_height,
                result.confidence,
                result.source_health.get("status"),
            )

        if not dry_run:
            flush_ok = await repo.async_flush_ingestion()
            if not flush_ok:
                raise RuntimeError("Failed to flush QuestDB URPD feature writes")
    finally:
        conn.close()
        if not dry_run:
            await repo.close()

    return results


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _coerce_utc(parsed)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize urpd_features_daily")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=UTXORACLE_DB_PATH,
        help="DuckDB path containing utxo_lifecycle_full, block_heights, and daily_prices",
    )
    parser.add_argument(
        "--timestamp",
        type=_parse_timestamp,
        help="Single row timestamp, ISO-8601. Defaults to now.",
    )
    parser.add_argument("--start-date", type=_parse_date, help="Backfill start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, help="Backfill end date YYYY-MM-DD")
    parser.add_argument("--backfill-days", type=int, help="Backfill the last N UTC days")
    parser.add_argument("--bucket-size-usd", type=float, default=5000.0)
    parser.add_argument("--dry-run", action="store_true", help="Calculate rows without QuestDB writes")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    _setup_logging()
    args = parse_args(argv)
    await run(
        db_path=args.db_path,
        target_ts=args.timestamp,
        start_date=args.start_date,
        end_date=args.end_date,
        backfill_days=args.backfill_days,
        bucket_size_usd=args.bucket_size_usd,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
