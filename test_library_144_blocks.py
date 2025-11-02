#!/usr/bin/env python3
"""
Library Test: 144 Blocks (Matches Reference Processing)

Tests library with SAME 144-block range that UTXOracle.py processes.
This should give 0% difference since we're processing identical data.

Usage:
    python3 test_library_144_blocks.py --date 2025-10-15
"""

import argparse
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List
from dotenv import load_dotenv

from UTXOracle_library import UTXOracleCalculator

load_dotenv()

# Bitcoin Core RPC configuration
RPC_USER = os.getenv("RPC_USER", "")
RPC_PASSWORD = os.getenv("RPC_PASSWORD", "")
RPC_HOST = os.getenv("RPC_HOST", "127.0.0.1")
RPC_PORT = int(os.getenv("RPC_PORT", 8332))
DUCKDB_PATH = os.getenv(
    "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)
HISTORICAL_DIR = Path(__file__).parent / "historical_data" / "html_files"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def bitcoin_rpc_call(method: str, params: List = []) -> dict:
    """Call Bitcoin Core RPC"""
    cmd = [
        "curl",
        "--silent",
        "--user",
        f"{RPC_USER}:{RPC_PASSWORD}",
        "--data-binary",
        json.dumps({"jsonrpc": "1.0", "method": method, "params": params}),
        f"http://{RPC_HOST}:{RPC_PORT}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"RPC call failed: {result.stderr}")

    response = json.loads(result.stdout)

    if "error" in response and response["error"]:
        raise Exception(f"RPC error: {response['error']}")

    return response["result"]


def extract_block_range_from_html(date_str: str) -> tuple:
    """
    Extract the block range (first, last) from HTML file.

    Args:
        date_str: Date in format "YYYY-MM-DD"

    Returns:
        tuple: (first_block, last_block)
    """
    html_file = HISTORICAL_DIR / f"UTXOracle_{date_str}.html"

    if not html_file.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file}")

    with open(html_file, "r") as f:
        content = f.read()

    # Extract heights_smooth array
    match = re.search(r"const heights_smooth = \[([0-9., ]+)\]", content)
    if not match:
        raise ValueError(f"Could not find heights_smooth in {html_file}")

    heights = [float(h.strip()) for h in match.group(1).split(",") if h.strip()]

    first_block = int(heights[0])
    last_block = int(heights[-1])

    return first_block, last_block


def fetch_144_blocks(first_block: int, last_block: int) -> List[dict]:
    """
    Fetch all transactions from 144-block range.

    Args:
        first_block: Starting block height
        last_block: Ending block height

    Returns:
        List of all transactions from all blocks
    """
    logging.info(
        f"Fetching {last_block - first_block + 1} blocks ({first_block}-{last_block})..."
    )

    all_transactions = []
    block_count = last_block - first_block + 1

    for i, block_height in enumerate(range(first_block, last_block + 1)):
        if (i + 1) % 20 == 0 or i == 0:
            logging.info(f"  Fetching block {i + 1}/{block_count}...")

        # Get block hash
        block_hash = bitcoin_rpc_call("getblockhash", [block_height])

        # Get block with transactions (verbosity=2)
        block = bitcoin_rpc_call("getblock", [block_hash, 2])

        # Add all transactions
        all_transactions.extend(block["tx"])

    logging.info(
        f"✅ Fetched {len(all_transactions)} total transactions from {block_count} blocks"
    )

    return all_transactions


def extract_reference_price_from_html(date_str: str) -> float:
    """
    Extract the FINAL consensus price from HTML (last value in prices array).

    This is the price after processing all 144 blocks.
    """
    html_file = HISTORICAL_DIR / f"UTXOracle_{date_str}.html"

    with open(html_file, "r") as f:
        content = f.read()

    # Extract prices array
    match = re.search(r"const prices = \[([0-9., ]+)\]", content)
    if not match:
        raise ValueError(f"Could not find prices in {html_file}")

    prices = [float(p.strip()) for p in match.group(1).split(",") if p.strip()]

    # Return LAST price (after all 144 blocks processed)
    final_price = prices[-1]

    logging.info(f"✅ Reference FINAL price: ${final_price:,.2f}")

    return final_price


def test_144_blocks(date_str: str):
    """
    Test library with 144 blocks (matching reference processing).

    Args:
        date_str: Date in format "YYYY-MM-DD"
    """
    print("=" * 80)
    print(f"LIBRARY TEST: 144-Block Processing (Date: {date_str})")
    print("=" * 80)
    print()

    # Step 1: Extract block range from HTML
    first_block, last_block = extract_block_range_from_html(date_str)
    block_count = last_block - first_block + 1

    logging.info(
        f"Block range from HTML: {first_block}-{last_block} ({block_count} blocks)"
    )
    print()

    # Step 2: Extract reference price (FINAL price after 144 blocks)
    ref_price = extract_reference_price_from_html(date_str)
    print()

    # Step 3: Fetch all 144 blocks via RPC
    all_transactions = fetch_144_blocks(first_block, last_block)
    print()

    # Step 4: Calculate price using library
    logging.info("Calculating price using UTXOracle_library...")
    calc = UTXOracleCalculator()
    result = calc.calculate_price_for_transactions(all_transactions)

    lib_price = result["price_usd"]
    lib_confidence = result["confidence"]

    logging.info(f"Library price (144 blocks): ${lib_price:,.2f}")
    logging.info(f"Library confidence: {lib_confidence:.3f}")

    # Print diagnostics
    if "diagnostics" in result:
        diag = result["diagnostics"]
        logging.info("\n📊 FILTER DIAGNOSTICS (ALL 6 FILTERS):")
        logging.info(f"   Total transactions:    {diag['total_txs']:,}")
        logging.info(f"   Filtered (inputs >5):  {diag['filtered_inputs']:,}")
        logging.info(f"   Filtered (outputs≠2):  {diag['filtered_outputs']:,}")
        logging.info(f"   Filtered (coinbase):   {diag['filtered_coinbase']:,}")
        logging.info(f"   Filtered (OP_RETURN):  {diag['filtered_op_return']:,}")
        logging.info(f"   Filtered (witness>500): {diag['filtered_witness']:,}")
        logging.info(f"   Filtered (same_day_tx): {diag['filtered_same_day']:,}")
        logging.info(f"   Total filtered:        {diag['total_filtered']:,}")
        logging.info(f"   ✓ Passed filter:       {diag['passed_filter']:,}")

    print()
    print("=" * 80)
    print("COMPARISON")
    print("=" * 80)

    # Step 5: Compare
    diff = abs(lib_price - ref_price)
    diff_pct = (diff / ref_price) * 100 if ref_price > 0 else 0

    print(f"Reference (144 blocks): ${ref_price:,.2f}")
    print(f"Library (144 blocks):   ${lib_price:,.2f}")
    print(f"Difference:             ${diff:,.2f} ({diff_pct:.6f}%)")
    print()

    if diff_pct < 0.01:
        print("✅ EXCELLENT! <0.01% difference (near-perfect match)")
    elif diff_pct < 0.1:
        print("✅ VERY GOOD! <0.1% difference")
    elif diff_pct < 1.0:
        print("⚠️  ACCEPTABLE: <1% difference")
    else:
        print("❌ FAIL: >1% difference")

    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Test library with 144 blocks")
    parser.add_argument("--date", required=True, help="Date in format YYYY-MM-DD")
    args = parser.parse_args()

    test_144_blocks(args.date)


if __name__ == "__main__":
    main()
