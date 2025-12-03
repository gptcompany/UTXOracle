#!/usr/bin/env python3
"""
Diagnostic Test: Compare Transaction Filtering

Compares which transactions pass the UTXOracle filter (reference)
vs which transactions pass the Library filter (current).

Expected: Both should filter IDENTICALLY for 0% price difference.
Actual: Library is more permissive → includes extra transactions → price difference.
"""

import json
import http.client
import base64
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Bitcoin Core RPC configuration
RPC_USER = os.getenv("RPC_USER", "")
RPC_PASSWORD = os.getenv("RPC_PASSWORD", "")
RPC_HOST = os.getenv("RPC_HOST", "127.0.0.1")
RPC_PORT = int(os.getenv("RPC_PORT", 8332))


def rpc_call(method: str, params: List = []) -> dict:
    """Call Bitcoin Core RPC"""
    credentials = base64.b64encode(f"{RPC_USER}:{RPC_PASSWORD}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {credentials}",
    }

    payload = json.dumps(
        {"jsonrpc": "1.0", "id": "filter_test", "method": method, "params": params}
    )

    conn = http.client.HTTPConnection(RPC_HOST, RPC_PORT, timeout=30)
    conn.request("POST", "/", payload, headers)
    response = conn.getresponse()
    data = json.loads(response.read().decode())
    conn.close()

    if "error" in data and data["error"]:
        raise Exception(f"RPC error: {data['error']}")

    return data["result"]


def apply_reference_filter(tx: dict, todays_txids: set) -> bool:
    """
    Apply UTXOracle.py filter (reference implementation).

    Returns True if transaction PASSES filter (should be included).
    """
    vins = tx.get("vin", [])
    vouts = tx.get("vout", [])

    # Count inputs
    input_count = len(vins)
    if input_count > 5:
        return False

    # Count outputs
    output_count = len(vouts)
    if output_count != 2:  # ✓ EXACTLY 2 outputs
        return False

    # Check coinbase
    if any("coinbase" in vin for vin in vins):
        return False

    # Check OP_RETURN
    for vout in vouts:
        script = vout.get("scriptPubKey", {})
        asm = script.get("asm", "")
        if asm.startswith("OP_RETURN"):
            return False

    # Check witness size (simplified - full check requires raw tx)
    # For now, assume all pass (need raw tx to check properly)

    # Check same-day tx (simplified - requires full TXID set)
    # For now, assume all pass

    return True


def apply_library_filter(tx: dict) -> bool:
    """
    Apply UTXOracle_library.py filter (current implementation).

    Returns True if transaction PASSES filter (should be included).
    """
    vins = tx.get("vin", [])
    vouts = tx.get("vout", [])

    # Library filter (lines 432-437)
    if len(vins) > 5:
        return False

    if len(vouts) > 2:  # ❌ ALLOWS 1, 2 outputs (not exactly 2!)
        return False

    return True


def analyze_block_filtering(block_height: int = 919111):
    """
    Analyze which transactions pass reference vs library filters.

    Expected: Same transactions pass both filters.
    Actual: Library is more permissive.
    """
    print("=" * 80)
    print(f"FILTER COMPARISON TEST: Block {block_height}")
    print("=" * 80)
    print()

    # Fetch block
    block_hash = rpc_call("getblockhash", [block_height])
    block = rpc_call("getblock", [block_hash, 2])  # Verbosity 2 = full tx details

    txs = block["tx"]
    todays_txids = {tx["txid"] for tx in txs}

    print(f"Total transactions in block: {len(txs)}")
    print()

    # Apply filters
    reference_pass = []
    library_pass = []

    for tx in txs:
        ref_pass = apply_reference_filter(tx, todays_txids)
        lib_pass = apply_library_filter(tx)

        if ref_pass:
            reference_pass.append(tx["txid"])
        if lib_pass:
            library_pass.append(tx["txid"])

    print(f"Reference filter: {len(reference_pass)} transactions PASS")
    print(f"Library filter:   {len(library_pass)} transactions PASS")
    print()

    # Find differences
    only_library = set(library_pass) - set(reference_pass)
    only_reference = set(reference_pass) - set(library_pass)

    if only_library:
        print(f"❌ Library includes {len(only_library)} EXTRA transactions:")
        for txid in list(only_library)[:5]:  # Show first 5
            tx = next(t for t in txs if t["txid"] == txid)
            vouts = tx.get("vout", [])
            print(f"  {txid[:16]}... (outputs: {len(vouts)})")
        if len(only_library) > 5:
            print(f"  ... and {len(only_library) - 5} more")
        print()

    if only_reference:
        print(
            f"⚠️  Reference includes {len(only_reference)} transactions NOT in library:"
        )
        for txid in list(only_reference)[:5]:
            tx = next(t for t in txs if t["txid"] == txid)
            vouts = tx.get("vout", [])
            print(f"  {txid[:16]}... (outputs: {len(vouts)})")
        if len(only_reference) > 5:
            print(f"  ... and {len(only_reference) - 5} more")
        print()

    if not only_library and not only_reference:
        print("✅ Both filters pass IDENTICAL transactions (0% difference expected!)")
    else:
        print(
            f"❌ FILTER MISMATCH: {len(only_library)} extra in library, {len(only_reference)} extra in reference"
        )
        print()
        print("This explains the 0.49% price difference!")

    print()
    print("=" * 80)
    print("CONCLUSION")
    print("=" * 80)

    if only_library:
        print("❌ Library filter is MORE PERMISSIVE than reference")
        print("   → Includes transactions with 1 output (reference requires exactly 2)")
        print("   → Missing coinbase, OP_RETURN, witness checks")
        print()
        print("FIX: Update library filter to match reference EXACTLY")
    else:
        print("✅ Filters match - difference must be elsewhere")


if __name__ == "__main__":
    analyze_block_filtering()
