
"""
Whale Flow Classification Logic Example
Purpose: Demonstrate the core logic for classifying a transaction as an
         exchange inflow, outflow, or neither. This is the heart of the
         Whale Flow Detector.
"""

# Assume we have these pre-loaded (from other examples)
EXCHANGE_ADDRESSES = {
    "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX", # Binance
    "3P14159f73E4gFrCh2HRze1k41v22b2p7g", # Another exchange
    # ... plus 500+ more addresses
}

# --- Mock Data ---
# This would come from parse_addresses_from_transaction()
TX_INFLOW = {
    "input_addresses": ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"], # Personal wallet
    "output_addresses": ["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"], # Binance wallet
    "value_to_exchange": 50.1 # BTC
}

TX_OUTFLOW = {
    "input_addresses": ["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"], # Binance wallet
    "output_addresses": ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"], # Personal wallet
    "value_from_exchange": 25.5 # BTC
}

TX_INTERNAL = {
    "input_addresses": ["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"], # Binance wallet
    "output_addresses": ["3P14159f73E4gFrCh2HRze1k41v22b2p7g"], # Another Binance wallet
    "value_to_exchange": 100.0 # BTC
}

TX_UNRELATED = {
    "input_addresses": ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"], # Personal wallet 1
    "output_addresses": ["3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"], # Personal wallet 2
    "value_to_exchange": 0 # No value to exchange
}


def classify_transaction(input_addrs: list, output_addrs: list, exchange_addrs: set) -> tuple:
    """
    Classifies a transaction based on its input and output addresses.

    Returns:
        A tuple: (flow_type, direction_multiplier)
        flow_type: "inflow", "outflow", "internal", "unrelated"
        direction_multiplier: 1 for inflow, -1 for outflow, 0 otherwise
    """
    input_is_exchange = any(addr in exchange_addrs for addr in input_addrs)
    output_is_exchange = any(addr in exchange_addrs for addr in output_addrs)

    if not input_is_exchange and output_is_exchange:
        # From personal wallet(s) TO an exchange
        return "inflow", 1
    
    if input_is_exchange and not output_is_exchange:
        # From an exchange TO personal wallet(s)
        return "outflow", -1
        
    if input_is_exchange and output_is_exchange:
        # Between two exchange wallets (e.g., hot to cold wallet transfer)
        return "internal", 0
        
    # Between two personal wallets
    return "unrelated", 0

def calculate_flow_value(output_addrs: list, tx_vouts: list, exchange_addrs: set) -> float:
    """
    Calculates the total BTC value sent TO exchange addresses in a transaction.
    """
    total_value = 0
    for vout in tx_vouts:
        addr = vout.get('scriptpubkey_address')
        if addr and addr in exchange_addrs:
            total_value += vout.get('value', 0)
    return total_value / 1e8 # Convert from satoshis to BTC

if __name__ == "__main__":
    print("--- Testing transaction classification logic ---")

    # Test Case 1: Inflow
    flow_type, _ = classify_transaction(TX_INFLOW["input_addresses"], TX_INFLOW["output_addresses"], EXCHANGE_ADDRESSES)
    print(f"Transaction 1 is an: {flow_type.upper()}")
    assert flow_type == "inflow"

    # Test Case 2: Outflow
    flow_type, _ = classify_transaction(TX_OUTFLOW["input_addresses"], TX_OUTFLOW["output_addresses"], EXCHANGE_ADDRESSES)
    print(f"Transaction 2 is an: {flow_type.upper()}")
    assert flow_type == "outflow"

    # Test Case 3: Internal Exchange Transfer
    flow_type, _ = classify_transaction(TX_INTERNAL["input_addresses"], TX_INTERNAL["output_addresses"], EXCHANGE_ADDRESSES)
    print(f"Transaction 3 is an: {flow_type.upper()} transfer")
    assert flow_type == "internal"

    # Test Case 4: Unrelated P2P Transfer
    flow_type, _ = classify_transaction(TX_UNRELATED["input_addresses"], TX_UNRELATED["output_addresses"], EXCHANGE_ADDRESSES)
    print(f"Transaction 4 is an: {flow_type.upper()} transfer")
    assert flow_type == "unrelated"

    print("\n--- Example complete ---")
