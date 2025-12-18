# On-Chain Metrics Gap Analysis

**Date**: 2025-12-17
**Source**: CheckOnChain.com vs UTXOracle implemented specs
**Scope**: On-chain metrics only (excluding ETF, technical indicators)

---

## Current Implementation Status

### ✅ IMPLEMENTED (18 metric categories)

| Category | Metric | Module | Spec |
|----------|--------|--------|------|
| **Supply** | HODL Waves | `hodl_waves.py` | spec-017 |
| | Revived Supply | `revived_supply.py` | spec-024 |
| | Supply Profit/Loss | `supply_profit_loss.py` | spec-021 |
| | Active/Vaulted Supply | `cointime.py` | spec-018 |
| **Valuation** | Realized Cap | `realized_metrics.py` | spec-007 |
| | MVRV / MVRV-Z | `realized_metrics.py` | spec-020 |
| | STH/LTH-MVRV | `cost_basis.py` | spec-023 |
| | NUPL (with zones) | `nupl.py` | spec-022 |
| | AVIV Ratio | `cointime.py` | spec-018 |
| **Lifespan** | CDD/VDD | `cdd_vdd.py` | spec-021 |
| | Reserve Risk | `reserve_risk.py` | spec-021 |
| | Liveliness/Vaultedness | `cointime.py` | spec-018 |
| **Profitability** | SOPR (STH/LTH) | `sopr.py` | spec-016 |
| | Sell-side Risk | `sell_side_risk.py` | spec-021 |
| | URPD | `urpd.py` | spec-021 |
| | Cost Basis Cohorts | `cost_basis.py` | spec-023 |
| **Network** | Active Addresses | `active_addresses.py` | spec-007 |
| | TX Volume USD | `tx_volume.py` | spec-007 |

---

## ❌ MISSING METRICS (Priority Ranked)

### Tier 1: High Value, Low Complexity (Recommended)

These leverage existing UTXO lifecycle data and require minimal new infrastructure.

#### 1. **Wallet Waves** (Supply by Wallet Size)
- **What**: Supply distribution across wallet size bands (shrimp, crab, fish, shark, whale)
- **Why**: Reveals retail vs institutional accumulation patterns
- **Complexity**: Medium (requires address balance aggregation)
- **Dependencies**: Address clustering (spec-013), UTXO lifecycle
- **CheckOnChain**: ✅ Has this
```
Bands: <1 BTC, 1-10, 10-100, 100-1000, 1000-10000, >10000 BTC
```

#### 2. **MVRV Momentum**
- **What**: Rate of change in MVRV ratio (7d, 30d deltas)
- **Why**: Detects acceleration in profit-taking or accumulation
- **Complexity**: Low (derivative of existing MVRV)
- **Dependencies**: MVRV (spec-020)
- **CheckOnChain**: ✅ Has this

#### 3. **Net Realized Profit/Loss**
- **What**: Aggregate realized gains/losses from spent UTXOs
- **Why**: Shows actual capital flows, not just paper P/L
- **Complexity**: Low (sum of spent UTXO P/L already calculated)
- **Dependencies**: UTXO lifecycle (spec-017)
- **CheckOnChain**: ✅ Has this

#### 4. **Exchange Flows** (Inflows/Outflows)
- **What**: BTC movement to/from known exchange addresses
- **Why**: Primary indicator of selling pressure vs accumulation
- **Complexity**: Medium (requires exchange address tagging)
- **Dependencies**: Address clustering (spec-013)
- **CheckOnChain**: ✅ Has this
- **Note**: Requires curated exchange address list

#### 5. **Binary CDD Indicator**
- **What**: Statistical significance flag when CDD exceeds N-sigma
- **Why**: Filters noise from CDD, highlights meaningful events
- **Complexity**: Very Low (z-score on existing CDD)
- **Dependencies**: CDD (spec-021)
- **CheckOnChain**: ✅ Has this

---

### Tier 2: Medium Value, Medium Complexity

#### 6. **NVT Price Model**
- **What**: Valuation based on network transaction volume
- **Why**: Alternative fair value estimate
- **Complexity**: Low (Price = Realized Cap / TX Volume × k)
- **Dependencies**: TX Volume (spec-007), Realized Cap
- **CheckOnChain**: ✅ Has this

#### 7. **Absorption Rates**
- **What**: Rate at which wallet cohorts absorb new supply
- **Why**: Measures conviction by holder class
- **Complexity**: Medium (requires time-series of wallet waves)
- **Dependencies**: Wallet Waves (#1 above)
- **CheckOnChain**: ✅ Has this

#### 8. **Active Address Momentum**
- **What**: Growth rate of unique active addresses
- **Why**: Proxy for user adoption acceleration
- **Complexity**: Very Low (delta on existing active addresses)
- **Dependencies**: Active Addresses (spec-007)
- **CheckOnChain**: ✅ Has this

#### 9. **Transaction Count Momentum**
- **What**: Growth rate of confirmed transactions
- **Why**: Network usage acceleration
- **Complexity**: Very Low (available from Bitcoin Core)
- **Dependencies**: None (Bitcoin Core RPC)
- **CheckOnChain**: ✅ Has this

#### 10. **P/L Ratio (Dominance)**
- **What**: Ratio of profit-taking to loss-taking (Realized Profit / Realized Loss)
- **Why**: Shows which side dominates market activity
- **Complexity**: Low (from existing spent UTXO data)
- **Dependencies**: UTXO lifecycle (spec-017)
- **CheckOnChain**: ✅ Has this

---

### Tier 3: Mining Economics (New Domain)

Requires new data sources (mining pools, difficulty API).

#### 11. **Puell Multiple**
- **What**: Daily miner revenue / 365-day MA of revenue
- **Why**: Miner profitability and potential selling pressure
- **Complexity**: Low (coinbase reward × price / MA)
- **Dependencies**: Block reward data (Bitcoin Core)
- **CheckOnChain**: ✅ Has this

#### 12. **Hashrate Ribbons**
- **What**: 30-day MA vs 60-day MA of hashrate
- **Why**: Miner capitulation signal when 30d < 60d
- **Complexity**: Medium (requires hashrate data source)
- **Dependencies**: External API (blockchain.com, mempool.space)
- **CheckOnChain**: ✅ Has this

#### 13. **Difficulty Ribbon**
- **What**: Difficulty adjustment percentage
- **Why**: Network security and miner economics
- **Complexity**: Very Low (Bitcoin Core RPC: getdifficulty)
- **Dependencies**: None
- **CheckOnChain**: ✅ Has this

#### 14. **Mining Pulse**
- **What**: Block interval deviation from 10 minutes
- **Why**: Real-time hashrate proxy
- **Complexity**: Very Low (timestamp delta)
- **Dependencies**: None (block headers)
- **CheckOnChain**: ✅ Has this

---

### Tier 4: Low Priority / Complex

#### 15. **Spent Supply Binary Indicator**
- **What**: Smart money exit flag at cycle peaks
- **Why**: Historical pattern matching for tops
- **Complexity**: High (requires backtested threshold calibration)
- **CheckOnChain**: ✅ Has this

#### 16. **Net Position Change (30/365d)**
- **What**: Capital flows into vaulted supply
- **Why**: Long-term accumulation trend
- **Complexity**: Medium (requires vaulted supply time series)
- **Dependencies**: Cointime (spec-018)
- **CheckOnChain**: ✅ Has this

#### 17. **Fee Revenue (BTC/USD)**
- **What**: Total transaction fees per day
- **Why**: Network demand and miner economics
- **Complexity**: Low (sum of fees from blocks)
- **Dependencies**: Bitcoin Core RPC
- **CheckOnChain**: ✅ Has this

---

## Recommended Implementation Order

Based on value/complexity ratio and existing infrastructure:

### Phase 1: Quick Wins (1-2 days each)
1. **MVRV Momentum** - derivative of spec-020
2. **Binary CDD Indicator** - z-score on spec-021
3. **Active Address Momentum** - delta on spec-007
4. **Net Realized P/L** - aggregate from spec-017
5. **P/L Ratio** - from spent UTXO data

### Phase 2: Medium Effort (3-5 days each)
6. **NVT Price Model** - new valuation metric
7. **Puell Multiple** - mining economics entry point
8. **Transaction Count Momentum** - network activity
9. **Mining Pulse** - block interval analysis
10. **Difficulty Ribbon** - from Bitcoin Core

### Phase 3: Infrastructure Required (1-2 weeks)
11. **Wallet Waves** - requires address aggregation
12. **Exchange Flows** - requires exchange address DB
13. **Hashrate Ribbons** - requires external API
14. **Absorption Rates** - requires Wallet Waves first

---

## Data Source Requirements

| Metric | Data Source | Available |
|--------|-------------|-----------|
| MVRV Momentum | DuckDB (existing) | ✅ |
| Binary CDD | DuckDB (existing) | ✅ |
| Net Realized P/L | DuckDB (existing) | ✅ |
| NVT Price Model | DuckDB (existing) | ✅ |
| Puell Multiple | Bitcoin Core RPC | ✅ |
| Mining Pulse | Bitcoin Core RPC | ✅ |
| Wallet Waves | Address clustering | ⚠️ Partial |
| Exchange Flows | External DB needed | ❌ |
| Hashrate | External API needed | ❌ |

---

## Summary

- **Implemented**: 18 metric categories
- **Missing**: 17 metric categories
- **Quick Wins**: 5 metrics (low effort, high value)
- **New Domain**: Mining economics (4 metrics)
- **Infrastructure Gap**: Exchange address database

**Recommendation**: Start with Phase 1 (MVRV Momentum, Binary CDD, Net Realized P/L) as they require zero new infrastructure and provide immediate value.
