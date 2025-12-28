# Spec-038: Exchange Address Database Expansion

## Problem Statement

Current exchange address database has only **10 curated addresses** from 4 exchanges. The 2018 academic dataset (Maru92) is **obsolete** - missing modern addresses for:
- Binance (launched 2017, grew massively post-2018)
- Coinbase (new cold wallets post-IPO 2021)
- FTX successor addresses (post-bankruptcy 2022)
- OKX, Bybit, Bitget, KuCoin (2020+ growth)
- All SegWit/Bech32 addresses (bc1...)

**Impact**: Exchange netflow metrics (spec-026) are unreliable without comprehensive address coverage.

## Goal

Build **comprehensive, current** exchange address database through exhaustive web research.

**Target**: 10,000+ verified addresses from 20+ exchanges (2023-2025 data).

## Research Sources (Priority Order)

### Tier 1: Blockchain Intelligence (High Quality)

| Source | Type | Coverage | Access |
|--------|------|----------|--------|
| [Arkham Intelligence](https://platform.arkhamintelligence.com/) | Entity labels | 50,000+ entities | Free tier |
| [Etherscan Labels](https://etherscan.io/labelcloud) | Exchange tags | Major exchanges | Free |
| [OXT.me](https://oxt.me/) | Wallet clusters | Exchange detection | Free |
| [Blockchain.com Explorer](https://www.blockchain.com/explorer) | Known addresses | Top wallets | Free |

### Tier 2: Community Curated Lists

| Source | Type | Freshness |
|--------|------|-----------|
| [BitcoinWhosWho](https://www.bitcoinwhoswho.com/) | Scam + exchange DB | Updated 2024 |
| [WalletExplorer](https://www.walletexplorer.com/) | Cluster labels | Updated 2023 |
| [CryptoScamDB](https://cryptoscamdb.org/) | Exchange + scam | Active |
| GitHub repos (search "bitcoin exchange addresses") | Various | Mixed |

### Tier 3: Exchange Official Sources

| Exchange | Source | Method |
|----------|--------|--------|
| Binance | Proof of Reserves | Published addresses |
| Coinbase | SEC filings | Cold wallet disclosure |
| Kraken | Transparency reports | Published addresses |
| OKX | Proof of Reserves | Merkle tree roots |
| Bitfinex | Public announcements | Known cold wallets |

### Tier 4: On-Chain Analytics

| Method | Description |
|--------|-------------|
| Large holder tracking | >10,000 BTC addresses |
| Deposit pattern analysis | Common input clustering |
| Exchange hot wallet heuristics | High tx frequency + round amounts |

## Deliverables

1. **research.md** - Findings from each source with address counts
2. **data/exchange_addresses_2025.csv** - Verified addresses
3. **scripts/bootstrap/scrape_exchange_addresses.py** - Automated collection
4. **Validation report** - Cross-reference with on-chain activity

## Success Criteria

| Metric | Target |
|--------|--------|
| Total addresses | >10,000 |
| Exchanges covered | >20 |
| Data freshness | 2023-2025 |
| Verification rate | >90% (confirmed on-chain activity) |

## User Stories

### US1: Arkham Intelligence Scrape (P1)
Collect labeled Bitcoin addresses from Arkham's public explorer for all major exchanges.

### US2: Proof of Reserves Collection (P1)
Extract addresses from exchange transparency reports and PoR publications.

### US3: WalletExplorer Refresh (P2)
Scrape current cluster labels from WalletExplorer for exchange identification.

### US4: GitHub Repository Aggregation (P2)
Search and aggregate exchange address lists from GitHub repositories.

### US5: On-Chain Verification (P3)
Verify collected addresses have recent on-chain activity (2024-2025).

## Constraints

- No paid API subscriptions required
- Manual verification for addresses >1,000 BTC
- Respect rate limits on scraped sources
- Document source for each address (provenance)

## Timeline

Research-intensive task requiring ~8-12 hours of web scraping and verification.
