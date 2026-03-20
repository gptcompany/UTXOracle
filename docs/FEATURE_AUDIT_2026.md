# UTXOracle Feature Audit 2026-03-20

This audit summarizes what the repository already exposes today, where it overlaps with `BRK`, and which upstream should be treated as authoritative in the live production direction.

## Current UTXOracle Feature Surface

### 1. Core Oracle and Price APIs

Current FastAPI families in `api/main.py`:
- `/api/prices/latest`
- `/api/prices/historical`
- `/api/prices/comparison`
- `/health`

Core repo responsibilities:
- canonical on-chain oracle price calculation from `UTXOracle.py` and `UTXOracle_library.py`
- historical storage and comparison against external market references
- future normalized consumer API for live systems

### 2. Whale and Live Monitoring Features

Current repo components:
- `/api/whale/latest`
- `/api/whale/historical`
- `/api/whale/history`
- `scripts/whale_detection_orchestrator.py`
- `scripts/mempool_whale_monitor.py`
- `scripts/whale_flow_detector.py`
- `scripts/whale_alert_broadcaster.py`
- `scripts/whale_urgency_scorer.py`

Primary characteristics:
- built around `mempool-api` WebSocket input
- augmented with repo-local analytics and storage
- focused on whale flow, alerting, and custom downstream logic

### 3. On-Chain Metrics Families Already Implemented

Current metric endpoint families visible in `api/main.py`:
- latest and advanced metric bundles
- Wasserstein distance
- cointime economics
- URPD
- supply profit/loss
- reserve risk
- sell-side risk
- CDD/VDD
- NUPL
- revived supply
- cost basis
- address balance cohorts
- wallet waves
- absorption rates
- exchange netflow
- binary CDD
- net realized PnL
- PL ratio
- mining pulse
- hash ribbons
- mining economics
- SOPR
- NVT
- volatility
- Puell multiple
- pro risk
- power law model
- RBN validation endpoints

Current metric modules visible in `scripts/metrics/`:
- `absorption_rates.py`
- `active_addresses.py`
- `address_cohorts.py`
- `binary_cdd.py`
- `cdd_vdd.py`
- `cointime.py`
- `cost_basis.py`
- `exchange_netflow.py`
- `fractal_dimension.py`
- `hodl_waves.py`
- `mining_economics.py`
- `monte_carlo_fusion.py`
- `mvrv_variants.py`
- `net_realized_pnl.py`
- `nupl.py`
- `nvt.py`
- `pl_ratio.py`
- `power_law.py`
- `pro_risk.py`
- `puell_multiple.py`
- `realized_metrics.py`
- `reserve_risk.py`
- `revived_supply.py`
- `sell_side_risk.py`
- `sopr.py`
- `supply_profit_loss.py`
- `symbolic_dynamics.py`
- `tx_volume.py`
- `urpd.py`
- `utxo_lifecycle.py`
- `volatility.py`
- `wallet_waves.py`
- `wasserstein.py`

## Overlap Analysis

### Strong Overlap with BRK

These areas are heavily overlapped by BRK and should be treated as prime candidates for upstream feature consumption or cross-validation:
- realized price and realized cap
- MVRV and related valuation families
- NUPL
- SOPR and spending metrics
- liveliness and cointime-adjacent metrics
- cohort-based analytics
- broad historical on-chain metric surfaces

### Partial Overlap with BRK

These areas may overlap conceptually but need methodology or bucket validation before treating BRK as a drop-in substitute:
- wallet waves and cohort boundaries
- address cohort definitions
- some market valuation families where normalization differs
- any metric depending on repo-local DuckDB lifecycle tables or custom thresholds

### UTXOracle-Unique or Repo-Specific Features

These should remain owned by this repository even in a BRK-centered live topology:
- canonical on-chain oracle price engine
- custom DuckDB research workflows
- UTXO lifecycle tables and custom lifecycle-derived analytics
- whale detection pipeline and alerting
- pro risk implementation and custom regime logic
- Monte Carlo and multi-signal fusion logic
- Hyperliquid comparison and downstream live snapshot normalization

### Upstream-Only or Infra-Specific Areas

These should remain tied to their respective upstreams:
- `electrs`: low-level confirmed-chain indexing and raw query workflows
- `mempool-api`: live mempool feed, fee estimates, mining stats, exchange BTC/USD updater
- `Hyperliquid`: oracle price, mark price, funding, open interest context

## Correct Live Ownership per Capability

| Capability | Owner in live production |
|-----------|---------------------------|
| Canonical on-chain oracle price | `UTXOracle` |
| Broad on-chain feature surface | `BRK` |
| Raw confirmed-chain lookup and sync support | `electrs` |
| Live mempool feed and exchange price | `mempool-api` |
| Derivatives and external oracle comparison | `Hyperliquid` |
| Stable consumer-facing live API | `UTXOracle` |

## Immediate Documentation Conclusions

1. The repo is no longer accurately described as only `UTXOracle + mempool + electrs`.
2. `BRK` must now be documented as a first-class upstream in the live architecture.
3. `mempool-api` should be documented as broader than whale detection alone.
4. `electrs` should be documented as infrastructure, not as the main analytics surface.
5. Older references to `3001`, `3110`, and `8000` must be treated as legacy until configuration alignment is implemented.

## Immediate Implementation Conclusions

1. Build `UTXOracle Live API` as the stable consumer contract.
2. Source curated overlapping metrics from `BRK` instead of duplicating or re-exposing the full BRK surface.
3. Keep `mempool-api` wired for whale and price feeds.
4. Keep `electrs` available for lifecycle sync and confirmed-chain fallback paths.
5. Add a separate BRK visual validation track for CheckOnChain-style chart parity.
