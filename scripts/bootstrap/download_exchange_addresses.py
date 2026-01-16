#!/usr/bin/env python3
"""Download and process exchange addresses from academic dataset.

Source: EntityAddressBitcoin dataset (EPFL, 2018)
https://github.com/Maru92/EntityAddressBitcoin

Downloads 5M+ labeled exchange addresses and converts to UTXOracle format.
"""

import csv
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Dataset URL (hosted on Switch Drive, ~1GB)
DATASET_URL = "https://drive.switch.ch/index.php/s/ag4OnNgwf7LhWFu/download"

# Output path
OUTPUT_PATH = Path(__file__).parent.parent.parent / "data" / "exchange_addresses.csv"

# Exchange name mapping (normalize to consistent names)
EXCHANGE_MAP = {
    "Bittrex.com": "Bittrex",
    "Poloniex.com": "Poloniex",
    "LocalBitcoins.com": "LocalBitcoins",
    "Bitstamp.net": "Bitstamp",
    "Huobi.com": "Huobi",
    "Cex.io": "CEX.io",
    "HitBtc.com": "HitBTC",
    "OKCoin.com": "OKCoin",
    "Kraken.com": "Kraken",
    "BTCC.com": "BTCC",
    "Coinbase.com": "Coinbase",
    "Gemini.com": "Gemini",
    "Bitfinex.com": "Bitfinex",
    "BTC-e.com": "BTC-e",
    "Bitcoin.de": "Bitcoin.de",
    "Luno.com": "Luno",
    "Paxful.com": "Paxful",
}

# Curated addresses to preserve (more recent, verified)
CURATED_ADDRESSES = [
    ("Binance", "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX", "hot_wallet"),
    ("Binance", "3P14159f73E4gFrCh2HRze1k41v22b2p7g", "cold_wallet"),
    ("Binance", "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s", "hot_wallet"),
    ("Binance", "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h", "segwit_hot"),
    ("Bitfinex", "1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g", "hot_wallet"),
    ("Bitfinex", "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r", "cold_wallet"),
    ("Kraken", "3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE", "cold_wallet"),
    (
        "Kraken",
        "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
        "segwit_hot",
    ),
    ("Coinbase", "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64", "cold_wallet"),
    ("Coinbase", "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "segwit_hot"),
]


def download_progress(block_num: int, block_size: int, total_size: int) -> None:
    """Show download progress."""
    if total_size > 0:
        percent = min(100, block_num * block_size * 100 / total_size)
        mb_downloaded = block_num * block_size / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(
            f"\rDownloading: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)"
        )
        sys.stdout.flush()


def main() -> None:
    """Download and process exchange addresses."""
    print("Exchange Address Database Builder")
    print("=" * 50)
    print(f"Source: {DATASET_URL}")
    print(f"Output: {OUTPUT_PATH}")
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "entity_addresses.zip"

        # Download dataset
        print("Downloading dataset (~1GB)...")
        urlretrieve(DATASET_URL, zip_path, download_progress)
        print("\nDownload complete!")

        # Extract
        print("Extracting...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        exchanges_csv = Path(tmpdir) / "data" / "Exchanges_full_detailed.csv"

        # Process
        print("Processing exchange addresses...")
        addresses = []
        seen = set()

        # Add curated addresses first
        for exchange, address, addr_type in CURATED_ADDRESSES:
            addresses.append(
                {"exchange_name": exchange, "address": address, "type": addr_type}
            )
            seen.add(address)

        # Add from dataset
        with open(exchanges_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                exchange = row["exchange"]
                if exchange in EXCHANGE_MAP and row["hashAdd"] not in seen:
                    addresses.append(
                        {
                            "exchange_name": EXCHANGE_MAP[exchange],
                            "address": row["hashAdd"],
                            "type": "wallet",
                        }
                    )
                    seen.add(row["hashAdd"])

        # Write output
        print(f"Writing {len(addresses):,} addresses to {OUTPUT_PATH}...")
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["exchange_name", "address", "type"])
            writer.writeheader()
            writer.writerows(addresses)

        # Summary
        print()
        print("Summary:")
        from collections import Counter

        counts = Counter(a["exchange_name"] for a in addresses)
        for exchange, count in counts.most_common():
            print(f"  {exchange}: {count:,}")
        print(f"\nTotal: {len(addresses):,} addresses")


if __name__ == "__main__":
    main()
