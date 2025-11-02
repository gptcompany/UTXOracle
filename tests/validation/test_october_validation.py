#!/usr/bin/env python3
"""
Validation Test: Library vs Current UTXOracle.py on 5 October Dates

Tests library against CURRENT reference implementation (not stale HTML files)
to confirm the discovery that both produce identical results.
"""

import subprocess
import sys
from pathlib import Path

# Add project root to path (we're in tests/validation/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from UTXOracle_library import UTXOracleCalculator


def get_blocks_from_html(html_path):
    """Extract block range from HTML file."""
    import re

    with open(html_path, "r") as f:
        content = f.read()

    heights_match = re.search(r"const heights = \[([0-9, ]+)\]", content)
    if not heights_match:
        return None, None

    heights_str = heights_match.group(1)
    heights = [int(h.strip()) for h in heights_str.split(",") if h.strip()]

    return min(heights), max(heights)


def run_utxoracle_reference(date_str):
    """Run UTXOracle.py for given date and extract price."""
    cmd = ["python3", "UTXOracle.py", "-d", date_str.replace("-", "/"), "--no-browser"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        print(f"❌ UTXOracle.py failed for {date_str}: {result.stderr}")
        return None

    # Extract price from output: "Oct 24, 2025 price: $67,890"
    import re

    match = re.search(r"price: \$([0-9,]+)", result.stdout)
    if match:
        price_str = match.group(1).replace(",", "")
        return float(price_str)

    return None


def fetch_transactions(first_block, last_block):
    """Fetch transactions from Bitcoin Core."""
    import json

    all_txs = []
    for height in range(first_block, last_block + 1):
        # Get block hash
        cmd = ["bitcoin-cli", "getblockhash", str(height)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to get block hash for {height}")
        block_hash = result.stdout.strip()

        # Get block with transactions
        cmd = ["bitcoin-cli", "getblock", block_hash, "2"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to get block {height}")

        block = json.loads(result.stdout)
        all_txs.extend(block["tx"])

    return all_txs


def test_date(date_str):
    """Test library vs reference for a specific date."""
    print(f"\n{'=' * 60}")
    print(f"Testing {date_str}")
    print(f"{'=' * 60}")

    # Get block range from HTML
    html_path = Path(f"historical_data/html_files/UTXOracle_{date_str}.html")
    if not html_path.exists():
        print(f"❌ HTML file not found: {html_path}")
        return None

    first_block, last_block = get_blocks_from_html(html_path)
    if not first_block:
        print("❌ Could not extract block range from HTML")
        return None

    print(f"Block range: {first_block}-{last_block}")

    # Run reference UTXOracle.py
    print("Running UTXOracle.py...")
    ref_price = run_utxoracle_reference(date_str)
    if ref_price is None:
        return None

    print(f"✅ Reference price: ${ref_price:,.2f}")

    # Fetch transactions
    print("Fetching transactions...")
    try:
        transactions = fetch_transactions(first_block, last_block)
        print(f"✅ Fetched {len(transactions)} transactions")
    except Exception as e:
        print(f"❌ Failed to fetch transactions: {e}")
        return None

    # Run library
    print("Running library...")
    calc = UTXOracleCalculator()
    result = calc.calculate_price_for_transactions(transactions)
    lib_price = result.get("price_usd")

    if lib_price is None:
        print("❌ Library returned None")
        return None

    print(f"✅ Library price: ${lib_price:,.2f}")

    # Compare
    diff = abs(ref_price - lib_price)
    diff_pct = (diff / ref_price) * 100

    print("\nComparison:")
    print(f"  Reference: ${ref_price:,.2f}")
    print(f"  Library:   ${lib_price:,.2f}")
    print(f"  Diff:      ${diff:,.2f} ({diff_pct:.6f}%)")

    if diff < 1.0:  # Less than $1 difference
        print("✅ PERFECT MATCH!")
        return {"date": date_str, "match": True, "diff_pct": diff_pct}
    else:
        print(f"⚠️  Difference: {diff_pct:.2f}%")
        return {"date": date_str, "match": False, "diff_pct": diff_pct}


def main():
    test_dates = [
        "2025-10-24",
        "2025-10-23",
        "2025-10-01",
        "2025-10-25",
        "2025-10-09",
    ]

    results = []
    for date in test_dates:
        result = test_date(date)
        if result:
            results.append(result)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    matches = sum(1 for r in results if r["match"])
    print(f"Perfect matches: {matches}/{len(results)}")

    if matches == len(results):
        print("\n✅ VALIDATION SUCCESSFUL!")
        print("   Library produces identical results to current UTXOracle.py")
        print("   across all tested dates.")
    else:
        print("\n⚠️  Some differences found - review results above")


if __name__ == "__main__":
    main()
