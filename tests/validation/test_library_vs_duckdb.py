#!/usr/bin/env python3
"""
Test UTXOracle_library.py against DuckDB reference data

Validates:
1. Daily prices (from price_analysis table)
2. Intraday prices (from intraday_prices table)

Expected result: 0% difference (library should match reference exactly)

Usage:
    python3 test_library_vs_duckdb.py --daily --samples 10
    python3 test_library_vs_duckdb.py --intraday --samples 5
    python3 test_library_vs_duckdb.py --all  # Test everything
"""

import argparse
import json
import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import List
# Use SOPS-encrypted secrets
sys.path.insert(0, "/media/sam/1TB/claude-hooks-shared/scripts")
from secrets_loader import load_secrets

import duckdb

from UTXOracle_library import UTXOracleCalculator

load_secrets()

# Configuration
RPC_USER = os.getenv("RPC_USER", "")
RPC_PASSWORD = os.getenv("RPC_PASSWORD", "")
RPC_HOST = os.getenv("RPC_HOST", "127.0.0.1")
RPC_PORT = int(os.getenv("RPC_PORT", 8332))
DUCKDB_PATH = os.getenv(
    "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def bitcoin_rpc_call(method: str, params: List = []) -> dict:
    """Call Bitcoin Core RPC using bitcoin-cli"""
    # Build bitcoin-cli command
    cmd = ["bitcoin-cli", method] + [str(p) for p in params]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"RPC call failed: {result.stderr}")

    # Parse JSON response
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # If not JSON, return as string (for simple responses)
        return result.stdout.strip()


def fetch_transactions_for_block_range(first_block: int, last_block: int) -> List[dict]:
    """
    Fetch all transactions from a block range.

    Args:
        first_block: Starting block height
        last_block: Ending block height

    Returns:
        List of all transactions from all blocks
    """
    all_transactions = []
    block_count = last_block - first_block + 1

    logging.info(f"Fetching {block_count} blocks ({first_block}-{last_block})...")

    for i, block_height in enumerate(range(first_block, last_block + 1)):
        if (i + 1) % 50 == 0 or i == 0:
            logging.info(f"  Progress: {i + 1}/{block_count} blocks...")

        # Get block hash
        block_hash = bitcoin_rpc_call("getblockhash", [block_height])

        # Get block with transactions (verbosity=2)
        block = bitcoin_rpc_call("getblock", [block_hash, 2])

        # Add all transactions
        all_transactions.extend(block["tx"])

    logging.info(
        f"✅ Fetched {len(all_transactions)} transactions from {block_count} blocks"
    )

    return all_transactions


def test_daily_prices(samples: int = 10):
    """
    Test library against daily prices from DuckDB.

    For each date:
    1. Get reference price from price_analysis table
    2. Get block range from HTML file
    3. Fetch same blocks from Bitcoin Core
    4. Calculate price using library
    5. Compare: should be 0% difference

    Args:
        samples: Number of random dates to test
    """
    print("=" * 80)
    print("TEST 1: Daily Prices (price_analysis table)")
    print("=" * 80)
    print()

    conn = duckdb.connect(DUCKDB_PATH)

    # Get random sample of dates
    query = f"""
        SELECT date, utxoracle_price
        FROM price_analysis
        WHERE utxoracle_price IS NOT NULL
        ORDER BY RANDOM()
        LIMIT {samples}
    """

    results = conn.execute(query).fetchall()
    conn.close()

    if not results:
        logging.error("No data found in price_analysis table")
        return

    logging.info(f"Testing {len(results)} random dates...\n")

    calc = UTXOracleCalculator()
    differences = []

    for date_obj, ref_price in results:
        date_str = str(date_obj)
        # Convert Decimal to float (DuckDB returns Decimal)
        ref_price = float(ref_price)
        logging.info(f"📅 Testing {date_str}...")
        logging.info(f"   Reference price: ${ref_price:,.2f}")

        try:
            # Find corresponding HTML file
            html_file = (
                Path(__file__).parent
                / "historical_data"
                / "html_files"
                / f"UTXOracle_{date_str}.html"
            )

            if not html_file.exists():
                logging.warning(f"   ⚠️  HTML file not found: {html_file}")
                continue

            # Extract block range from HTML
            with open(html_file, "r") as f:
                content = f.read()

            import re

            match = re.search(r"const heights_smooth = \[([0-9., ]+)\]", content)
            if not match:
                logging.warning("   ⚠️  Could not find heights_smooth in HTML")
                continue

            heights = [float(h.strip()) for h in match.group(1).split(",") if h.strip()]
            first_block = int(heights[0])
            last_block = int(heights[-1])

            logging.info(
                f"   Block range: {first_block}-{last_block} ({last_block - first_block + 1} blocks)"
            )

            # Fetch transactions
            all_txs = fetch_transactions_for_block_range(first_block, last_block)

            # Calculate using library
            result = calc.calculate_price_for_transactions(all_txs)
            lib_price = result["price_usd"]

            logging.info(f"   Library price: ${lib_price:,.2f}")

            # Compare
            diff = abs(lib_price - ref_price)
            diff_pct = (diff / ref_price) * 100 if ref_price > 0 else 0

            logging.info(f"   Difference: ${diff:,.2f} ({diff_pct:.6f}%)")

            differences.append(
                {
                    "date": date_str,
                    "ref_price": ref_price,
                    "lib_price": lib_price,
                    "diff": diff,
                    "diff_pct": diff_pct,
                }
            )

            if diff_pct < 0.01:
                logging.info("   ✅ EXCELLENT! <0.01% difference\n")
            elif diff_pct < 0.1:
                logging.info("   ✅ VERY GOOD! <0.1% difference\n")
            elif diff_pct < 1.0:
                logging.info("   ⚠️  ACCEPTABLE: <1% difference\n")
            else:
                logging.info("   ❌ FAIL: >1% difference\n")

        except Exception as e:
            logging.error(f"   ❌ Error testing {date_str}: {e}\n")
            continue

    # Summary statistics
    print("\n" + "=" * 80)
    print("DAILY PRICES SUMMARY")
    print("=" * 80)

    if differences:
        avg_diff_pct = sum(d["diff_pct"] for d in differences) / len(differences)
        max_diff_pct = max(d["diff_pct"] for d in differences)
        min_diff_pct = min(d["diff_pct"] for d in differences)

        print(f"Samples tested: {len(differences)}")
        print(f"Average difference: {avg_diff_pct:.6f}%")
        print(f"Max difference: {max_diff_pct:.6f}%")
        print(f"Min difference: {min_diff_pct:.6f}%")

        perfect_matches = len([d for d in differences if d["diff_pct"] < 0.01])
        print(f"Perfect matches (<0.01%): {perfect_matches}/{len(differences)}")

        if avg_diff_pct < 0.01:
            print("\n✅ RESULT: Library matches reference (0% difference)")
        elif avg_diff_pct < 0.1:
            print("\n✅ RESULT: Library very close to reference (<0.1% avg)")
        else:
            print(
                f"\n❌ RESULT: Library differs from reference ({avg_diff_pct:.3f}% avg)"
            )


def test_intraday_prices(samples: int = 5):
    """
    Test library against intraday prices from DuckDB.

    For each intraday point:
    1. Get reference price from intraday_prices table
    2. Get block height from table
    3. Fetch 144 blocks ending at that height
    4. Calculate price using library
    5. Compare: should be 0% difference

    Args:
        samples: Number of random intraday points to test
    """
    print("\n" + "=" * 80)
    print("TEST 2: Intraday Prices (intraday_prices table)")
    print("=" * 80)
    print()

    conn = duckdb.connect(DUCKDB_PATH)

    # Get random sample of intraday points
    query = f"""
        SELECT date, block_height, price_usd
        FROM intraday_prices
        WHERE price_usd IS NOT NULL
        ORDER BY RANDOM()
        LIMIT {samples}
    """

    results = conn.execute(query).fetchall()
    conn.close()

    if not results:
        logging.error("No data found in intraday_prices table")
        return

    logging.info(f"Testing {len(results)} random intraday points...\n")

    calc = UTXOracleCalculator()
    differences = []

    for date_obj, block_height, ref_price in results:
        date_str = str(date_obj)
        # Convert Decimal to float (DuckDB returns Decimal)
        ref_price = float(ref_price)
        logging.info(f"📅 Testing {date_str} @ block {block_height}...")
        logging.info(f"   Reference price: ${ref_price:,.2f}")

        try:
            # Calculate block range (144 blocks ending at this height)
            first_block = block_height - 143
            last_block = block_height

            logging.info(f"   Block range: {first_block}-{last_block} (144 blocks)")

            # Fetch transactions
            all_txs = fetch_transactions_for_block_range(first_block, last_block)

            # Calculate using library
            result = calc.calculate_price_for_transactions(all_txs)
            lib_price = result["price_usd"]

            logging.info(f"   Library price: ${lib_price:,.2f}")

            # Compare
            diff = abs(lib_price - ref_price)
            diff_pct = (diff / ref_price) * 100 if ref_price > 0 else 0

            logging.info(f"   Difference: ${diff:,.2f} ({diff_pct:.6f}%)")

            differences.append(
                {
                    "date": date_str,
                    "block": block_height,
                    "ref_price": ref_price,
                    "lib_price": lib_price,
                    "diff": diff,
                    "diff_pct": diff_pct,
                }
            )

            if diff_pct < 0.01:
                logging.info("   ✅ EXCELLENT! <0.01% difference\n")
            elif diff_pct < 0.1:
                logging.info("   ✅ VERY GOOD! <0.1% difference\n")
            elif diff_pct < 1.0:
                logging.info("   ⚠️  ACCEPTABLE: <1% difference\n")
            else:
                logging.info("   ❌ FAIL: >1% difference\n")

        except Exception as e:
            logging.error(f"   ❌ Error testing {date_str}: {e}\n")
            continue

    # Summary statistics
    print("\n" + "=" * 80)
    print("INTRADAY PRICES SUMMARY")
    print("=" * 80)

    if differences:
        avg_diff_pct = sum(d["diff_pct"] for d in differences) / len(differences)
        max_diff_pct = max(d["diff_pct"] for d in differences)
        min_diff_pct = min(d["diff_pct"] for d in differences)

        print(f"Samples tested: {len(differences)}")
        print(f"Average difference: {avg_diff_pct:.6f}%")
        print(f"Max difference: {max_diff_pct:.6f}%")
        print(f"Min difference: {min_diff_pct:.6f}%")

        perfect_matches = len([d for d in differences if d["diff_pct"] < 0.01])
        print(f"Perfect matches (<0.01%): {perfect_matches}/{len(differences)}")

        if avg_diff_pct < 0.01:
            print("\n✅ RESULT: Library matches reference (0% difference)")
        elif avg_diff_pct < 0.1:
            print("\n✅ RESULT: Library very close to reference (<0.1% avg)")
        else:
            print(
                f"\n❌ RESULT: Library differs from reference ({avg_diff_pct:.3f}% avg)"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Test UTXOracle library vs DuckDB reference"
    )
    parser.add_argument("--daily", action="store_true", help="Test daily prices")
    parser.add_argument("--intraday", action="store_true", help="Test intraday prices")
    parser.add_argument(
        "--all", action="store_true", help="Test both daily and intraday"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of samples per test (default: 10)",
    )
    args = parser.parse_args()

    if args.all:
        test_daily_prices(args.samples)
        test_intraday_prices(args.samples)
    elif args.daily:
        test_daily_prices(args.samples)
    elif args.intraday:
        test_intraday_prices(args.samples)
    else:
        # Default: test daily only
        test_daily_prices(args.samples)


if __name__ == "__main__":
    main()
