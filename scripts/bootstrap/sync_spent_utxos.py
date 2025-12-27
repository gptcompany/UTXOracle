"""Tier 2 Bootstrap: Incremental rpc-v3 sync for spent UTXOs.

This module handles syncing spent UTXO data via Bitcoin Core RPC verbosity=3.
It scans blocks for transaction inputs that spend UTXOs from our database,
updating them with spent metadata (spent_block, spent_timestamp, spent_price_usd).

Architecture: See docs/ARCHITECTURE.md section "UTXO Lifecycle Bootstrap Architecture"

Key Features:
- Uses rpc-v3 which includes prevout.height (required for SOPR calculation)
- Efficient batch processing with configurable parallel workers
- Tracks sync progress for resumption

Usage:
    # Sync spent UTXOs for blocks 800000-850000
    python -m scripts.bootstrap.sync_spent_utxos --start-block 800000 --end-block 850000

    # Resume from last checkpoint
    python -m scripts.bootstrap.sync_spent_utxos --resume
"""

from __future__ import annotations

import argparse

from scripts.config import UTXORACLE_DB_PATH
import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import duckdb

logger = logging.getLogger(__name__)


def get_unspent_utxo_txids(conn: duckdb.DuckDBPyConnection) -> set[str]:
    """Get set of txids for all unspent UTXOs.

    Used for efficient lookup when processing block inputs.

    Args:
        conn: DuckDB connection

    Returns:
        Set of txid strings for unspent UTXOs
    """
    result = conn.execute(
        "SELECT DISTINCT txid FROM utxo_lifecycle WHERE is_spent = FALSE OR is_spent IS NULL"
    ).fetchall()
    return {row[0] for row in result}


def mark_utxo_as_spent(
    conn: duckdb.DuckDBPyConnection,
    txid: str,
    vout: int,
    spent_block: int,
    spent_timestamp: int,
    spent_price_usd: float,
) -> bool:
    """Mark a specific UTXO as spent with metadata.

    Args:
        conn: DuckDB connection
        txid: Transaction ID of the UTXO
        vout: Output index
        spent_block: Block height where UTXO was spent
        spent_timestamp: Unix timestamp of spent block
        spent_price_usd: BTC/USD price at time of spending

    Returns:
        True if UTXO was found and updated, False otherwise
    """
    # First check if UTXO exists and is unspent
    exists = conn.execute(
        """
        SELECT 1 FROM utxo_lifecycle
        WHERE txid = ? AND vout = ? AND (is_spent = FALSE OR is_spent IS NULL)
        """,
        [txid, vout],
    ).fetchone()

    if not exists:
        return False

    # Update the UTXO
    conn.execute(
        """
        UPDATE utxo_lifecycle
        SET is_spent = TRUE,
            spent_block = ?,
            spent_timestamp = ?,
            spent_price_usd = ?
        WHERE txid = ? AND vout = ?
        """,
        [spent_block, spent_timestamp, spent_price_usd, txid, vout],
    )

    return True


def process_block_spent_utxos(
    conn: duckdb.DuckDBPyConnection,
    block_data: dict,
    block_price: float,
) -> int:
    """Process a block and mark spent UTXOs.

    Scans all transaction inputs in the block and marks matching UTXOs as spent.

    Args:
        conn: DuckDB connection
        block_data: Block data from rpc-v3 (includes prevout in vin)
        block_price: BTC/USD price for this block

    Returns:
        Number of UTXOs marked as spent
    """
    block_height = block_data["height"]
    block_time = block_data["time"]

    spent_count = 0

    for tx in block_data.get("tx", []):
        for vin in tx.get("vin", []):
            # Skip coinbase inputs
            if "coinbase" in vin:
                continue

            spent_txid = vin.get("txid", "")
            spent_vout = vin.get("vout", 0)

            if not spent_txid:
                continue

            # Try to mark this UTXO as spent
            if mark_utxo_as_spent(
                conn,
                txid=spent_txid,
                vout=spent_vout,
                spent_block=block_height,
                spent_timestamp=block_time,
                spent_price_usd=block_price,
            ):
                spent_count += 1

    return spent_count


def get_block_from_rpc_v3(rpc: Any, block_height: int) -> dict:
    """Fetch block data from Bitcoin Core using getblock verbosity=3.

    Bitcoin Core 25.0+ supports verbosity=3 which includes prevout data
    for all inputs, eliminating the need for additional lookups.

    Args:
        rpc: Bitcoin Core RPC connection
        block_height: Block height to fetch

    Returns:
        Block data dict with height, time, and transactions
    """
    block_hash = rpc.getblockhash(block_height)
    block_data = rpc.getblock(block_hash, 3)

    return {
        "height": block_data["height"],
        "time": block_data["time"],
        "tx": block_data.get("tx", []),
        "hash": block_hash,
    }


async def sync_spent_utxos_range(
    conn: duckdb.DuckDBPyConnection,
    start_block: int,
    end_block: int,
    rpc: Any,
    price_lookup: Callable[[int], float],
    workers: int = 10,
) -> dict:
    """Sync spent UTXOs for a range of blocks using rpc-v3.

    Args:
        conn: DuckDB connection
        start_block: First block to process
        end_block: Last block to process (inclusive)
        rpc: Bitcoin Core RPC connection
        price_lookup: Function to get price for a block height
        workers: Number of parallel block fetches

    Returns:
        Dict with sync statistics
    """
    stats = {
        "start_time": time.time(),
        "blocks_processed": 0,
        "utxos_spent": 0,
        "start_block": start_block,
        "end_block": end_block,
    }

    heights = list(range(start_block, end_block + 1))
    chunk_size = workers * 2

    logger.info(
        f"Starting spent UTXO sync: blocks {start_block}-{end_block} "
        f"({len(heights)} blocks, {workers} workers)"
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        loop = asyncio.get_running_loop()

        for chunk_start in range(0, len(heights), chunk_size):
            chunk_heights = heights[chunk_start : chunk_start + chunk_size]

            # Fetch blocks in parallel
            futures = [
                loop.run_in_executor(executor, get_block_from_rpc_v3, rpc, h)
                for h in chunk_heights
            ]
            blocks = await asyncio.gather(*futures, return_exceptions=True)

            # Filter successful results
            valid_blocks = [
                b for b in blocks if b is not None and not isinstance(b, Exception)
            ]

            # Process blocks sequentially (DuckDB not thread-safe)
            for block_data in sorted(valid_blocks, key=lambda b: b["height"]):
                try:
                    block_height = block_data["height"]
                    block_price = price_lookup(block_height)

                    spent_count = process_block_spent_utxos(
                        conn, block_data, block_price
                    )

                    stats["blocks_processed"] += 1
                    stats["utxos_spent"] += spent_count

                    if stats["blocks_processed"] % 100 == 0:
                        logger.info(
                            f"[rpc-v3] Block {block_height}: "
                            f"spent={spent_count}, total_spent={stats['utxos_spent']}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing block {block_data.get('height')}: {e}"
                    )
                    raise

    stats["duration_seconds"] = time.time() - stats["start_time"]
    return stats


def get_tier2_sync_state(conn: duckdb.DuckDBPyConnection) -> dict | None:
    """Get Tier 2 sync state from database.

    Returns:
        Dict with last_block and total_spent, or None if not synced
    """
    try:
        result = conn.execute(
            """
            SELECT last_block, total_spent, last_sync_time
            FROM tier2_sync_state
            ORDER BY last_sync_time DESC
            LIMIT 1
            """
        ).fetchone()

        if result:
            return {
                "last_block": result[0],
                "total_spent": result[1],
                "last_sync_time": result[2],
            }
    except Exception:
        # Table doesn't exist yet
        pass

    return None


def update_tier2_sync_state(
    conn: duckdb.DuckDBPyConnection,
    last_block: int,
    total_spent: int,
) -> None:
    """Update Tier 2 sync state in database.

    Args:
        conn: DuckDB connection
        last_block: Last processed block
        total_spent: Total UTXOs marked as spent
    """
    # Create table if not exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tier2_sync_state (
            last_block INTEGER,
            total_spent INTEGER,
            last_sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        "INSERT INTO tier2_sync_state (last_block, total_spent) VALUES (?, ?)",
        [last_block, total_spent],
    )


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Sync spent UTXOs via Bitcoin Core rpc-v3"
    )
    parser.add_argument(
        "--start-block",
        type=int,
        help="First block to process",
    )
    parser.add_argument(
        "--end-block",
        type=int,
        help="Last block to process (default: chain tip)",
    )
    parser.add_argument(
        "--db-path",
        default=str(UTXORACLE_DB_PATH),
        help="Path to UTXO lifecycle DuckDB database",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of parallel block fetches (default: 10)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last sync checkpoint",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Connect to database
    conn = duckdb.connect(args.db_path)

    try:
        # Get RPC connection
        from scripts.sync_utxo_lifecycle import BitcoinRPC

        rpc = BitcoinRPC()

        # Determine start block
        if args.resume:
            state = get_tier2_sync_state(conn)
            if state:
                args.start_block = state["last_block"] + 1
                logger.info(f"Resuming from block {args.start_block}")
            else:
                logger.error("No sync state found. Use --start-block instead.")
                return 1

        if args.start_block is None:
            logger.error("--start-block required (or use --resume)")
            return 1

        # Determine end block
        if args.end_block is None:
            args.end_block = rpc.getblockcount()

        if args.start_block > args.end_block:
            logger.info("Already synced to chain tip")
            return 0

        # Create price lookup function
        # TODO: Connect to main DB for prices
        def price_lookup(block_height: int) -> float:
            # Simplified price lookup - in production, use get_utxoracle_price
            return 50000.0  # Placeholder

        # Run sync
        stats = await sync_spent_utxos_range(
            conn,
            start_block=args.start_block,
            end_block=args.end_block,
            rpc=rpc,
            price_lookup=price_lookup,
            workers=args.workers,
        )

        # Update sync state
        update_tier2_sync_state(
            conn,
            last_block=args.end_block,
            total_spent=stats["utxos_spent"],
        )

        print("\n" + "=" * 60)
        print("TIER 2 SYNC COMPLETE")
        print("=" * 60)
        print(f"  Blocks: {stats['start_block']} - {stats['end_block']}")
        print(f"  Processed: {stats['blocks_processed']:,}")
        print(f"  UTXOs spent: {stats['utxos_spent']:,}")
        print(f"  Duration: {stats['duration_seconds']:.1f}s")
        print("=" * 60)

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
