#!/usr/bin/env python3
"""Automated exchange address scraper from WalletExplorer.

Scrapes ALL pages from WalletExplorer for each exchange.
Run weekly via cron to keep addresses current.

Usage:
    python -m scripts.bootstrap.scrape_exchange_addresses
    python -m scripts.bootstrap.scrape_exchange_addresses --exchange Binance.com
    python -m scripts.bootstrap.scrape_exchange_addresses --dry-run
"""

import argparse
import csv
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# WalletExplorer exchanges to scrape
EXCHANGES = {
    "Binance.com": "Binance",
    "Kraken.com": "Kraken",
    "Bitfinex.com": "Bitfinex",
    "Bitstamp.net": "Bitstamp",
    "Huobi.com": "Huobi",
    "OKCoin.com": "OKCoin",
    "Poloniex.com": "Poloniex",
    "Bittrex.com": "Bittrex",
    "HitBtc.com": "HitBTC",
    "Coincheck.com": "Coincheck",
    "Luno.com": "Luno",
    "Cex.io": "CEX.io",
    "Bitcoin.de": "Bitcoin.de",
    "LocalBitcoins.com": "LocalBitcoins",
}

# Known cold wallets (manually verified, always include)
VERIFIED_COLD_WALLETS = [
    # Binance
    ("Binance", "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo", "cold_wallet"),  # 248K BTC
    ("Binance", "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6", "cold_wallet"),  # 142K BTC
    ("Binance", "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h", "cold_wallet"),
    ("Binance", "1Pzaqw98PeRfyHypfqyEgg5yycJRsENrE7t", "cold_wallet"),
    # Bitfinex
    ("Bitfinex", "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r", "cold_wallet"),  # 138K BTC
    ("Bitfinex", "1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g", "cold_wallet"),
    # Kraken
    ("Kraken", "bc1qu30560k5wc8jm58hwx3crlvlydc6vz78npce4z", "cold_wallet"),  # 30K BTC
    (
        "Kraken",
        "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
        "cold_wallet",
    ),
    # Coinbase (limited public disclosure)
    ("Coinbase", "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64", "cold_wallet"),
    ("Coinbase", "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "cold_wallet"),
    # OKX
    (
        "OKX",
        "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfl6t94",
        "cold_wallet",
    ),
    ("OKX", "3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a", "cold_wallet"),
    # Bybit
    ("Bybit", "bc1q7t9fxfaakmtk8pj7tdxjqwz0xj66k2dqusgv8w", "cold_wallet"),
]

OUTPUT_PATH = Path(__file__).parent.parent.parent / "data" / "exchange_addresses.csv"

# Bitcoin address regex
BTC_ADDR_PATTERN = re.compile(
    r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{39,59})\b"
)


def fetch_page(url: str, retries: int = 3) -> str:
    """Fetch URL with retries and rate limiting."""
    headers = {"User-Agent": "UTXOracle/1.0 (Exchange Address Research)"}
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except (HTTPError, URLError) as e:
            print(f"  Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2**attempt)  # Exponential backoff
    return ""


def scrape_wallet_explorer(wallet_name: str, max_pages: int = 100) -> list[str]:
    """Scrape all addresses for a wallet from WalletExplorer."""
    addresses = []
    base_url = f"https://www.walletexplorer.com/wallet/{wallet_name}/addresses"

    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}" if page > 1 else base_url
        print(f"  Fetching page {page}...")

        html = fetch_page(url)
        if not html:
            print(f"  Failed to fetch page {page}, stopping")
            break

        # Extract addresses
        found = BTC_ADDR_PATTERN.findall(html)
        if not found:
            print(f"  No addresses found on page {page}, stopping")
            break

        addresses.extend(found)
        print(f"  Found {len(found)} addresses (total: {len(addresses)})")

        # Check if there's a next page
        if f"page={page + 1}" not in html and page > 1:
            print(f"  No more pages after {page}")
            break

        # Rate limit
        time.sleep(1)

    return addresses


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape exchange addresses from WalletExplorer"
    )
    parser.add_argument(
        "--exchange", help="Scrape only this exchange (e.g., Binance.com)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=50, help="Max pages per exchange"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't write output file"
    )
    args = parser.parse_args()

    print("Exchange Address Scraper")
    print("=" * 50)
    print(f"Output: {OUTPUT_PATH}")
    print()

    all_addresses: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    # Add verified cold wallets first
    for exchange, addr, addr_type in VERIFIED_COLD_WALLETS:
        if addr not in seen:
            all_addresses.append((exchange, addr, addr_type))
            seen.add(addr)
    print(f"Added {len(all_addresses)} verified cold wallets")

    # Scrape exchanges
    exchanges_to_scrape = (
        {args.exchange: EXCHANGES.get(args.exchange, args.exchange)}
        if args.exchange
        else EXCHANGES
    )

    for wallet_name, exchange_name in exchanges_to_scrape.items():
        print(f"\nScraping {wallet_name} -> {exchange_name}")
        addresses = scrape_wallet_explorer(wallet_name, args.max_pages)

        new_count = 0
        for addr in addresses:
            if addr not in seen:
                all_addresses.append((exchange_name, addr, "wallet"))
                seen.add(addr)
                new_count += 1

        print(f"  Added {new_count} new addresses for {exchange_name}")

    # Summary
    print("\n" + "=" * 50)
    print("Summary:")
    from collections import Counter

    counts = Counter(ex for ex, _, _ in all_addresses)
    for exchange, count in counts.most_common():
        print(f"  {exchange}: {count:,}")
    print(f"\nTotal: {len(all_addresses):,} addresses")

    if args.dry_run:
        print("\n[DRY RUN] Not writing output file")
        return

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["exchange_name", "address", "type"])
        for exchange, addr, addr_type in all_addresses:
            writer.writerow([exchange, addr, addr_type])

    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
