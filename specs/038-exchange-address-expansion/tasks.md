# Tasks: Spec-038 Exchange Address Database Expansion

## Phase 1: Research & Data Collection ✅

- [x] T001 Research available data sources for exchange addresses
- [x] T002 Evaluate Maru92/EntityAddressBitcoin dataset (OBSOLETE - 2018 data)
- [x] T003 Identify WalletExplorer as primary source (fresh Dec 2025)
- [x] T004 Document Arkham Intel and BitInfoCharts as blocked (403)
- [x] T005 Compile verified cold wallet addresses from Proof of Reserves

## Phase 2: Scraper Implementation ✅

- [x] T006 Create `scripts/bootstrap/scrape_exchange_addresses.py`
- [x] T007 Implement WalletExplorer HTML parsing with regex
- [x] T008 Add rate limiting (1 sec between requests)
- [x] T009 Add retry logic with exponential backoff
- [x] T010 Support `--exchange` filter for single exchange
- [x] T011 Support `--max-pages` limit per exchange
- [x] T012 Support `--dry-run` mode

## Phase 3: Data Collection ✅

- [x] T013 Scrape Binance.com (1,004 addresses)
- [x] T014 Scrape Kraken.com (1,002 addresses)
- [x] T015 Scrape Bitfinex.com (1,002 addresses)
- [x] T016 Scrape Bitstamp.net (1,000 addresses)
- [x] T017 Scrape Huobi.com (1,000 addresses)
- [x] T018 Scrape OKCoin.com (1,000 addresses)
- [x] T019 Scrape Poloniex.com (1,000 addresses)
- [x] T020 Scrape Bittrex.com (1,000 addresses)
- [x] T021 Scrape HitBtc.com (1,000 addresses)
- [x] T022 Scrape Luno.com (1,000 addresses)
- [x] T023 Scrape Cex.io (1,000 addresses)
- [x] T024 Scrape Bitcoin.de (1,000 addresses)
- [x] T025 Scrape LocalBitcoins.com (1,000 addresses)
- [x] T026 Merge with verified cold wallets (13 addresses)
- [x] T027 Deduplicate addresses
- [x] T028 Write to `data/exchange_addresses.csv` (13,013 total)

## Phase 4: Documentation ✅

- [x] T029 Create `specs/038-exchange-address-expansion/spec.md`
- [x] T030 Create `specs/038-exchange-address-expansion/research.md`
- [x] T031 Update `docs/ARCHITECTURE.md` with spec-038 section
- [x] T032 Update spec implementation status table

## Phase 5: Automation ✅

- [x] T033 Setup weekly cron job for address refresh (user crontab)
- [x] T034 Create systemd timer as cron alternative
- [x] T035 Add Playwright scraper for blocked sources (Arkham, BitInfoCharts blocked by WAF)

## Phase 6: Integration ✅

- [x] T036 Update `scripts/metrics/exchange_netflow.py` to use bulk COPY
- [x] T037 Add address count validation at startup (warn if <1000)
- [x] T038 Add exchange coverage report endpoint `/api/exchange-addresses/stats`

## Summary

| Phase | Status | Tasks |
|-------|--------|-------|
| Research | ✅ Complete | 5/5 |
| Scraper | ✅ Complete | 7/7 |
| Collection | ✅ Complete | 16/16 |
| Documentation | ✅ Complete | 4/4 |
| Automation | ✅ Complete | 3/3 |
| Integration | ✅ Complete | 3/3 |
| **Total** | **100%** | **38/38** |
