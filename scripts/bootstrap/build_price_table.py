"""Build daily price table from mempool.space historical API.

Fetches BTC/USD prices from 2011 to present using the mempool.space
/api/v1/historical-price endpoint. Stores in DuckDB for UTXO lifecycle
price lookups.

Usage:
    python -m scripts.bootstrap.build_price_table --db-path data/utxo_lifecycle.duckdb

API Endpoint:
    GET /api/v1/historical-price?currency=USD&timestamp={unix}
    Returns: {"USD": 16.45}
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import aiohttp
import duckdb

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MEMPOOL_URL = "http://localhost:8999"
DEFAULT_START_DATE = date(2011, 1, 1)  # mempool has data from 2011
DEFAULT_BATCH_SIZE = 100  # concurrent requests
DEFAULT_RATE_LIMIT = 50  # max concurrent connections


def create_price_table_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create daily_prices table schema.

    Args:
        conn: DuckDB connection
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            date DATE PRIMARY KEY,
            price_usd DOUBLE NOT NULL,
            block_height INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.info("Created daily_prices table schema")


async def fetch_historical_price(
    timestamp: int,
    session: Optional[aiohttp.ClientSession] = None,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
) -> Optional[float]:
    """Fetch historical BTC/USD price from mempool API.

    Args:
        timestamp: Unix timestamp for the price
        session: Optional aiohttp session (creates new if None)
        mempool_url: Base URL for mempool API

    Returns:
        Price in USD or None if unavailable
    """
    url = f"{mempool_url}/api/v1/historical-price?currency=USD&timestamp={timestamp}"

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(
                    f"Failed to fetch price for timestamp {timestamp}: HTTP {response.status}"
                )
                return None

            data = await response.json()
            price = data.get("USD")

            if price is None or price == 0:
                return None

            return float(price)

    except Exception as e:
        logger.error(f"Error fetching price for timestamp {timestamp}: {e}")
        return None
    finally:
        if close_session:
            await session.close()


async def fetch_prices_batch(
    dates: list[date],
    session: aiohttp.ClientSession,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> dict[date, Optional[float]]:
    """Fetch prices for a batch of dates concurrently.

    Args:
        dates: List of dates to fetch
        session: aiohttp session
        mempool_url: Base URL for mempool API
        semaphore: Optional semaphore for rate limiting

    Returns:
        Dict mapping date -> price (or None if unavailable)
    """
    results: dict[date, Optional[float]] = {}

    async def fetch_with_limit(d: date) -> tuple[date, Optional[float]]:
        # Convert date to midnight UTC timestamp
        timestamp = int(datetime.combine(d, datetime.min.time()).timestamp())

        if semaphore:
            async with semaphore:
                price = await fetch_historical_price(timestamp, session, mempool_url)
        else:
            price = await fetch_historical_price(timestamp, session, mempool_url)

        return d, price

    tasks = [fetch_with_limit(d) for d in dates]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for result in completed:
        if isinstance(result, Exception):
            logger.error(f"Batch fetch error: {result}")
        else:
            d, price = result
            results[d] = price

    return results


async def build_price_table(
    conn: duckdb.DuckDBPyConnection,
    start_date: date = DEFAULT_START_DATE,
    end_date: Optional[date] = None,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rate_limit: int = DEFAULT_RATE_LIMIT,
) -> int:
    """Build complete price table from start_date to end_date.

    Args:
        conn: DuckDB connection
        start_date: First date to fetch (default: 2011-01-01)
        end_date: Last date to fetch (default: yesterday)
        mempool_url: Base URL for mempool API
        batch_size: Number of dates per batch
        rate_limit: Max concurrent requests

    Returns:
        Number of prices inserted
    """
    if end_date is None:
        end_date = date.today() - timedelta(days=1)

    # Create schema
    create_price_table_schema(conn)

    # Check existing dates to avoid duplicates
    existing = set()
    try:
        result = conn.execute("SELECT date FROM daily_prices").fetchall()
        existing = {row[0] for row in result}
        logger.info(f"Found {len(existing)} existing price records")
    except Exception:
        pass  # Table might be empty

    # Generate list of dates to fetch
    all_dates = []
    current = start_date
    while current <= end_date:
        if current not in existing:
            all_dates.append(current)
        current += timedelta(days=1)

    logger.info(f"Need to fetch {len(all_dates)} prices ({start_date} to {end_date})")

    if not all_dates:
        logger.info("All prices already fetched")
        return 0

    # Fetch prices in batches
    total_inserted = 0
    semaphore = asyncio.Semaphore(rate_limit)

    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for i in range(0, len(all_dates), batch_size):
            batch = all_dates[i : i + batch_size]
            logger.info(f"Fetching batch {i // batch_size + 1} ({len(batch)} dates)...")

            prices = await fetch_prices_batch(batch, session, mempool_url, semaphore)

            # Insert prices
            for d, price in prices.items():
                if price is not None:
                    try:
                        conn.execute(
                            "INSERT INTO daily_prices (date, price_usd) VALUES (?, ?)",
                            [d, price],
                        )
                        total_inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert price for {d}: {e}")

            # Progress update
            progress = min(i + batch_size, len(all_dates)) / len(all_dates) * 100
            logger.info(f"Progress: {progress:.1f}% ({total_inserted} prices inserted)")

    logger.info(f"Completed: {total_inserted} prices inserted")
    return total_inserted


def get_price_for_block_height(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    block_heights_table: str = "block_heights",
) -> Optional[float]:
    """Get price for a specific block height.

    Looks up the block timestamp, then finds the nearest daily price.

    Args:
        conn: DuckDB connection
        block_height: Block height to look up
        block_heights_table: Table with height->timestamp mapping

    Returns:
        Price in USD or None if not found
    """
    try:
        result = conn.execute(
            f"""
            SELECT p.price_usd
            FROM daily_prices p
            JOIN {block_heights_table} b ON CAST(to_timestamp(b.timestamp) AS DATE) = p.date
            WHERE b.height = ?
            """,
            [block_height],
        ).fetchone()

        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting price for block {block_height}: {e}")
        return None


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build daily price table from mempool.space API"
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("DUCKDB_PATH", "data/utxo_lifecycle.duckdb"),
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--mempool-url",
        default=os.getenv("MEMPOOL_API_URL", DEFAULT_MEMPOOL_URL),
        help="Mempool API URL",
    )
    parser.add_argument(
        "--start-date",
        default="2011-01-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date (YYYY-MM-DD), defaults to yesterday",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Dates per batch",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=DEFAULT_RATE_LIMIT,
        help="Max concurrent requests",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse dates
    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None

    # Connect to DuckDB
    conn = duckdb.connect(args.db_path)

    try:
        count = await build_price_table(
            conn,
            start_date=start,
            end_date=end,
            mempool_url=args.mempool_url,
            batch_size=args.batch_size,
            rate_limit=args.rate_limit,
        )
        print(f"Successfully inserted {count} daily prices")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
