#!/usr/bin/env python3
"""
UTXO Lifecycle Sync Script

Synchronizes UTXO lifecycle data from Bitcoin Core to DuckDB.
Supports incremental sync from last checkpoint.

Spec: 017-utxo-lifecycle-engine
Phase: 8 - Sync & API
Tasks: T057

Usage:
    python scripts/sync_utxo_lifecycle.py [--start-block N] [--end-block N] [--batch-size N]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.metrics.utxo_lifecycle import (
    init_schema,
    init_indexes,
    process_block_utxos,
    get_sync_state,
    update_sync_state,
    prune_old_utxos,
    BLOCKS_PER_DAY,
)
from scripts.models.metrics_models import AgeCohortsConfig

# =============================================================================
# Configuration
# =============================================================================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Database paths
UTXO_DB_PATH = os.getenv("UTXO_LIFECYCLE_DB_PATH", "data/utxo_lifecycle.duckdb")
MAIN_DB_PATH = os.getenv(
    "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)

# Processing configuration
DEFAULT_BATCH_SIZE = int(os.getenv("UTXO_BATCH_SIZE", "10000"))
RETENTION_DAYS = int(os.getenv("UTXO_RETENTION_DAYS", "180"))
PRUNING_ENABLED = os.getenv("UTXO_PRUNING_ENABLED", "true").lower() == "true"
SNAPSHOT_INTERVAL = int(os.getenv("UTXO_SNAPSHOT_INTERVAL", "144"))

# Age cohort configuration
STH_THRESHOLD_DAYS = int(os.getenv("UTXO_STH_THRESHOLD_DAYS", "155"))

# Electrs configuration
ELECTRS_URL = os.getenv("ELECTRS_HTTP_URL", "http://localhost:3001")


# =============================================================================
# Data Source Clients
# =============================================================================


def get_rpc_connection():
    """Get Bitcoin Core RPC connection using cookie auth or credentials."""
    try:
        from scripts.utils.bitcoin_rpc import get_rpc_client

        return get_rpc_client()
    except ImportError:
        logger.warning("bitcoin_rpc module not available, using fallback")

        # Fallback: direct RPC connection
        from bitcoinrpc.authproxy import AuthServiceProxy

        rpc_url = os.getenv("BITCOIN_RPC_URL", "http://127.0.0.1:8332")
        rpc_user = os.getenv("BITCOIN_RPC_USER", "")
        rpc_pass = os.getenv("BITCOIN_RPC_PASSWORD", "")

        if rpc_user and rpc_pass:
            # Use credentials from env
            parts = rpc_url.replace("http://", "").replace("https://", "")
            protocol = "https" if "https" in rpc_url else "http"
            auth_url = f"{protocol}://{rpc_user}:{rpc_pass}@{parts}"
            return AuthServiceProxy(auth_url)
        else:
            # Try cookie auth
            datadir = os.getenv("BITCOIN_DATADIR", os.path.expanduser("~/.bitcoin"))
            cookie_path = Path(datadir) / ".cookie"
            if cookie_path.exists():
                cookie = cookie_path.read_text().strip()
                user, password = cookie.split(":")
                parts = rpc_url.replace("http://", "").replace("https://", "")
                protocol = "https" if "https" in rpc_url else "http"
                auth_url = f"{protocol}://{user}:{password}@{parts}"
                return AuthServiceProxy(auth_url)
            raise RuntimeError("No RPC credentials available")


# =============================================================================
# Electrs HTTP API Client
# =============================================================================


def get_block_from_electrs(block_height: int) -> dict:
    """Fetch block data from electrs HTTP API.

    Converts electrs format to the format expected by process_block_utxos:
    - value: satoshi -> BTC
    - vout: add 'n' index field
    - block: add 'height' and 'time' from status

    Args:
        block_height: Block height to fetch.

    Returns:
        Block data dict compatible with process_block_utxos.
    """
    import requests

    # Get block hash from height
    resp = requests.get(f"{ELECTRS_URL}/block-height/{block_height}", timeout=30)
    resp.raise_for_status()
    block_hash = resp.text.strip()

    # Get block metadata (for timestamp)
    resp = requests.get(f"{ELECTRS_URL}/block/{block_hash}", timeout=30)
    resp.raise_for_status()
    block_meta = resp.json()
    block_time = block_meta.get("timestamp", 0)

    # Fetch all transactions (paginated, 25 per page)
    all_txs = []
    start_index = 0
    while True:
        resp = requests.get(
            f"{ELECTRS_URL}/block/{block_hash}/txs/{start_index}",
            timeout=60,
        )
        resp.raise_for_status()
        txs = resp.json()
        if not txs:
            break
        all_txs.extend(txs)
        if len(txs) < 25:
            break
        start_index += 25

    # Convert electrs format to expected format
    converted_txs = []
    for tx in all_txs:
        converted_tx = {
            "txid": tx["txid"],
            "vout": [],
            "vin": [],
        }

        # Convert vouts: satoshi -> BTC, add 'n' index
        for i, vout in enumerate(tx.get("vout", [])):
            converted_tx["vout"].append(
                {
                    "value": vout.get("value", 0) / 100_000_000,  # satoshi -> BTC
                    "n": i,
                    "scriptPubKey": {
                        "address": vout.get("scriptpubkey_address", ""),
                        "type": vout.get("scriptpubkey_type", ""),
                    },
                }
            )

        # Convert vins
        for vin in tx.get("vin", []):
            converted_vin = {
                "txid": vin.get("txid", ""),
                "vout": vin.get("vout", 0),
            }
            # Include prevout if available (electrs provides this!)
            if "prevout" in vin and vin["prevout"]:
                converted_vin["prevout"] = {
                    "value": vin["prevout"].get("value", 0) / 100_000_000,
                    "scriptpubkey_address": vin["prevout"].get(
                        "scriptpubkey_address", ""
                    ),
                }
            converted_tx["vin"].append(converted_vin)

        converted_txs.append(converted_tx)

    return {
        "height": block_height,
        "time": block_time,
        "tx": converted_txs,
        "hash": block_hash,
    }


def get_current_block_height_electrs() -> int:
    """Get current blockchain height from electrs."""
    import requests

    resp = requests.get(f"{ELECTRS_URL}/blocks/tip/height", timeout=10)
    resp.raise_for_status()
    return int(resp.text.strip())


def get_utxoracle_price(block_height: int, main_db: duckdb.DuckDBPyConnection) -> float:
    """Get UTXOracle price for a block height from main database."""
    try:
        # Try intraday_prices first (has block_height)
        result = main_db.execute(
            """
            SELECT price
            FROM intraday_prices
            WHERE block_height <= ?
            ORDER BY block_height DESC
            LIMIT 1
            """,
            [block_height],
        ).fetchone()

        if result and result[0]:
            return float(result[0])

        # Fallback: use price_analysis (daily prices)
        result = main_db.execute(
            "SELECT utxoracle_price FROM price_analysis ORDER BY date DESC LIMIT 1"
        ).fetchone()

        if result and result[0]:
            return float(result[0])

        # Last resort: return a placeholder
        logger.warning(f"No price found for block {block_height}, using 50000.0")
        return 50000.0

    except Exception as e:
        logger.error(f"Error fetching price for block {block_height}: {e}")
        return 50000.0


# =============================================================================
# Sync Functions
# =============================================================================


def sync_blocks(
    utxo_db: duckdb.DuckDBPyConnection,
    main_db: duckdb.DuckDBPyConnection,
    start_block: int,
    end_block: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    age_config: Optional[AgeCohortsConfig] = None,
) -> tuple[int, int, int]:
    """
    Sync blocks from Bitcoin Core to UTXO lifecycle database.

    Returns:
        Tuple of (blocks_processed, utxos_created, utxos_spent)
    """
    if age_config is None:
        age_config = AgeCohortsConfig(sth_threshold_days=STH_THRESHOLD_DAYS)

    rpc = get_rpc_connection()

    total_created = 0
    total_spent = 0
    blocks_processed = 0
    # Track what we've already reported to avoid double-counting
    reported_created = 0
    reported_spent = 0

    for block_height in range(start_block, end_block + 1):
        try:
            # Get block data from Bitcoin Core
            block_hash = rpc.getblockhash(block_height)
            block_data = rpc.getblock(block_hash, 2)  # Verbosity 2 for full tx data

            # Get price for this block
            block_price = get_utxoracle_price(block_height, main_db)

            # Process block
            created, spent = process_block_utxos(
                utxo_db, block_data, block_price, age_config
            )

            total_created += len(created)
            total_spent += len(spent)
            blocks_processed += 1

            # Update sync state periodically
            if blocks_processed % 100 == 0:
                block_time = datetime.fromtimestamp(block_data["time"])
                # Pass only the delta since last report to avoid double-counting
                # since update_sync_state accumulates internally
                delta_created = total_created - reported_created
                delta_spent = total_spent - reported_spent
                update_sync_state(
                    utxo_db,
                    block_height,
                    block_time,
                    delta_created,
                    delta_spent,
                )
                reported_created = total_created
                reported_spent = total_spent
                logger.info(
                    f"Processed block {block_height}: "
                    f"created={len(created)}, spent={len(spent)}, "
                    f"total_created={total_created}, total_spent={total_spent}"
                )

        except Exception as e:
            logger.error(f"Error processing block {block_height}: {e}")
            raise

    # Final sync state update - only report unreported counts
    if blocks_processed > 0:
        try:
            block_hash = rpc.getblockhash(end_block)
            block_data = rpc.getblock(block_hash, 1)
            block_time = datetime.fromtimestamp(block_data["time"])
            # Pass only the remaining unreported counts
            delta_created = total_created - reported_created
            delta_spent = total_spent - reported_spent
            update_sync_state(
                utxo_db, end_block, block_time, delta_created, delta_spent
            )
        except Exception as e:
            logger.warning(f"Failed to update final sync state: {e}")

    return blocks_processed, total_created, total_spent


def sync_blocks_electrs(
    utxo_db: duckdb.DuckDBPyConnection,
    main_db: duckdb.DuckDBPyConnection,
    start_block: int,
    end_block: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    age_config: Optional[AgeCohortsConfig] = None,
) -> tuple[int, int, int]:
    """
    Sync blocks from electrs HTTP API to UTXO lifecycle database.

    Faster than RPC because electrs includes prevout data inline.

    Returns:
        Tuple of (blocks_processed, utxos_created, utxos_spent)
    """
    if age_config is None:
        age_config = AgeCohortsConfig(sth_threshold_days=STH_THRESHOLD_DAYS)

    total_created = 0
    total_spent = 0
    blocks_processed = 0
    reported_created = 0
    reported_spent = 0

    for block_height in range(start_block, end_block + 1):
        try:
            # Get block data from electrs
            block_data = get_block_from_electrs(block_height)

            # Get price for this block
            block_price = get_utxoracle_price(block_height, main_db)

            # Process block
            created, spent = process_block_utxos(
                utxo_db, block_data, block_price, age_config
            )

            total_created += len(created)
            total_spent += len(spent)
            blocks_processed += 1

            # Update sync state periodically
            if blocks_processed % 100 == 0:
                block_time = datetime.fromtimestamp(block_data["time"])
                delta_created = total_created - reported_created
                delta_spent = total_spent - reported_spent
                update_sync_state(
                    utxo_db,
                    block_height,
                    block_time,
                    delta_created,
                    delta_spent,
                )
                reported_created = total_created
                reported_spent = total_spent
                logger.info(
                    f"[electrs] Processed block {block_height}: "
                    f"created={len(created)}, spent={len(spent)}, "
                    f"total_created={total_created}, total_spent={total_spent}"
                )

        except Exception as e:
            logger.error(f"Error processing block {block_height}: {e}")
            raise

    # Final sync state update
    if blocks_processed > 0:
        try:
            block_data = get_block_from_electrs(end_block)
            block_time = datetime.fromtimestamp(block_data["time"])
            delta_created = total_created - reported_created
            delta_spent = total_spent - reported_spent
            update_sync_state(
                utxo_db, end_block, block_time, delta_created, delta_spent
            )
        except Exception as e:
            logger.warning(f"Failed to update final sync state: {e}")

    return blocks_processed, total_created, total_spent


def get_current_block_height() -> int:
    """Get current blockchain height from Bitcoin Core."""
    rpc = get_rpc_connection()
    return rpc.getblockcount()


def run_sync(
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    prune: bool = PRUNING_ENABLED,
    source: str = "electrs",
) -> dict:
    """
    Run the UTXO lifecycle sync process.

    Args:
        start_block: Starting block (None = resume from last checkpoint)
        end_block: Ending block (None = current chain tip)
        batch_size: Number of UTXOs per batch
        prune: Whether to prune old spent UTXOs
        source: Data source ("electrs" or "rpc")

    Returns:
        Dict with sync statistics
    """
    start_time = time.time()

    # Ensure database directory exists
    db_path = Path(UTXO_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Connect to databases
    utxo_db = duckdb.connect(str(db_path))
    main_db = duckdb.connect(MAIN_DB_PATH, read_only=True)

    # Select height getter based on source
    get_height = (
        get_current_block_height_electrs
        if source == "electrs"
        else get_current_block_height
    )

    try:
        # Initialize schema if needed
        init_schema(utxo_db)
        init_indexes(utxo_db)

        # Determine start block
        if start_block is None:
            sync_state = get_sync_state(utxo_db)
            if sync_state:
                start_block = sync_state.last_processed_block + 1
                logger.info(f"Resuming from block {start_block}")
            else:
                # Default: start from 6 months ago
                current_height = get_height()
                start_block = max(0, current_height - (RETENTION_DAYS * BLOCKS_PER_DAY))
                logger.info(f"Starting fresh sync from block {start_block}")

        # Determine end block
        if end_block is None:
            end_block = get_height()

        if start_block > end_block:
            logger.info("Already synced to chain tip")
            return {
                "status": "up_to_date",
                "blocks_processed": 0,
                "utxos_created": 0,
                "utxos_spent": 0,
            }

        logger.info(f"Syncing blocks {start_block} to {end_block} (source: {source})")

        # Run sync based on source
        if source == "electrs":
            blocks, created, spent = sync_blocks_electrs(
                utxo_db, main_db, start_block, end_block, batch_size
            )
        else:
            blocks, created, spent = sync_blocks(
                utxo_db, main_db, start_block, end_block, batch_size
            )

        # Prune old UTXOs if enabled
        pruned = 0
        if prune and blocks > 0:
            retention_blocks = RETENTION_DAYS * BLOCKS_PER_DAY
            pruned = prune_old_utxos(utxo_db, retention_blocks, end_block)
            logger.info(f"Pruned {pruned} old spent UTXOs")

        elapsed = time.time() - start_time

        return {
            "status": "completed",
            "blocks_processed": blocks,
            "utxos_created": created,
            "utxos_spent": spent,
            "utxos_pruned": pruned,
            "start_block": start_block,
            "end_block": end_block,
            "elapsed_seconds": round(elapsed, 2),
            "blocks_per_second": round(blocks / elapsed, 2) if elapsed > 0 else 0,
        }

    finally:
        utxo_db.close()
        main_db.close()


# =============================================================================
# CLI Entry Point
# =============================================================================


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Sync UTXO lifecycle data from electrs or Bitcoin Core RPC"
    )
    parser.add_argument(
        "--start-block",
        type=int,
        default=None,
        help="Starting block height (default: resume from last checkpoint)",
    )
    parser.add_argument(
        "--end-block",
        type=int,
        default=None,
        help="Ending block height (default: current chain tip)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"UTXOs per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--source",
        choices=["electrs", "rpc"],
        default="electrs",
        help="Data source: electrs (default, faster) or rpc (Bitcoin Core RPC)",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Disable automatic pruning of old spent UTXOs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing",
    )

    args = parser.parse_args()

    if args.dry_run:
        # Connect to UTXO database to check sync state
        db_path = Path(UTXO_DB_PATH)
        if db_path.exists():
            utxo_db = duckdb.connect(str(db_path), read_only=True)
            sync_state = get_sync_state(utxo_db)
            utxo_db.close()

            if sync_state:
                print(f"Last synced block: {sync_state.last_processed_block}")
                print(f"Last sync time: {sync_state.last_processed_timestamp}")
                print(f"Total UTXOs created: {sync_state.total_utxos_created}")
                print(f"Total UTXOs spent: {sync_state.total_utxos_spent}")
            else:
                print("No sync state found - would start fresh sync")
        else:
            print(f"Database not found at {db_path} - would create new")

        # Use appropriate height getter based on source
        if args.source == "electrs":
            current_height = get_current_block_height_electrs()
        else:
            current_height = get_current_block_height()
        start = args.start_block or (
            sync_state.last_processed_block + 1
            if sync_state
            else current_height - 25920
        )
        end = args.end_block or current_height

        print(f"Would sync blocks {start} to {end} ({end - start + 1} blocks)")
        print(f"Data source: {args.source}")
        return

    try:
        result = run_sync(
            start_block=args.start_block,
            end_block=args.end_block,
            batch_size=args.batch_size,
            prune=not args.no_prune,
            source=args.source,
        )

        print("\nSync completed:")
        for key, value in result.items():
            print(f"  {key}: {value}")

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
