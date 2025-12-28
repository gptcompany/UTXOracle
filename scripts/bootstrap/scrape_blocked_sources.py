#!/usr/bin/env python3
"""
Playwright-based scraper for blocked exchange address sources.

Uses headless browser to bypass 403 restrictions on:
- Arkham Intel (arkham.io)
- BitInfoCharts (bitinfocharts.com)

Usage:
    uv run python -m scripts.bootstrap.scrape_blocked_sources
    uv run python -m scripts.bootstrap.scrape_blocked_sources --source arkham
    uv run python -m scripts.bootstrap.scrape_blocked_sources --source bitinfocharts
"""

import argparse
import csv
import logging
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Output path
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data"
EXCHANGE_CSV = OUTPUT_DIR / "exchange_addresses.csv"

# Arkham Intel exchange entity URLs
ARKHAM_EXCHANGES = {
    "Binance": "https://platform.arkhamintelligence.com/explorer/entity/binance",
    "Coinbase": "https://platform.arkhamintelligence.com/explorer/entity/coinbase",
    "Kraken": "https://platform.arkhamintelligence.com/explorer/entity/kraken",
    "Bitfinex": "https://platform.arkhamintelligence.com/explorer/entity/bitfinex",
    "OKX": "https://platform.arkhamintelligence.com/explorer/entity/okx",
    "Bybit": "https://platform.arkhamintelligence.com/explorer/entity/bybit",
    "KuCoin": "https://platform.arkhamintelligence.com/explorer/entity/kucoin",
    "Gemini": "https://platform.arkhamintelligence.com/explorer/entity/gemini",
}

# BitInfoCharts rich list URLs
BITINFOCHARTS_EXCHANGES = {
    "Binance": "https://bitinfocharts.com/bitcoin/wallet/Binance-coldwallet",
    "Bitfinex": "https://bitinfocharts.com/bitcoin/wallet/Bitfinex-coldwallet",
    "Kraken": "https://bitinfocharts.com/bitcoin/wallet/Kraken.com",
    "Huobi": "https://bitinfocharts.com/bitcoin/wallet/Huobi",
    "OKX": "https://bitinfocharts.com/bitcoin/wallet/OKX.com",
}


def scrape_arkham(page, exchange_name: str, url: str) -> list[tuple[str, str, str]]:
    """Scrape Bitcoin addresses from Arkham Intel entity page."""
    addresses = []

    try:
        logger.info(f"Scraping Arkham: {exchange_name} from {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait for page to load
        time.sleep(3)

        # Look for Bitcoin addresses in the page
        # Arkham displays addresses in tables or lists
        content = page.content()

        # Find Bitcoin addresses (P2PKH, P2SH, P2WPKH, P2WSH, P2TR patterns)
        btc_patterns = [
            r"\b(1[a-km-zA-HJ-NP-Z1-9]{25,34})\b",  # P2PKH (legacy)
            r"\b(3[a-km-zA-HJ-NP-Z1-9]{25,34})\b",  # P2SH
            r"\b(bc1q[a-z0-9]{38,59})\b",  # P2WPKH/P2WSH (bech32)
            r"\b(bc1p[a-z0-9]{58})\b",  # P2TR (taproot)
        ]

        for pattern in btc_patterns:
            matches = re.findall(pattern, content)
            for addr in matches:
                if len(addr) >= 26:  # Minimum BTC address length
                    addresses.append((exchange_name, addr, "arkham_scraped"))

        # Deduplicate
        addresses = list(set(addresses))
        logger.info(f"Found {len(addresses)} addresses for {exchange_name} on Arkham")

    except PlaywrightTimeout:
        logger.warning(f"Timeout loading {url}")
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")

    return addresses


def scrape_bitinfocharts(
    page, exchange_name: str, url: str
) -> list[tuple[str, str, str]]:
    """Scrape Bitcoin addresses from BitInfoCharts wallet page."""
    addresses = []

    try:
        logger.info(f"Scraping BitInfoCharts: {exchange_name} from {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait for dynamic content
        time.sleep(2)

        content = page.content()

        # BitInfoCharts shows main wallet address and related addresses
        btc_patterns = [
            r"\b(1[a-km-zA-HJ-NP-Z1-9]{25,34})\b",
            r"\b(3[a-km-zA-HJ-NP-Z1-9]{25,34})\b",
            r"\b(bc1q[a-z0-9]{38,59})\b",
            r"\b(bc1p[a-z0-9]{58})\b",
        ]

        for pattern in btc_patterns:
            matches = re.findall(pattern, content)
            for addr in matches:
                if len(addr) >= 26:
                    addresses.append((exchange_name, addr, "bitinfocharts_scraped"))

        addresses = list(set(addresses))
        logger.info(
            f"Found {len(addresses)} addresses for {exchange_name} on BitInfoCharts"
        )

    except PlaywrightTimeout:
        logger.warning(f"Timeout loading {url}")
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")

    return addresses


def load_existing_addresses() -> set[str]:
    """Load existing addresses from CSV to avoid duplicates."""
    existing = set()
    if EXCHANGE_CSV.exists():
        with open(EXCHANGE_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row["address"])
    return existing


def append_to_csv(new_addresses: list[tuple[str, str, str]]):
    """Append new addresses to CSV file."""
    if not new_addresses:
        logger.info("No new addresses to append")
        return

    existing = load_existing_addresses()
    unique_new = [
        (ex, addr, typ) for ex, addr, typ in new_addresses if addr not in existing
    ]

    if not unique_new:
        logger.info("All scraped addresses already exist in CSV")
        return

    # Append to existing CSV
    with open(EXCHANGE_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        for exchange_name, address, addr_type in unique_new:
            writer.writerow([exchange_name, address, addr_type])

    logger.info(f"Appended {len(unique_new)} new addresses to {EXCHANGE_CSV}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape blocked exchange address sources"
    )
    parser.add_argument(
        "--source",
        choices=["arkham", "bitinfocharts", "all"],
        default="all",
        help="Source to scrape (default: all)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print addresses without saving",
    )
    args = parser.parse_args()

    all_addresses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Scrape Arkham
        if args.source in ("arkham", "all"):
            for exchange_name, url in ARKHAM_EXCHANGES.items():
                addresses = scrape_arkham(page, exchange_name, url)
                all_addresses.extend(addresses)
                time.sleep(2)  # Rate limiting

        # Scrape BitInfoCharts
        if args.source in ("bitinfocharts", "all"):
            for exchange_name, url in BITINFOCHARTS_EXCHANGES.items():
                addresses = scrape_bitinfocharts(page, exchange_name, url)
                all_addresses.extend(addresses)
                time.sleep(2)

        browser.close()

    # Deduplicate by address
    seen = set()
    unique_addresses = []
    for ex, addr, typ in all_addresses:
        if addr not in seen:
            seen.add(addr)
            unique_addresses.append((ex, addr, typ))

    logger.info(f"Total unique addresses scraped: {len(unique_addresses)}")

    if args.dry_run:
        for ex, addr, typ in unique_addresses[:20]:
            print(f"{ex},{addr},{typ}")
        if len(unique_addresses) > 20:
            print(f"... and {len(unique_addresses) - 20} more")
    else:
        append_to_csv(unique_addresses)

    return 0


if __name__ == "__main__":
    sys.exit(main())
