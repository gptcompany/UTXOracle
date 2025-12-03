#!/usr/bin/env python3
"""
Backfill Exchange Prices from mempool.space API

Populates missing exchange prices in DuckDB using mempool.space historical API.

Usage:
    python scripts/backfill_exchange_prices.py --days 7
    python scripts/backfill_exchange_prices.py --date 2025-10-29
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

import requests
import duckdb
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
load_dotenv()

# Configuration
MEMPOOL_PUBLIC_API = "https://mempool.space/api/v1/historical-price"
DUCKDB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def fetch_exchange_price_for_date(date_str: str) -> float:
    """
    Fetch historical exchange price from mempool.space public API.

    Args:
        date_str: Date in format 'YYYY-MM-DD'

    Returns:
        float: USD price

    Raises:
        requests.RequestException: On API errors
    """
    # Convert date to Unix timestamp (noon UTC)
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12, minute=0, second=0)
    timestamp = int(dt.timestamp())

    url = f"{MEMPOOL_PUBLIC_API}?currency=USD&timestamp={timestamp}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Response format: {"prices": [{"USD": 112345.67, "EUR": ...}]}
        data = response.json()

        # Handle different response formats
        if isinstance(data, dict):
            if "prices" in data and len(data["prices"]) > 0:
                price = data["prices"][0].get("USD")
            elif "USD" in data:
                price = data["USD"]
            else:
                raise ValueError(f"Unexpected response format: {data}")
        else:
            raise ValueError(f"Unexpected response type: {type(data)}")

        if price is None:
            raise ValueError(f"USD price not found in response: {data}")

        logging.info(f"  [{date_str}] Fetched exchange price: ${price:,.2f}")
        return float(price)

    except requests.RequestException as e:
        logging.error(f"  [{date_str}] API request failed: {e}")
        raise


def get_dates_with_missing_exchange_prices(conn, max_days_back: int = 7) -> List[str]:
    """
    Find dates that have UTXOracle price but missing exchange price.

    Args:
        conn: DuckDB connection
        max_days_back: How many days back to check

    Returns:
        list: Dates missing exchange prices (YYYY-MM-DD)
    """
    query = """
        SELECT DATE(timestamp) as date
        FROM prices
        WHERE timestamp >= CURRENT_DATE - INTERVAL '{days} days'
          AND utxoracle_price IS NOT NULL
          AND mempool_price IS NULL
        ORDER BY date DESC
    """.format(days=max_days_back)

    result = conn.execute(query).fetchall()
    dates = [row[0].strftime("%Y-%m-%d") for row in result]

    logging.info(f"Found {len(dates)} dates with missing exchange prices")
    return dates


def update_exchange_price(conn, date_str: str, exchange_price: float) -> None:
    """
    Update exchange price and diff columns for a specific date.

    Args:
        conn: DuckDB connection
        date_str: Date string (YYYY-MM-DD)
        exchange_price: Exchange price to update
    """
    query = """
        UPDATE prices
        SET
            mempool_price = ?,
            diff_amount = utxoracle_price - ?,
            diff_percent = ((utxoracle_price - ?) / ?) * 100
        WHERE DATE(timestamp) = ?
          AND utxoracle_price IS NOT NULL
    """

    conn.execute(
        query,
        [exchange_price, exchange_price, exchange_price, exchange_price, date_str],
    )

    # Verify update
    result = conn.execute(
        "SELECT COUNT(*) FROM prices WHERE DATE(timestamp) = ? AND mempool_price IS NOT NULL",
        [date_str],
    ).fetchone()

    if result[0] > 0:
        logging.info(f"  [{date_str}] ✅ Updated {result[0]} record(s)")
    else:
        logging.warning(f"  [{date_str}] ⚠️  No records updated")


def backfill_missing_prices(max_days_back: int = 7, dry_run: bool = False) -> None:
    """
    Backfill missing exchange prices from mempool.space API.

    Args:
        max_days_back: How many days back to check
        dry_run: If True, don't write to database
    """
    with duckdb.connect(DUCKDB_PATH) as conn:
        # Find dates with missing exchange prices
        missing_dates = get_dates_with_missing_exchange_prices(conn, max_days_back)

        if not missing_dates:
            logging.info("✅ No missing exchange prices found")
            return

        logging.info(f"Backfilling {len(missing_dates)} dates...")

        for date_str in missing_dates:
            try:
                # Fetch exchange price from API
                exchange_price = fetch_exchange_price_for_date(date_str)

                if dry_run:
                    logging.info(
                        f"  [{date_str}] DRY RUN: Would update to ${exchange_price:,.2f}"
                    )
                else:
                    # Update database
                    update_exchange_price(conn, date_str, exchange_price)

                # Rate limiting (mempool.space public API)
                time.sleep(1)

            except Exception as e:
                logging.error(f"  [{date_str}] Failed to backfill: {e}")
                continue

        logging.info("✅ Backfill complete")


def backfill_specific_date(date_str: str, dry_run: bool = False) -> None:
    """
    Backfill exchange price for a specific date.

    Args:
        date_str: Date string (YYYY-MM-DD)
        dry_run: If True, don't write to database
    """
    try:
        # Fetch exchange price
        exchange_price = fetch_exchange_price_for_date(date_str)

        if dry_run:
            logging.info(f"DRY RUN: Would update {date_str} to ${exchange_price:,.2f}")
            return

        # Update database
        with duckdb.connect(DUCKDB_PATH) as conn:
            update_exchange_price(conn, date_str, exchange_price)

        logging.info(f"✅ Backfill complete for {date_str}")

    except Exception as e:
        logging.error(f"Failed to backfill {date_str}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill exchange prices from mempool.space"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days back to check (default: 7)"
    )
    parser.add_argument("--date", type=str, help="Backfill specific date (YYYY-MM-DD)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing",
    )

    args = parser.parse_args()

    logging.info("=" * 60)
    logging.info("Exchange Price Backfill Script")
    logging.info("=" * 60)
    logging.info(f"Database: {DUCKDB_PATH}")
    logging.info(f"API: {MEMPOOL_PUBLIC_API}")

    if args.dry_run:
        logging.info("⚠️  DRY RUN MODE - No changes will be written")

    logging.info("")

    if args.date:
        # Backfill specific date
        backfill_specific_date(args.date, dry_run=args.dry_run)
    else:
        # Backfill missing dates
        backfill_missing_prices(max_days_back=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
