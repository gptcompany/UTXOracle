"""
Address Parsing & Extraction Example
Source: Logic adapted from https://github.com/1200wd/bitcoinlib
Purpose: Show how to extract input and output addresses from a raw
         transaction object fetched from the electrs API.
"""
import json

# Mock electrs transaction data for demonstration
# In a real scenario, this would come from fetch_transaction(txid)
MOCK_TX_DATA = {
  "txid": "f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16",
  "version": 1,
  "locktime": 0,
  "vin": [
    {
      "txid": "a1b2c3...",
      "vout": 0,
      "prevout": {
        "scriptpubkey": "76a914751e76e8199196d454941c45d1b3a323f1433bd688ac",
        "scriptpubkey_asm": "OP_DUP OP_HASH160 OP_PUSHBYTES_20 751e76e8199196d454941c45d1b3a323f1433bd6 OP_EQUALVERIFY OP_CHECKSIG",
        "scriptpubkey_type": "p2pkh",
        "scriptpubkey_address": "1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH",
        "value": 5000000000
      },
      "scriptsig": "483045022100884d142d86652a3f47ba4746ec719bbfbd040a570b1deccbb6498c75c4ae24cb02204b913739185cf427c712848e04de1e5420343a4902b030de7244c8242341716601",
      "scriptsig_asm": "OP_PUSHBYTES_72 3045022100884d142d86652a3f47ba4746ec719bbfbd040a570b1deccbb6498c75c4ae24cb02204b913739185cf427c712848e04de1e5420343a4902b030de7244c8242341716601 OP_PUSHBYTES_1 01",
      "is_coinbase": false
    }
  ],
  "vout": [
    {
      "scriptpubkey": "76a914751e76e8199196d454941c45d1b3a323f1433bd688ac",
      "scriptpubkey_asm": "OP_DUP OP_HASH160 OP_PUSHBYTES_20 751e76e8199196d454941c45d1b3a323f1433bd6 OP_EQUALVERIFY OP_CHECKSIG",
      "scriptpubkey_type": "p2pkh",
      "scriptpubkey_address": "1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH",
      "value": 4999900000
    },
    {
      "scriptpubkey": "a914f9a839a38c95c3e4a231e24c23a39401f84524f387",
      "scriptpubkey_asm": "OP_HASH160 OP_PUSHBYTES_20 f9a839a38c95c3e4a231e24c23a39401f84524f3 OP_EQUAL",
      "scriptpubkey_type": "p2sh",
      "scriptpubkey_address": "3P14159f73E4gFrCh2HRze1k41v22b2p7g",
      "value": 100000
    }
  ],
  "status": {
    "confirmed": true,
    "block_height": 600000,
    "block_hash": "0000000000000000000a2c5f1e9c4a8a4bc9e7a362a1a2f897d2c84b40e4b66a",
    "block_time": 1571769413
  }
}

def parse_addresses_from_transaction(tx_data: dict) -> tuple:
    """
    Extracts input and output addresses from a raw electrs transaction.
    This is a critical step for tracking flows between entities.
    """
    input_addresses = set()
    output_addresses = set()

    # Extract from vin (inputs)
    # The address that *sent* the funds is in the 'prevout' of the input
    for vin in tx_data.get('vin', []):
        if 'prevout' in vin and vin['prevout'] and 'scriptpubkey_address' in vin['prevout']:
            input_addresses.add(vin['prevout']['scriptpubkey_address'])

    # Extract from vout (outputs)
    # The address that *received* the funds is in the output itself
    for vout in tx_data.get('vout', []):
        if 'scriptpubkey_address' in vout:
            output_addresses.add(vout['scriptpubkey_address'])

    return list(input_addresses), list(output_addresses)

if __name__ == "__main__":
    print("--- Parsing addresses from a mock transaction ---")
    
    inputs, outputs = parse_addresses_from_transaction(MOCK_TX_DATA)
    
    print(f"\nInput Addresses ({len(inputs)}):")
    for addr in inputs:
        print(f"  - {addr}")
        
    print(f"\nOutput Addresses ({len(outputs)}):")
    for addr in outputs:
        print(f"  - {addr}")

    print("\n--- Example complete ---")
    print("Note: bitcoinlib is not needed for simple parsing if the electrs API provides the address directly.")
    print("It would be used for more complex script validation or offline address generation.")
