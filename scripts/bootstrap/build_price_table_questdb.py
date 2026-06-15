#!/usr/bin/env python3
"""Build QuestDB daily_prices from mempool.space historical prices.

Production replacement for ``build_price_table.py``. This module never opens
DuckDB: it reads the current QuestDB max(date), fetches BTC/USD prices, and
streams daily price rows to QuestDB via ILP.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiohttp

from api.questdb_repository import _open_pg_sync

logger = logging.getLogger(__name__)
DEFAULT_MEMPOOL_URL = "http://localhost:8999"
DEFAULT_START_DATE = date(2011, 1, 1)
DEFAULT_BATCH_SIZE = 100
DEFAULT_RATE_LIMIT = 50


def _resolve_log_level(raw_level: str | None) -> int:
    if (
        not raw_level
        or raw_level.startswith("ENC[")
        or raw_level.startswith("encrypted:")
    ):
        return logging.INFO
    level = getattr(logging, raw_level.upper(), None)
    return level if isinstance(level, int) else logging.INFO


def _open_sender():
    from questdb.ingress import Sender

    host = os.getenv("QUESTDB_ILP_HOST", "localhost")
    port = int(os.getenv("QUESTDB_ILP_PORT", "9009"))
    return Sender.from_conf(f"tcp::addr={host}:{port};")


def _normalize_questdb_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def resolve_questdb_start_date() -> date:
    """Return max(date)+1 from QuestDB daily_prices, or historical default."""
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max(date) FROM daily_prices")
            row = cur.fetchone()
    max_date = _normalize_questdb_date(row[0] if row else None)
    if max_date is None:
        return DEFAULT_START_DATE
    return max_date + timedelta(days=1)


def _iter_dates(start_date: date, end_date: date) -> list[date]:
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _date_to_timestamp(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


async def fetch_historical_price(
    timestamp: int,
    session: aiohttp.ClientSession,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
) -> Optional[float]:
    """Fetch one historical BTC/USD price from the mempool.space API."""
    url = f"{mempool_url}/api/v1/historical-price?currency=USD&timestamp={timestamp}"
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(
                    "Failed to fetch price for timestamp %s: HTTP %s",
                    timestamp,
                    response.status,
                )
                return None
            data = await response.json()
    except Exception as exc:
        logger.error("Error fetching price for timestamp %s: %s", timestamp, exc)
        return None

    prices = data.get("prices", [])
    if not prices:
        return None
    price = prices[0].get("USD")
    if price is None or price == 0:
        return None
    return float(price)


async def fetch_prices_batch(
    dates: list[date],
    session: aiohttp.ClientSession,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> dict[date, Optional[float]]:
    """Fetch a batch of daily prices keyed by date."""
    results: dict[date, Optional[float]] = {}

    async def fetch_with_limit(price_date: date) -> tuple[date, Optional[float]]:
        timestamp = int(datetime.combine(price_date, datetime.min.time()).timestamp())
        if semaphore is not None:
            async with semaphore:
                price = await fetch_historical_price(timestamp, session, mempool_url)
        else:
            price = await fetch_historical_price(timestamp, session, mempool_url)
        return price_date, price

    completed = await asyncio.gather(
        *(fetch_with_limit(price_date) for price_date in dates),
        return_exceptions=True,
    )
    for item in completed:
        if isinstance(item, Exception):
            logger.error("Batch price fetch error: %s", item)
            continue
        price_date, price = item
        results[price_date] = price
    return results


async def build_price_table(
    start_date: date,
    end_date: date,
    *,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rate_limit: int = DEFAULT_RATE_LIMIT,
) -> int:
    """Stream daily BTC/USD prices to QuestDB. Returns emitted row count."""
    if end_date < start_date:
        logger.info("Already fresh: start=%s end=%s", start_date, end_date)
        return 0

    all_dates = _iter_dates(start_date, end_date)
    logger.info("Fetching %d daily prices (%s to %s)", len(all_dates), start_date, end_date)

    sender = _open_sender()
    rows = 0
    fetched_at = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(rate_limit)
    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit)
    timeout = aiohttp.ClientTimeout(total=30)

    try:
        sender.establish()
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for i in range(0, len(all_dates), batch_size):
                batch = all_dates[i : i + batch_size]
                prices = await fetch_prices_batch(
                    batch,
                    session,
                    mempool_url,
                    semaphore,
                )
                for price_date, price in sorted(prices.items()):
                    if price is None:
                        continue
                    sender.row(
                        "daily_prices",
                        symbols={"source": "mempool_space"},
                        columns={
                            "price_usd": float(price),
                            "fetched_at": fetched_at,
                        },
                        at=_date_to_timestamp(price_date),
                    )
                    rows += 1
                sender.flush()
                logger.info(
                    "daily_prices progress: %d/%d candidate dates, rows=%d",
                    min(i + batch_size, len(all_dates)),
                    len(all_dates),
                    rows,
                )
    finally:
        try:
            sender.close()
        except Exception:
            pass

    logger.info("Inserted %d daily_prices rows into QuestDB", rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--mempool-url", default=DEFAULT_MEMPOOL_URL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--rate-limit", type=int, default=DEFAULT_RATE_LIMIT)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else _resolve_log_level(os.getenv("LOG_LEVEL")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    start_date = (
        datetime.strptime(args.start_date, "%Y-%m-%d").date()
        if args.start_date
        else resolve_questdb_start_date()
    )
    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").date()
        if args.end_date
        else date.today() - timedelta(days=1)
    )
    return asyncio.run(
        build_price_table(
            start_date,
            end_date,
            mempool_url=args.mempool_url,
            batch_size=args.batch_size,
            rate_limit=args.rate_limit,
        )
    ) and 0


if __name__ == "__main__":
    raise SystemExit(main())
