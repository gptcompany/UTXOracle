"""
Electrs HTTP API Example
Purpose: Demonstrate how to fetch raw transaction data for a block.
This is the primary data source for the Whale Flow Detector.
"""
import requests
import json
import os

# Configuration from environment or defaults
ELECTRS_API_URL = os.getenv("ELECTRS_API_URL", "http://localhost:3001")

def fetch_latest_block_hash() -> str:
    """Fetches the hash of the latest block."""
    try:
        response = requests.get(f"{ELECTRS_API_URL}/blocks/tip/hash")
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching latest block hash: {e}")
        return None

def fetch_block_txids(block_hash: str) -> list:
    """Fetches all transaction IDs for a given block hash."""
    try:
        response = requests.get(f"{ELECTRS_API_URL}/block/{block_hash}/txids")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching txids for block {block_hash}: {e}")
        return []

def fetch_transaction(txid: str) -> dict:
    """Fetches the full data for a single transaction."""
    try:
        response = requests.get(f"{ELECTRS_API_URL}/tx/{txid}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching transaction {txid}: {e}")
        return None

if __name__ == "__main__":
    print(f"Querying electrs API at: {ELECTRS_API_URL}")

    # 1. Get the latest block hash
    latest_hash = fetch_latest_block_hash()
    if not latest_hash:
        sys.exit(1)
    print(f"Latest block hash: {latest_hash}")

    # 2. Get all transaction IDs in that block
    txids = fetch_block_txids(latest_hash)
    if not txids:
        sys.exit(1)
    print(f"Found {len(txids)} transactions in block.")

    # 3. Fetch the first 5 transactions as a demonstration
    print("\n--- Fetching first 5 transactions ---")
    for i, txid in enumerate(txids[:5]):
        print(f"\n[{i+1}/{len(txids)}] Fetching tx: {txid}")
        tx_data = fetch_transaction(txid)
        if tx_data:
            # Print a summary of the transaction
            vin_count = len(tx_data.get('vin', []))
            vout_count = len(tx_data.get('vout', []))
            total_value = sum(vout.get('value', 0) for vout in tx_data.get('vout', [])) / 1e8
            print(f"  - Inputs: {vin_count}, Outputs: {vout_count}, Total Value: {total_value:.8f} BTC")
            # print(json.dumps(tx_data, indent=2)) # Uncomment for full details
    print("\n--- Example complete ---")
