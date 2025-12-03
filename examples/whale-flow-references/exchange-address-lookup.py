"""
Exchange Address Lookup Example
Source for address list: https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17
Purpose: Demonstrate an efficient O(1) lookup method for checking if an
         address belongs to a known exchange.
"""
import requests
import time

# In a real application, this URL would be in a config file
EXCHANGE_ADDRESS_GIST_URL = "https://gist.githubusercontent.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17/raw/9278298a5332a102443c44831134c31253348a7a/exchange_addresses.txt"

def load_exchange_addresses() -> set:
    """
    Downloads a list of known exchange addresses and loads them into a set
    for efficient lookups.
    """
    print(f"Downloading exchange address list from Gist...")
    try:
        response = requests.get(EXCHANGE_ADDRESS_GIST_URL, timeout=10)
        response.raise_for_status()
        addresses = response.text.splitlines()
        # Using a set provides O(1) average time complexity for lookups
        address_set = {addr.strip() for addr in addresses if addr.strip()}
        print(f"Loaded {len(address_set):,} unique exchange addresses into the lookup set.")
        return address_set
    except requests.exceptions.RequestException as e:
        print(f"Error downloading address list: {e}")
        return set()

if __name__ == "__main__":
    exchange_addresses = load_exchange_addresses()

    if not exchange_addresses:
        print("Could not load addresses. Exiting.")
        exit()

    # --- Test Cases ---
    known_exchange_addr = "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX" # A known Binance address from the list
    random_personal_addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh" # A random address

    print("\n--- Testing address lookups ---")

    # Test 1: A known exchange address
    start_time = time.perf_counter()
    is_exchange = known_exchange_addr in exchange_addresses
    end_time = time.perf_counter()
    print(f"Is '{known_exchange_addr[:10]}...' an exchange? -> {is_exchange}")
    print(f"  (Lookup time: {(end_time - start_time) * 1e6:.2f} microseconds)")

    # Test 2: A random personal address
    start_time = time.perf_counter()
    is_exchange = random_personal_addr in exchange_addresses
    end_time = time.perf_counter()
    print(f"Is '{random_personal_addr[:10]}...' an exchange? -> {is_exchange}")
    print(f"  (Lookup time: {(end_time - start_time) * 1e6:.2f} microseconds)")
    
    print("\n--- Example complete ---")
    print("Note the extremely fast lookup times, which are critical for processing thousands of transactions per block.")
