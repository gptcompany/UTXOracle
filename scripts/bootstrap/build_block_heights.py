"""Build block heights table from electrs API or Bitcoin Core RPC.

Maps block height -> timestamp for UTXO lifecycle price lookups.

Primary: Bitcoin Core RPC (getblockhash + getblockheader, 2 calls per block, local)
Fallback: electrs /block-height/{h} and /block/{hash} endpoints (2 calls per block, HTTP)

Usage:
    python -m scripts.bootstrap.build_block_heights --db-path data/utxo_lifecycle.duckdb

    # Use Bitcoin Core RPC (faster)
    python -m scripts.bootstrap.build_block_heights --use-rpc --rpc-cookie ~/.bitcoin/.cookie

API Endpoints (electrs fallback):
    GET /block-height/{height} -> block hash (text)
    GET /block/{hash} -> {"timestamp": unix_ts, "height": int, ...}
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp
import duckdb

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_ELECTRS_URL = "http://localhost:3001"
DEFAULT_RPC_URL = "http://localhost:8332"
DEFAULT_BATCH_SIZE = 500  # heights per batch (increased from 100)
DEFAULT_RATE_LIMIT = 50  # max concurrent requests (increased from 30)
DEFAULT_INSERT_BATCH_SIZE = 1000  # rows per INSERT batch


def create_block_heights_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create block_heights table schema.

    Args:
        conn: DuckDB connection
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS block_heights (
            height INTEGER PRIMARY KEY,
            timestamp BIGINT NOT NULL,
            block_hash VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create index for timestamp lookups
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_block_heights_timestamp
        ON block_heights(timestamp)
    """)
    logger.info("Created block_heights table schema")


def batch_insert_heights(
    conn: duckdb.DuckDBPyConnection,
    records: list[tuple[int, int, Optional[str]]],
) -> int:
    """Batch insert block height records.

    Args:
        conn: DuckDB connection
        records: List of (height, timestamp, block_hash) tuples

    Returns:
        Number of rows actually inserted (excludes duplicates)
    """
    if not records:
        return 0

    # Count rows before insertion to track actual inserts
    count_before = conn.execute("SELECT COUNT(*) FROM block_heights").fetchone()[0]

    # Use INSERT OR IGNORE to skip duplicates
    for height, timestamp, block_hash in records:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO block_heights (height, timestamp, block_hash) VALUES (?, ?, ?)",
                [height, timestamp, block_hash],
            )
        except Exception:
            pass  # Skip duplicates

    # Return actual rows inserted
    count_after = conn.execute("SELECT COUNT(*) FROM block_heights").fetchone()[0]
    return count_after - count_before


# =============================================================================
# Bitcoin Core RPC Functions (Primary - faster local calls vs HTTP)
# =============================================================================


def parse_bitcoin_cookie(cookie_path: str) -> tuple[str, str]:
    """Parse Bitcoin Core cookie file for RPC auth.

    Args:
        cookie_path: Path to .cookie file

    Returns:
        Tuple of (username, password)
    """
    cookie_file = Path(cookie_path)
    if not cookie_file.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    content = cookie_file.read_text().strip()
    if ":" not in content:
        raise ValueError(f"Invalid cookie format: {cookie_path}")

    return tuple(content.split(":", 1))


async def rpc_getblockheader(
    height: int,
    session: aiohttp.ClientSession,
    rpc_url: str,
    auth: aiohttp.BasicAuth,
) -> Optional[tuple[int, str]]:
    """Get block header via Bitcoin Core RPC.

    Args:
        height: Block height
        session: aiohttp session
        rpc_url: Bitcoin Core RPC URL
        auth: Basic auth credentials

    Returns:
        Tuple of (timestamp, block_hash) or None if failed
    """
    # First get block hash from height
    payload_hash = {
        "jsonrpc": "1.0",
        "id": f"getblockhash_{height}",
        "method": "getblockhash",
        "params": [height],
    }

    try:
        async with session.post(rpc_url, json=payload_hash, auth=auth) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if "error" in data and data["error"]:
                return None
            block_hash = data["result"]

        # Now get block header
        payload_header = {
            "jsonrpc": "1.0",
            "id": f"getblockheader_{height}",
            "method": "getblockheader",
            "params": [block_hash],
        }

        async with session.post(rpc_url, json=payload_header, auth=auth) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if "error" in data and data["error"]:
                return None
            header = data["result"]
            return (header["time"], block_hash)

    except Exception as e:
        logger.debug("RPC error for height %d: %s", height, type(e).__name__)
        return None


async def batch_fetch_rpc(
    heights: list[int],
    session: aiohttp.ClientSession,
    rpc_url: str,
    auth: aiohttp.BasicAuth,
    semaphore: asyncio.Semaphore,
) -> dict[int, tuple[int, str]]:
    """Batch fetch block headers via RPC.

    Args:
        heights: List of heights to fetch
        session: aiohttp session
        rpc_url: Bitcoin Core RPC URL
        auth: Basic auth credentials
        semaphore: Concurrency limiter

    Returns:
        Dict mapping height -> (timestamp, block_hash)
    """
    results: dict[int, tuple[int, str]] = {}

    async def fetch_one(h: int) -> tuple[int, Optional[tuple[int, str]]]:
        async with semaphore:
            result = await rpc_getblockheader(h, session, rpc_url, auth)
            return h, result

    tasks = [fetch_one(h) for h in heights]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for item in completed:
        if isinstance(item, Exception):
            logger.debug(f"RPC batch error: {item}")
        elif item[1] is not None:
            h, data = item
            results[h] = data

    return results


async def build_block_heights_table_rpc(
    conn: duckdb.DuckDBPyConnection,
    start_height: int = 0,
    end_height: Optional[int] = None,
    rpc_url: str = DEFAULT_RPC_URL,
    cookie_path: Optional[str] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rate_limit: int = DEFAULT_RATE_LIMIT,
) -> int:
    """Build block heights table using Bitcoin Core RPC (faster).

    Args:
        conn: DuckDB connection
        start_height: First block height
        end_height: Last block height (default: from RPC)
        rpc_url: Bitcoin Core RPC URL
        cookie_path: Path to .cookie file
        batch_size: Heights per batch
        rate_limit: Max concurrent requests

    Returns:
        Number of heights inserted
    """
    # Create schema
    create_block_heights_schema(conn)

    # Parse cookie for auth
    if cookie_path is None:
        # Try default locations
        for path in [
            Path.home() / ".bitcoin" / ".cookie",
            Path("/media/sam/3TB-WDC/Bitcoin/.cookie"),
        ]:
            if path.exists():
                cookie_path = str(path)
                break

    if cookie_path is None:
        raise FileNotFoundError("Could not find Bitcoin Core cookie file")

    user, password = parse_bitcoin_cookie(cookie_path)
    auth = aiohttp.BasicAuth(user, password)
    logger.info(f"Using RPC auth from: {cookie_path}")

    # Get current tip if end_height not specified
    if end_height is None:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "1.0",
                "id": "getblockcount",
                "method": "getblockcount",
                "params": [],
            }
            async with session.post(rpc_url, json=payload, auth=auth) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"RPC getblockcount failed: HTTP {resp.status}")
                data = await resp.json()
                end_height = data["result"]
        logger.info(f"Current blockchain tip: {end_height}")

    # Check existing heights
    existing = set()
    try:
        result = conn.execute("SELECT height FROM block_heights").fetchall()
        existing = {row[0] for row in result}
        logger.info(f"Found {len(existing)} existing height records")
    except Exception:
        pass

    # Heights to fetch
    all_heights = [h for h in range(start_height, end_height + 1) if h not in existing]
    logger.info(f"Need to fetch {len(all_heights)} heights via RPC")

    if not all_heights:
        logger.info("All heights already fetched")
        return 0

    # Fetch with RPC
    total_inserted = 0
    semaphore = asyncio.Semaphore(rate_limit)

    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit)
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for i in range(0, len(all_heights), batch_size):
            batch = all_heights[i : i + batch_size]

            results = await batch_fetch_rpc(batch, session, rpc_url, auth, semaphore)

            # Batch insert
            records = [(h, ts, hash_) for h, (ts, hash_) in results.items()]
            inserted = batch_insert_heights(conn, records)
            total_inserted += inserted

            # Progress
            progress = min(i + batch_size, len(all_heights)) / len(all_heights) * 100
            logger.info(
                f"Progress: {progress:.1f}% ({total_inserted}/{len(all_heights)} inserted)"
            )

    logger.info(f"Completed via RPC: {total_inserted} heights inserted")
    return total_inserted


# =============================================================================
# Electrs API Functions (Fallback - slower, 2 calls per block)
# =============================================================================


async def fetch_block_timestamp(
    height: int,
    session: Optional[aiohttp.ClientSession] = None,
    electrs_url: str = DEFAULT_ELECTRS_URL,
) -> Optional[int]:
    """Fetch block timestamp for a given height from electrs.

    Args:
        height: Block height
        session: Optional aiohttp session
        electrs_url: Base URL for electrs API

    Returns:
        Unix timestamp or None if failed
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        # Step 1: Get block hash from height
        hash_url = f"{electrs_url}/block-height/{height}"
        async with session.get(hash_url) as response:
            if response.status != 200:
                logger.warning(
                    f"Failed to get hash for height {height}: HTTP {response.status}"
                )
                return None
            block_hash = (await response.text()).strip()

        # Step 2: Get block metadata from hash
        meta_url = f"{electrs_url}/block/{block_hash}"
        async with session.get(meta_url) as response:
            if response.status != 200:
                logger.warning(
                    f"Failed to get metadata for block {block_hash}: HTTP {response.status}"
                )
                return None
            data = await response.json()
            return data.get("timestamp")

    except Exception as e:
        logger.error(f"Error fetching timestamp for height {height}: {e}")
        return None
    finally:
        if close_session:
            await session.close()


async def batch_fetch_block_timestamps(
    heights: list[int],
    session: Optional[aiohttp.ClientSession] = None,
    electrs_url: str = DEFAULT_ELECTRS_URL,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> dict[int, Optional[int]]:
    """Fetch timestamps for multiple block heights concurrently.

    Args:
        heights: List of block heights
        session: Optional aiohttp session
        electrs_url: Base URL for electrs API
        semaphore: Optional semaphore for rate limiting

    Returns:
        Dict mapping height -> timestamp (or None if failed)
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    results: dict[int, Optional[int]] = {}

    async def fetch_with_limit(h: int) -> tuple[int, Optional[int]]:
        if semaphore:
            async with semaphore:
                ts = await fetch_block_timestamp(h, session, electrs_url)
        else:
            ts = await fetch_block_timestamp(h, session, electrs_url)
        return h, ts

    try:
        tasks = [fetch_with_limit(h) for h in heights]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Batch fetch error: {result}")
            else:
                h, ts = result
                results[h] = ts

    finally:
        if close_session:
            await session.close()

    return results


async def build_block_heights_table(
    conn: duckdb.DuckDBPyConnection,
    start_height: int = 0,
    end_height: Optional[int] = None,
    electrs_url: str = DEFAULT_ELECTRS_URL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rate_limit: int = DEFAULT_RATE_LIMIT,
) -> int:
    """Build complete block heights table.

    Args:
        conn: DuckDB connection
        start_height: First block height (default: 0)
        end_height: Last block height (default: current tip)
        electrs_url: Base URL for electrs API
        batch_size: Heights per batch
        rate_limit: Max concurrent requests

    Returns:
        Number of heights inserted
    """
    # Create schema
    create_block_heights_schema(conn)

    # Get current tip if end_height not specified
    if end_height is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{electrs_url}/blocks/tip/height") as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Failed to get tip height: HTTP {response.status}"
                    )
                end_height = int((await response.text()).strip())
        logger.info(f"Current blockchain tip: {end_height}")

    # Check existing heights to avoid duplicates
    existing = set()
    try:
        result = conn.execute("SELECT height FROM block_heights").fetchall()
        existing = {row[0] for row in result}
        logger.info(f"Found {len(existing)} existing height records")
    except Exception:
        pass

    # Generate list of heights to fetch
    all_heights = [h for h in range(start_height, end_height + 1) if h not in existing]
    logger.info(
        f"Need to fetch {len(all_heights)} heights ({start_height} to {end_height})"
    )

    if not all_heights:
        logger.info("All heights already fetched")
        return 0

    # Fetch heights in batches
    total_inserted = 0
    semaphore = asyncio.Semaphore(rate_limit)

    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for i in range(0, len(all_heights), batch_size):
            batch = all_heights[i : i + batch_size]
            logger.info(
                f"Fetching batch {i // batch_size + 1} ({len(batch)} heights)..."
            )

            timestamps = await batch_fetch_block_timestamps(
                batch, session, electrs_url, semaphore
            )

            # Batch insert (electrs doesn't give us hash, so use None)
            records = [(h, ts, None) for h, ts in timestamps.items() if ts is not None]
            inserted = batch_insert_heights(conn, records)
            total_inserted += inserted

            # Progress update
            progress = min(i + batch_size, len(all_heights)) / len(all_heights) * 100
            logger.info(
                f"Progress: {progress:.1f}% ({total_inserted} heights inserted)"
            )

    logger.info(f"Completed: {total_inserted} heights inserted")
    return total_inserted


def get_timestamp_for_height(
    conn: duckdb.DuckDBPyConnection,
    height: int,
) -> Optional[int]:
    """Get timestamp for a specific block height.

    Args:
        conn: DuckDB connection
        height: Block height

    Returns:
        Unix timestamp or None if not found
    """
    try:
        result = conn.execute(
            "SELECT timestamp FROM block_heights WHERE height = ?",
            [height],
        ).fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting timestamp for height {height}: {e}")
        return None


def get_height_for_timestamp(
    conn: duckdb.DuckDBPyConnection,
    timestamp: int,
) -> Optional[int]:
    """Get closest block height for a timestamp.

    Args:
        conn: DuckDB connection
        timestamp: Unix timestamp

    Returns:
        Block height or None if not found
    """
    try:
        # Find the closest block at or before the timestamp
        result = conn.execute(
            """
            SELECT height FROM block_heights
            WHERE timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [timestamp],
        ).fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting height for timestamp {timestamp}: {e}")
        return None


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build block heights table from electrs API or Bitcoin Core RPC"
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("DUCKDB_PATH", "data/utxo_lifecycle.duckdb"),
        help="Path to DuckDB database",
    )

    # Source selection
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--use-rpc",
        action="store_true",
        help="Use Bitcoin Core RPC (faster, requires running node)",
    )
    source_group.add_argument(
        "--use-electrs",
        action="store_true",
        default=True,
        help="Use electrs HTTP API (default, slower)",
    )

    # RPC options
    parser.add_argument(
        "--rpc-url",
        default=os.getenv("BITCOIN_RPC_URL", DEFAULT_RPC_URL),
        help="Bitcoin Core RPC URL",
    )
    parser.add_argument(
        "--rpc-cookie",
        default=os.getenv("BITCOIN_COOKIE_PATH"),
        help="Path to Bitcoin Core .cookie file",
    )

    # Electrs options
    parser.add_argument(
        "--electrs-url",
        default=os.getenv("ELECTRS_HTTP_URL", DEFAULT_ELECTRS_URL),
        help="Electrs HTTP API URL",
    )

    # Common options
    parser.add_argument(
        "--start-height",
        type=int,
        default=0,
        help="Start block height",
    )
    parser.add_argument(
        "--end-height",
        type=int,
        default=None,
        help="End block height (default: current tip)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Heights per batch (default: 500)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=DEFAULT_RATE_LIMIT,
        help="Max concurrent requests (default: 50)",
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

    # Connect to DuckDB
    conn = duckdb.connect(args.db_path)

    try:
        if args.use_rpc:
            logger.info("Using Bitcoin Core RPC mode (faster)")
            count = await build_block_heights_table_rpc(
                conn,
                start_height=args.start_height,
                end_height=args.end_height,
                rpc_url=args.rpc_url,
                cookie_path=args.rpc_cookie,
                batch_size=args.batch_size,
                rate_limit=args.rate_limit,
            )
        else:
            logger.info("Using electrs API mode (fallback)")
            count = await build_block_heights_table(
                conn,
                start_height=args.start_height,
                end_height=args.end_height,
                electrs_url=args.electrs_url,
                batch_size=args.batch_size,
                rate_limit=args.rate_limit,
            )
        print(f"Successfully inserted {count} block heights")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
