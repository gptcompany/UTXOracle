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

from scripts.config import UTXORACLE_DB_PATH
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
    create_indexes,
    get_import_stats,
    import_chainstate_csv,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MEMPOOL_URL = "http://localhost:8999"
DEFAULT_ELECTRS_URL = "http://localhost:3001"
DEFAULT_BITCOIN_DATADIR = os.path.expanduser("~/.bitcoin")
DEFAULT_BITCOIND_STOP_TIMEOUT = 60  # seconds to wait for bitcoind to stop
DEFAULT_BITCOIND_START_TIMEOUT = 120  # seconds to wait for bitcoind to start
DEFAULT_LEVELDB_FLUSH_DELAY = 5  # seconds to wait after RPC stops for LevelDB flush


def bootstrap_tier2_available() -> bool:
    """Check if Tier 2 bootstrap (rpc-v3) is available.

    Tier 2 requires Bitcoin Core 25.0+ which supports getblock verbosity=3.

    Returns:
        True if rpc-v3 is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["bitcoin-cli", "getnetworkinfo"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False

        # Parse version from output
        import json

        info = json.loads(result.stdout)
        version = info.get("version", 0)
        # Version 250000 = 25.0.0
        return version >= 250000
    except Exception:
        return False


def is_bitcoind_running() -> bool:
    """Check if bitcoind is currently running.

    Returns:
        True if bitcoind is running and accepting RPC commands
    """
    try:
        result = subprocess.run(
            ["bitcoin-cli", "getblockchaininfo"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_chainstate_locked(bitcoin_datadir: str = DEFAULT_BITCOIN_DATADIR) -> bool:
    """Check if LevelDB LOCK file exists in chainstate directory.

    The LOCK file indicates bitcoind still has the database open.
    Running bitcoin-utxo-dump while LOCK exists causes data corruption.

    Args:
        bitcoin_datadir: Bitcoin data directory

    Returns:
        True if LOCK file exists (database is locked), False otherwise
    """
    lock_path = os.path.join(bitcoin_datadir, "chainstate", "LOCK")
    return os.path.exists(lock_path)


def stop_bitcoind(
    timeout: int = DEFAULT_BITCOIND_STOP_TIMEOUT,
    bitcoin_datadir: str = DEFAULT_BITCOIN_DATADIR,
) -> bool:
    """Stop bitcoind gracefully and wait for it to fully stop.

    This function ensures:
    1. RPC is no longer responding
    2. LevelDB LOCK file is released
    3. Additional flush delay for disk writes

    Args:
        timeout: Maximum seconds to wait for bitcoind to stop
        bitcoin_datadir: Bitcoin data directory (for LOCK file check)

    Returns:
        True if bitcoind stopped successfully and chainstate is unlocked
    """
    if not is_bitcoind_running():
        # Verify chainstate is not locked even if bitcoind appears stopped
        if is_chainstate_locked(bitcoin_datadir):
            logger.warning("Bitcoin Core not running but chainstate LOCK file exists")
            logger.warning("This may indicate unclean shutdown - waiting for release")
            # Wait for LOCK file to be released
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not is_chainstate_locked(bitcoin_datadir):
                    logger.info("Chainstate LOCK released")
                    return True
                time.sleep(2)
            logger.error("Chainstate LOCK file still present - possible corruption")
            return False
        logger.info("Bitcoin Core is not running")
        return True

    logger.info("Stopping Bitcoin Core...")
    try:
        result = subprocess.run(
            ["bitcoin-cli", "stop"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.error(f"Failed to send stop command: {result.stderr.decode()}")
            return False

        # Wait for bitcoind to fully stop (RPC becomes unavailable)
        start_time = time.time()
        rpc_stopped = False
        while time.time() - start_time < timeout:
            if not is_bitcoind_running():
                rpc_stopped = True
                logger.info("Bitcoin Core RPC stopped")
                break
            time.sleep(2)

        if not rpc_stopped:
            logger.error(f"Bitcoin Core RPC did not stop within {timeout}s")
            return False

        # CRITICAL: Wait for LevelDB LOCK file to be released
        # RPC stops responding BEFORE LevelDB is fully flushed
        logger.info("Waiting for chainstate LOCK file to be released...")
        lock_wait_start = time.time()
        while time.time() - lock_wait_start < timeout:
            if not is_chainstate_locked(bitcoin_datadir):
                # Additional safety delay for disk flush completion
                logger.info(
                    f"LOCK released, waiting {DEFAULT_LEVELDB_FLUSH_DELAY}s for disk flush..."
                )
                time.sleep(DEFAULT_LEVELDB_FLUSH_DELAY)
                logger.info(
                    "Bitcoin Core stopped successfully - chainstate safe to read"
                )
                return True
            time.sleep(1)

        logger.error(
            f"Chainstate LOCK file not released within {timeout}s after RPC stop"
        )
        logger.error("Possible causes: unclean shutdown, disk I/O issues")
        return False

    except Exception as e:
        logger.error(f"Error stopping Bitcoin Core: {e}")
        return False


def start_bitcoind(
    bitcoin_datadir: str = DEFAULT_BITCOIN_DATADIR,
    timeout: int = DEFAULT_BITCOIND_START_TIMEOUT,
) -> bool:
    """Start bitcoind and wait for it to be ready for RPC commands.

    Args:
        bitcoin_datadir: Bitcoin data directory
        timeout: Maximum seconds to wait for bitcoind to start

    Returns:
        True if bitcoind started and is accepting RPC commands
    """
    if is_bitcoind_running():
        logger.info("Bitcoin Core is already running")
        return True

    logger.info(f"Starting Bitcoin Core with datadir={bitcoin_datadir}...")
    proc = None
    try:
        # Start bitcoind in background (daemon mode)
        cmd = ["bitcoind", f"-datadir={bitcoin_datadir}", "-daemon"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
        )

        if result.returncode != 0:
            # bitcoind might not support -daemon, try without
            logger.warning("Trying without -daemon flag...")
            cmd = ["bitcoind", f"-datadir={bitcoin_datadir}"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Wait for bitcoind to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if is_bitcoind_running():
                logger.info("Bitcoin Core started and ready for RPC")
                return True
            time.sleep(5)

        # Timeout reached - clean up orphan process if we started one
        if proc is not None:
            logger.warning("Terminating orphan bitcoind process after timeout")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        logger.error(f"Bitcoin Core did not start within {timeout}s")
        return False

    except Exception as e:
        # Clean up orphan process on exception
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        logger.error(f"Error starting Bitcoin Core: {e}")
        return False


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

    IMPORTANT: This function verifies the chainstate is NOT locked before
    attempting to read. Reading LevelDB while bitcoind has it open causes
    data corruption.

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

    # CRITICAL: Verify chainstate is NOT locked before reading
    # This prevents corruption from reading inconsistent LevelDB state
    if is_chainstate_locked(bitcoin_datadir):
        logger.error("ABORT: Chainstate LOCK file exists!")
        logger.error(f"LOCK file found at: {os.path.join(chainstate_dir, 'LOCK')}")
        logger.error(
            "Bitcoin Core may be running or did not shut down cleanly. "
            "Reading chainstate now would cause data corruption."
        )
        logger.error(
            "Solutions: 1) Stop bitcoind with 'bitcoin-cli stop' and wait "
            "2) Use --auto-manage-bitcoind flag"
        )
        return False

    logger.info("Chainstate LOCK check passed - safe to read")

    try:
        # Run bitcoin-utxo-dump
        # Output format: txid,vout,height,coinbase,amount,type,address
        # Note: bitcoin-utxo-dump uses 'type' field for script type (p2pkh, p2wpkh, etc.)
        # The -o flag specifies output file path, not format
        cmd = [
            "bitcoin-utxo-dump",
            "-db",
            chainstate_dir,
            "-o",
            output_path,
            "-f",
            "txid,vout,height,coinbase,amount,type,address",
            "-nowarnings",
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        # bitcoin-utxo-dump writes directly to the output file via -o flag
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=7200,  # 2 hour timeout
        )

        if result.returncode != 0:
            logger.error(f"bitcoin-utxo-dump failed: {result.stderr.decode()}")
            return False

        # Verify output exists and has reasonable size
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            size_mb = size / 1024 / 1024

            # Mainnet chainstate should be at least several GB
            # A very small file indicates corruption or incomplete dump
            MIN_EXPECTED_SIZE_MB = 100  # Minimum expected size for mainnet
            if size_mb < MIN_EXPECTED_SIZE_MB:
                logger.warning(
                    f"CSV file is suspiciously small: {size_mb:.1f} MB "
                    f"(expected > {MIN_EXPECTED_SIZE_MB} MB for mainnet)"
                )
                logger.warning(
                    "This may indicate chainstate corruption or incomplete dump. "
                    "Verify chainstate was not locked during dump."
                )

            logger.info(f"Generated CSV: {output_path} ({size_mb:.1f} MB)")
            return True

        logger.error(f"Output file not created: {output_path}")
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

    # Step 4: Create indexes and VIEW
    logger.info("Step 4/4: Creating indexes and computed VIEW...")
    start = time.time()
    create_indexes(conn)

    # Create VIEW with computed columns (btc_value, creation_price, etc.)
    # VIEW joins with block_heights and daily_prices tables
    from scripts.bootstrap.import_chainstate import (
        create_utxo_lifecycle_view,
        verify_supporting_tables,
    )

    table_status = verify_supporting_tables(conn)
    if table_status["view_functional"]:
        create_utxo_lifecycle_view(conn)
        logger.info("Created utxo_lifecycle_full VIEW for metrics queries")
    else:
        logger.warning(
            "VIEW not created - metrics will use base table with inline calculations"
        )
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
        default=str(UTXORACLE_DB_PATH),
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
        "--auto-manage-bitcoind",
        action="store_true",
        help="Automatically stop bitcoind before dump and restart after (requires --run-dump)",
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
    bitcoind_was_running = False
    if args.run_dump:
        if not deps["bitcoin_utxo_dump"]:
            print("ERROR: bitcoin-utxo-dump not available")
            print(
                "Install with: go install github.com/in3rsha/bitcoin-utxo-dump@latest"
            )
            return 1

        # Auto-manage bitcoind if requested
        if args.auto_manage_bitcoind:
            bitcoind_was_running = is_bitcoind_running()
            if bitcoind_was_running:
                print("\n[Auto-manage] Stopping Bitcoin Core for chainstate dump...")
                if not stop_bitcoind(
                    timeout=DEFAULT_BITCOIND_STOP_TIMEOUT,
                    bitcoin_datadir=args.bitcoin_datadir,
                ):
                    print("ERROR: Failed to stop Bitcoin Core")
                    print("       Chainstate may be locked - cannot proceed safely")
                    return 1
                print("[Auto-manage] Bitcoin Core stopped successfully")
                print("[Auto-manage] Chainstate LOCK released - safe to read")

        if not run_bitcoin_utxo_dump(args.csv_path, args.bitcoin_datadir):
            print("ERROR: Failed to run bitcoin-utxo-dump")
            # Restart bitcoind even on failure if we stopped it
            if args.auto_manage_bitcoind and bitcoind_was_running:
                print("\n[Auto-manage] Restarting Bitcoin Core after failure...")
                start_bitcoind(args.bitcoin_datadir)
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
    bootstrap_success = False

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
        bootstrap_success = True

    finally:
        conn.close()
        # Always restart bitcoind if we stopped it, even on exception
        if args.auto_manage_bitcoind and bitcoind_was_running:
            print("\n[Auto-manage] Restarting Bitcoin Core...")
            if start_bitcoind(args.bitcoin_datadir):
                print("[Auto-manage] Bitcoin Core restarted successfully")
            else:
                print("WARNING: Failed to restart Bitcoin Core - please start manually")
                if bootstrap_success:
                    return 1

    return 0 if bootstrap_success else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
