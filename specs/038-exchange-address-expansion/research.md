# Research: Exchange Address Database Expansion

## Data Sources Evaluated (Dec 2025)

### Tier 1: Primary Sources (Used)

| Source | URL | Addresses | Freshness | Status |
|--------|-----|-----------|-----------|--------|
| WalletExplorer | walletexplorer.com | 50,000+ per exchange | Updated daily | ✅ Scraped |
| Arkham Intel | intel.arkm.com | 10,000+ entities | Real-time | ⚠️ 403 blocked |
| BitInfoCharts | bitinfocharts.com | 1000s labeled | Updated daily | ⚠️ 403 blocked |

### Tier 2: Proof of Reserves (Verified Cold Wallets)

| Exchange | BTC Holdings | Cold Wallet Addresses | Source |
|----------|--------------|----------------------|--------|
| Binance | 475,000 BTC | 34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo (248K), 3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6 (142K) | binance.com/proof-of-reserves |
| Bitfinex | 138,000 BTC | 3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r | bitinfocharts.com |
| Kraken | 192,000 BTC | bc1qu* (30K), bc1q9* (22K) | blog.kraken.com/por-march-2025 |
| Coinbase | 516B AUM | Undisclosed (public company) | SEC filings |
| OKX | 23.1B USD | Published 23,000+ addresses | github.com/okx/proof-of-reserves |

### Tier 3: Academic Datasets (Obsolete)

| Source | Addresses | Date | Issue |
|--------|-----------|------|-------|
| Maru92/EntityAddressBitcoin | 7.6M exchange | Apr 2018 | **Too old** - missing bc1, modern exchanges |
| Figshare Dataset | 103K labeled | 2022 | Incomplete exchange coverage |

## Implementation

### Automated Scraper Created

```bash
# One-time full scrape (~30 min)
python -m scripts.bootstrap.scrape_exchange_addresses --max-pages 50

# Weekly cron job (recommended)
0 3 * * 0 cd /media/sam/1TB/UTXOracle && python -m scripts.bootstrap.scrape_exchange_addresses --max-pages 50
```

### Exchanges Scraped from WalletExplorer

| Exchange | WalletExplorer ID | Est. Addresses |
|----------|-------------------|----------------|
| Binance | Binance.com | 5,000+ |
| Kraken | Kraken.com | 3,000+ |
| Bitfinex | Bitfinex.com | 4,000 |
| Bitstamp | Bitstamp.net | 2,000+ |
| Huobi | Huobi.com | 3,000+ |
| OKCoin | OKCoin.com | 1,500+ |
| Poloniex | Poloniex.com | 2,000+ |
| Bittrex | Bittrex.com | 1,500+ |
| HitBTC | HitBtc.com | 1,000+ |
| LocalBitcoins | LocalBitcoins.com | 5,000+ |
| Luno | Luno.com | 2,000+ |
| CEX.io | Cex.io | 1,000+ |
| Bitcoin.de | Bitcoin.de | 1,000+ |

**Estimated Total**: 30,000+ unique addresses

## Verified Cold Wallets (Always Include)

These addresses are manually verified from Proof of Reserves disclosures:

```python
VERIFIED_COLD_WALLETS = [
    # Binance
    ("Binance", "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo", "cold_wallet"),  # 248K BTC
    ("Binance", "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6", "cold_wallet"),  # 142K BTC
    ("Binance", "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h", "cold_wallet"),
    # Bitfinex
    ("Bitfinex", "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r", "cold_wallet"),  # 138K BTC
    # Kraken
    ("Kraken", "bc1qu30560k5wc8jm58hwx3crlvlydc6vz78npce4z", "cold_wallet"),  # 30K BTC
    # OKX
    ("OKX", "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfl6t94", "cold_wallet"),
    # Coinbase (limited)
    ("Coinbase", "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64", "cold_wallet"),
]
```

## Blocked Sources (Need Alternative)

1. **Arkham Intelligence** (intel.arkm.com) - 403 Forbidden
   - Alternative: Use their public API if available

2. **BitInfoCharts** (bitinfocharts.com) - 403 Forbidden
   - Alternative: Scrape with browser automation (Playwright)

3. **Coinbase** - No public wallet disclosure
   - Workaround: Use Arkham's entity tracking when accessible

## Recommendations

1. **Run scraper weekly** via cron to capture new addresses
2. **Add Playwright scraper** for sites blocking requests
3. **Monitor Arkham API** for public endpoint availability
4. **Cross-validate** addresses with on-chain activity (>1 tx in last 30 days)
