#!/usr/bin/env python3
"""
Debug convergence algorithm - compare library vs reference step-by-step
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from UTXOracle_library import UTXOracleCalculator


def bitcoin_rpc_call(method: str, params: list = []):
    """Call Bitcoin Core RPC using bitcoin-cli"""
    cmd = ["bitcoin-cli", method] + [str(p) for p in params]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"RPC call failed: {result.stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def main():
    # Test Oct 15, 2025 (blocks 919111-919254)
    # Reference: $109,890.11
    # Library (broken): $111,706.88

    print("Fetching blocks 919111-919254...")
    all_transactions = []

    for block_height in range(919111, 919255):
        if (block_height - 919111) % 50 == 0:
            print(f"  Block {block_height}...")

        block_hash = bitcoin_rpc_call("getblockhash", [block_height])
        block = bitcoin_rpc_call("getblock", [block_hash, 2])
        all_transactions.extend(block["tx"])

    print(f"\n✅ Fetched {len(all_transactions)} transactions\n")

    # Run library calculation
    calc = UTXOracleCalculator()
    result = calc.calculate_price_for_transactions(all_transactions)

    print("Library result:")
    print(f"  Price: ${result['price_usd']:,.2f}")
    print(f"  Confidence: {result['confidence']:.4f}")
    print(f"  TX count: {result['tx_count']}")
    print(f"  Output count: {result['output_count']}")

    # Add detailed diagnostics
    if "diagnostics" in result:
        diag = result["diagnostics"]
        print("\nFiltering diagnostics:")
        print(f"  Total transactions: {diag['total_txs']}")
        print(f"  Filtered inputs: {diag['filtered_inputs']}")
        print(f"  Filtered outputs: {diag['filtered_outputs']}")
        print(f"  Filtered coinbase: {diag['filtered_coinbase']}")
        print(f"  Filtered op_return: {diag['filtered_op_return']}")
        print(f"  Filtered witness: {diag['filtered_witness']}")
        print(f"  Filtered same_day: {diag['filtered_same_day']}")

    print("\n📊 Reference price: $109,890.11")
    print(f"📊 Library price: ${result['price_usd']:,.2f}")
    diff = abs(result["price_usd"] - 109890.11)
    diff_pct = (diff / 109890.11) * 100
    print(f"📊 Difference: ${diff:,.2f} ({diff_pct:.2f}%)")


if __name__ == "__main__":
    main()
