"""Bootstrap UTXO lifecycle database using two-tier architecture.

Orchestrates the full bootstrap process:
1. Build daily_prices table from mempool API (2011-present)
2. Build block_heights table from electrs
3. Import chainstate CSV from bitcoin-utxo-dump
4. Compute creation prices for all UTXOs

Architecture: See docs/ARCHITECTURE.md section "UTXO Lifecycle Bootstrap Architecture"

Usage:
    # Full bootstrap (Tier 1)
    python -m scripts.bootstrap.bootstrap_utxo_lifecycle --csv-path utxos.csv

    # Check dependencies first
    python -m scripts.bootstrap.bootstrap_utxo_lifecycle --check-only

Prerequisites:
    - Bitcoin Core fully synced (chainstate available)
    - bitcoin-utxo-dump installed: go install github.com/in3rsha/bitcoin-utxo-dump@latest
    - mempool.space backend running (port 8999)
    - electrs HTTP API running (port 3001)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import time

import aiohttp
import duckdb

from scripts.bootstrap.build_block_heights import build_block_heights_table
from scripts.bootstrap.build_price_table import build_price_table
from scripts.bootstrap.import_chainstate import (
    compute_btc_values,
    compute_creation_prices,
    create_indexes,
    get_import_stats,
    import_chainstate_csv,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MEMPOOL_URL = "http://localhost:8999"
DEFAULT_ELECTRS_URL = "http://localhost:3001"
DEFAULT_BITCOIN_DATADIR = os.path.expanduser("~/.bitcoin")


def create_all_schemas(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all required table schemas.

    Args:
        conn: DuckDB connection
    """
    from scripts.bootstrap.build_block_heights import create_block_heights_schema
    from scripts.bootstrap.build_price_table import create_price_table_schema
    from scripts.bootstrap.import_chainstate import create_utxo_lifecycle_schema

    create_price_table_schema(conn)
    create_block_heights_schema(conn)
    create_utxo_lifecycle_schema(conn)

    logger.info("Created all table schemas")


async def check_dependencies() -> dict[str, bool]:
    """Check availability of all required dependencies.

    Returns:
        Dict mapping dependency name -> availability status
    """
    deps = {
        "bitcoin_core": False,
        "electrs": False,
        "mempool_api": False,
        "bitcoin_utxo_dump": False,
    }

    # Check Bitcoin Core via RPC
    try:
        result = subprocess.run(
            ["bitcoin-cli", "getblockchaininfo"],
            capture_output=True,
            timeout=10,
        )
        deps["bitcoin_core"] = result.returncode == 0
    except Exception as e:
        logger.debug(f"Bitcoin Core check failed: {e}")

    # Check electrs HTTP API
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{os.getenv('ELECTRS_HTTP_URL', DEFAULT_ELECTRS_URL)}/blocks/tip/height"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                deps["electrs"] = resp.status == 200
    except Exception as e:
        logger.debug(f"electrs check failed: {e}")

    # Check mempool API
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{os.getenv('MEMPOOL_API_URL', DEFAULT_MEMPOOL_URL)}/api/v1/prices"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                deps["mempool_api"] = resp.status == 200
    except Exception as e:
        logger.debug(f"mempool API check failed: {e}")

    # Check bitcoin-utxo-dump
    try:
        result = subprocess.run(
            ["bitcoin-utxo-dump", "--help"],
            capture_output=True,
            timeout=5,
        )
        deps["bitcoin_utxo_dump"] = result.returncode == 0
    except Exception as e:
        logger.debug(f"bitcoin-utxo-dump check failed: {e}")

    return deps


def run_bitcoin_utxo_dump(
    output_path: str,
    bitcoin_datadir: str = DEFAULT_BITCOIN_DATADIR,
) -> bool:
    """Run bitcoin-utxo-dump to export chainstate to CSV.

    Args:
        output_path: Path for output CSV file
        bitcoin_datadir: Bitcoin data directory

    Returns:
        True if successful
    """
    logger.info(f"Running bitcoin-utxo-dump to {output_path}...")

    chainstate_dir = os.path.join(bitcoin_datadir, "chainstate")
    if not os.path.exists(chainstate_dir):
        logger.error(f"Chainstate directory not found: {chainstate_dir}")
        return False

    try:
        # Run bitcoin-utxo-dump
        # Format: count,txid,vout,height,coinbase,amount,script_type,address
        cmd = [
            "bitcoin-utxo-dump",
            "-db",
            chainstate_dir,
            "-o",
            "csv",
            "-f",
            "txid,vout,height,coinbase,amount,script,address",
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        with open(output_path, "w") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=7200,  # 2 hour timeout
            )

        if result.returncode != 0:
            logger.error(f"bitcoin-utxo-dump failed: {result.stderr.decode()}")
            return False

        # Verify output
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"Generated CSV: {output_path} ({size / 1024 / 1024:.1f} MB)")
            return True

        return False

    except subprocess.TimeoutExpired:
        logger.error("bitcoin-utxo-dump timed out (>2 hours)")
        return False
    except Exception as e:
        logger.error(f"Failed to run bitcoin-utxo-dump: {e}")
        return False


async def bootstrap_tier1(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
    electrs_url: str = DEFAULT_ELECTRS_URL,
    skip_prices: bool = False,
    skip_heights: bool = False,
) -> dict:
    """Execute Tier 1 bootstrap (current UTXOs only).

    Steps:
    1. Build daily_prices table (if not skipped)
    2. Build block_heights table (if not skipped)
    3. Import chainstate CSV
    4. Compute BTC values and creation prices

    Args:
        conn: DuckDB connection
        csv_path: Path to chainstate CSV from bitcoin-utxo-dump
        mempool_url: Mempool API URL
        electrs_url: Electrs HTTP URL
        skip_prices: Skip price table build (if already populated)
        skip_heights: Skip heights table build (if already populated)

    Returns:
        Dict with bootstrap statistics
    """
    stats = {
        "start_time": time.time(),
        "prices_count": 0,
        "heights_count": 0,
        "utxos_count": 0,
        "total_btc": 0,
        "duration_seconds": 0,
    }

    # Step 1: Build price table
    if not skip_prices:
        logger.info("Step 1/4: Building daily_prices table...")
        start = time.time()
        stats["prices_count"] = await build_price_table(
            conn,
            mempool_url=mempool_url,
        )
        logger.info(f"Completed in {time.time() - start:.1f}s")
    else:
        logger.info("Step 1/4: Skipping price table (already populated)")

    # Step 2: Build block heights table
    if not skip_heights:
        logger.info("Step 2/4: Building block_heights table...")
        start = time.time()
        stats["heights_count"] = await build_block_heights_table(
            conn,
            electrs_url=electrs_url,
        )
        logger.info(f"Completed in {time.time() - start:.1f}s")
    else:
        logger.info("Step 2/4: Skipping heights table (already populated)")

    # Step 3: Import chainstate CSV
    logger.info("Step 3/4: Importing chainstate CSV...")
    start = time.time()
    stats["utxos_count"] = import_chainstate_csv(conn, csv_path)
    logger.info(f"Completed in {time.time() - start:.1f}s")

    # Step 4: Compute derived values
    logger.info("Step 4/4: Computing BTC values and creation prices...")
    start = time.time()
    compute_btc_values(conn)
    compute_creation_prices(conn)
    create_indexes(conn)
    logger.info(f"Completed in {time.time() - start:.1f}s")

    # Get final stats
    import_stats = get_import_stats(conn)
    stats["total_btc"] = import_stats.get("total_btc", 0)
    stats["duration_seconds"] = time.time() - stats["start_time"]

    return stats


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Bootstrap UTXO lifecycle database")
    parser.add_argument(
        "--csv-path",
        help="Path to chainstate CSV from bitcoin-utxo-dump",
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
        "--electrs-url",
        default=os.getenv("ELECTRS_HTTP_URL", DEFAULT_ELECTRS_URL),
        help="Electrs HTTP URL",
    )
    parser.add_argument(
        "--bitcoin-datadir",
        default=os.getenv("BITCOIN_DATADIR", DEFAULT_BITCOIN_DATADIR),
        help="Bitcoin data directory (for chainstate)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies, don't bootstrap",
    )
    parser.add_argument(
        "--run-dump",
        action="store_true",
        help="Run bitcoin-utxo-dump to generate CSV (requires --csv-path)",
    )
    parser.add_argument(
        "--skip-prices",
        action="store_true",
        help="Skip building price table",
    )
    parser.add_argument(
        "--skip-heights",
        action="store_true",
        help="Skip building heights table",
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

    # Check dependencies
    print("Checking dependencies...")
    deps = await check_dependencies()

    print("\nDependency Status:")
    for name, available in deps.items():
        status = "OK" if available else "MISSING"
        print(f"  {name}: {status}")

    if args.check_only:
        missing = [k for k, v in deps.items() if not v]
        if missing:
            print(f"\nMissing dependencies: {', '.join(missing)}")
            return 1
        print("\nAll dependencies available!")
        return 0

    # Validate CSV path
    if not args.csv_path:
        if args.run_dump:
            args.csv_path = "/tmp/utxo_chainstate.csv"
        else:
            parser.error("--csv-path required (or use --run-dump)")

    # Run bitcoin-utxo-dump if requested
    if args.run_dump:
        if not deps["bitcoin_utxo_dump"]:
            print("ERROR: bitcoin-utxo-dump not available")
            print(
                "Install with: go install github.com/in3rsha/bitcoin-utxo-dump@latest"
            )
            return 1

        if not run_bitcoin_utxo_dump(args.csv_path, args.bitcoin_datadir):
            print("ERROR: Failed to run bitcoin-utxo-dump")
            return 1

    # Verify CSV exists
    if not os.path.exists(args.csv_path):
        print(f"ERROR: CSV file not found: {args.csv_path}")
        return 1

    # Run bootstrap
    print("\nStarting Tier 1 bootstrap...")
    print(f"  CSV: {args.csv_path}")
    print(f"  Database: {args.db_path}")

    conn = duckdb.connect(args.db_path)

    try:
        stats = await bootstrap_tier1(
            conn,
            csv_path=args.csv_path,
            mempool_url=args.mempool_url,
            electrs_url=args.electrs_url,
            skip_prices=args.skip_prices,
            skip_heights=args.skip_heights,
        )

        print("\n" + "=" * 60)
        print("BOOTSTRAP COMPLETE")
        print("=" * 60)
        print(f"  Duration: {stats['duration_seconds'] / 60:.1f} minutes")
        print(f"  Prices: {stats['prices_count']:,} days")
        print(f"  Heights: {stats['heights_count']:,} blocks")
        print(f"  UTXOs: {stats['utxos_count']:,}")
        print(f"  Total BTC: {stats['total_btc']:,.2f}")
        print("=" * 60)

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
