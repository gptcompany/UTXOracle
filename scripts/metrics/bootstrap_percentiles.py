#!/usr/bin/env python3
"""
Bootstrap Percentile Data Generator (spec-033, T006)

Generates 4-year historical percentile data for all 6 PRO Risk component metrics.
This data is used for normalizing current values to 0-1 percentile scores.

Usage:
    python scripts/metrics/bootstrap_percentiles.py [--db-path PATH] [--dry-run]

Metrics:
    - MVRV Z-Score (from realized_metrics)
    - SOPR (from sopr module)
    - NUPL (from nupl module)
    - Reserve Risk (from reserve_risk module)
    - Puell Multiple (from puell_multiple module)
    - HODL Waves (from hodl_waves module)

Output:
    Populates the risk_percentiles table in DuckDB with daily values.
"""

from __future__ import annotations

import argparse
from datetime import datetime

import duckdb

from scripts.config import UTXORACLE_DB_PATH

# Default database path - uses centralized config
DEFAULT_DB_PATH = str(UTXORACLE_DB_PATH)

# Metrics to bootstrap
METRICS = [
    "mvrv_z",
    "sopr",
    "nupl",
    "reserve_risk",
    "puell",
    "hodl_waves",
]

# Minimum days of history required
MIN_HISTORY_DAYS = 1460  # 4 years


def fetch_mvrv_z_history(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple[datetime, float]]:
    """Fetch MVRV-Z historical data from utxo_snapshots or cointime_metrics."""
    # TODO: Implement actual data fetching
    # Query would be something like:
    # SELECT timestamp, mvrv_z FROM cointime_metrics WHERE mvrv_z IS NOT NULL ORDER BY timestamp
    return []


def fetch_sopr_history(conn: duckdb.DuckDBPyConnection) -> list[tuple[datetime, float]]:
    """Fetch SOPR historical data."""
    # TODO: Implement actual data fetching
    return []


def fetch_nupl_history(conn: duckdb.DuckDBPyConnection) -> list[tuple[datetime, float]]:
    """Fetch NUPL historical data."""
    # TODO: Implement actual data fetching
    return []


def fetch_reserve_risk_history(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple[datetime, float]]:
    """Fetch Reserve Risk historical data."""
    # TODO: Implement actual data fetching
    return []


def fetch_puell_history(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple[datetime, float]]:
    """Fetch Puell Multiple historical data."""
    # TODO: Implement actual data fetching
    return []


def fetch_hodl_waves_history(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple[datetime, float]]:
    """Fetch HODL Waves (short-term holder ratio) historical data."""
    # TODO: Implement actual data fetching
    return []


# Mapping of metric names to fetch functions
FETCH_FUNCTIONS = {
    "mvrv_z": fetch_mvrv_z_history,
    "sopr": fetch_sopr_history,
    "nupl": fetch_nupl_history,
    "reserve_risk": fetch_reserve_risk_history,
    "puell": fetch_puell_history,
    "hodl_waves": fetch_hodl_waves_history,
}


def calculate_percentile(value: float, historical_values: list[float]) -> float:
    """
    Calculate percentile rank of value within historical distribution.

    Args:
        value: Current value to rank
        historical_values: List of historical values

    Returns:
        Percentile (0.0 - 1.0)
    """
    if not historical_values:
        return 0.5

    count_less_or_equal = sum(1 for h in historical_values if h <= value)
    return count_less_or_equal / len(historical_values)


def bootstrap_metric(
    conn: duckdb.DuckDBPyConnection,
    metric_name: str,
    dry_run: bool = False,
) -> int:
    """
    Bootstrap percentile data for a single metric.

    Args:
        conn: DuckDB connection
        metric_name: Name of the metric to bootstrap
        dry_run: If True, don't write to database

    Returns:
        Number of records inserted
    """
    fetch_fn = FETCH_FUNCTIONS.get(metric_name)
    if not fetch_fn:
        print(f"  No fetch function for {metric_name}")
        return 0

    # Fetch historical data
    history = fetch_fn(conn)
    if not history:
        print(f"  No historical data found for {metric_name}")
        return 0

    print(f"  Found {len(history)} historical records for {metric_name}")

    if len(history) < MIN_HISTORY_DAYS:
        print(
            f"  Warning: Only {len(history)} days, need {MIN_HISTORY_DAYS} for stable percentiles"
        )

    # Sort by date
    history.sort(key=lambda x: x[0])

    # Calculate percentiles for each date using expanding window
    records_inserted = 0
    historical_values: list[float] = []

    for i, (date_val, raw_value) in enumerate(history):
        historical_values.append(raw_value)

        # Calculate percentile using all data up to this point
        percentile = calculate_percentile(raw_value, historical_values)

        if not dry_run:
            # Insert into risk_percentiles table
            conn.execute(
                """
                INSERT OR REPLACE INTO risk_percentiles
                (metric_name, date, raw_value, percentile, history_days, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    metric_name,
                    date_val.date(),
                    raw_value,
                    percentile,
                    len(historical_values),
                ],
            )

        records_inserted += 1

        # Progress update every 365 days
        if (i + 1) % 365 == 0:
            print(f"    Processed {i + 1}/{len(history)} records...")

    return records_inserted


def bootstrap_all_metrics(db_path: str, dry_run: bool = False) -> dict[str, int]:
    """
    Bootstrap percentile data for all 6 metrics.

    Args:
        db_path: Path to DuckDB database
        dry_run: If True, don't write to database

    Returns:
        Dict of metric_name -> records inserted
    """
    # Connect to database
    conn = duckdb.connect(db_path)

    results = {}

    for metric_name in METRICS:
        print(f"\nBootstrapping {metric_name}...")
        count = bootstrap_metric(conn, metric_name, dry_run)
        results[metric_name] = count
        print(f"  Inserted {count} records")

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap historical percentile data for PRO Risk metrics"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing to database",
    )
    parser.add_argument(
        "--metric",
        choices=METRICS,
        help="Bootstrap only a specific metric",
    )

    args = parser.parse_args()

    print("Bootstrap Percentile Data Generator (spec-033)")
    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        print()

    if args.metric:
        # Bootstrap single metric
        conn = duckdb.connect(args.db_path)
        count = bootstrap_metric(conn, args.metric, args.dry_run)
        conn.close()
        print(f"\nTotal: {count} records for {args.metric}")
    else:
        # Bootstrap all metrics
        results = bootstrap_all_metrics(args.db_path, args.dry_run)
        print("\n=== Summary ===")
        total = 0
        for metric, count in results.items():
            print(f"  {metric}: {count} records")
            total += count
        print(f"  TOTAL: {total} records")


if __name__ == "__main__":
    main()
