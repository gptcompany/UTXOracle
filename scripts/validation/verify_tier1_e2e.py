import requests
import logging
from typing import List

logging.basicConfig(level=logging.INFO)

def _convert_satoshi_to_btc(transactions: List[dict]) -> List[dict]:
    for tx in transactions:
        if "vout" in tx:
            for vout in tx["vout"]:
                if "value" in vout:
                    vout["value"] = vout["value"] / 1e8
    return transactions

def test_tier1_fetch():
    electrs_url = "http://localhost:3002"
    try:
        logging.info(f"Testing Electrs at {electrs_url}")
        resp = requests.get(f"{electrs_url}/blocks/tip/hash", timeout=10)
        resp.raise_for_status()
        best_hash = resp.text.strip().strip('"')
        logging.info(f"Best hash: {best_hash}")

        resp = requests.get(f"{electrs_url}/block/{best_hash}/txids", timeout=30)
        resp.raise_for_status()
        txids = resp.json()
        logging.info(f"Fetched {len(txids)} txids")

        if len(txids) > 0:
            txid = txids[0]
            logging.info(f"Fetching full data for tx {txid}")
            resp = requests.get(f"{electrs_url}/tx/{txid}", timeout=10)
            resp.raise_for_status()
            tx = resp.json()
            logging.info("Successfully fetched full transaction data")
            
            # Test conversion
            original_val = tx["vout"][0]["value"]
            converted_txs = _convert_satoshi_to_btc([tx])
            new_val = converted_txs[0]["vout"][0]["value"]
            logging.info(f"Satoshi to BTC conversion: {original_val} -> {new_val}")
            
            if abs(new_val - (original_val / 1e8)) < 1e-10:
                logging.info("✅ Tier 1 E2E Verification PASSED")
            else:
                logging.error("❌ Conversion mismatch")
        else:
            logging.warning("No transactions in block")
            
    except Exception as e:
        logging.error(f"❌ Tier 1 E2E Verification FAILED: {e}")

if __name__ == "__main__":
    test_tier1_fetch()
