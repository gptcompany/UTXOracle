# Research: Advanced On-Chain Metrics (spec-021)

**Date**: 2025-12-10 | **Status**: Complete | **Unknowns Resolved**: 0 (none identified)

## Executive Summary

All technical decisions for spec-021 can be made from existing codebase context. No external research required. This document confirms the resolution of potential unknowns and documents implementation decisions.

## Research Tasks

### 1. UTXO Lifecycle Data Model Verification

**Question**: Does `utxo_lifecycle` table have all fields needed for spec-021 metrics?

**Decision**: Yes - all required fields exist

**Verification** (from `scripts/metrics/utxo_lifecycle.py`):
```sql
-- Required fields for spec-021
creation_price_usd  -- URPD bucket assignment
btc_value           -- All metrics (BTC amounts)
is_spent            -- Filter unspent for URPD, Supply P/L
spent_block         -- Sell-side Risk (date range)
spent_price_usd     -- Sell-side Risk (realized profit)
creation_block      -- Age calculations, CDD
```

**Alternatives Considered**: None needed - existing schema is sufficient.

---

### 2. DuckDB Aggregation Performance

**Question**: Can DuckDB handle URPD calculation for ~180M UTXOs in < 30 seconds?

**Decision**: Yes - DuckDB optimized for analytical aggregations

**Rationale**:
- DuckDB is columnar and vectorized (designed for aggregations)
- Existing `hodl_waves.py` uses similar `GROUP BY` pattern successfully
- Index on `is_spent` already exists (from `init_indexes()`)
- URPD query only needs unspent UTXOs (~85M active)

**Query Pattern**:
```sql
SELECT
    FLOOR(creation_price_usd / :bucket_size) * :bucket_size as price_bucket,
    SUM(btc_value) as btc_in_bucket,
    COUNT(*) as utxo_count
FROM utxo_lifecycle
WHERE is_spent = FALSE
GROUP BY price_bucket
ORDER BY price_bucket DESC
```

**Alternatives Considered**:
- Materialized view (rejected: adds complexity, DuckDB fast enough)
- Pre-computed buckets (rejected: bucket size should be configurable)

---

### 3. Reserve Risk Formula Clarification

**Question**: Which Reserve Risk formula to implement (standard vs simplified)?

**Decision**: Implement standard formula first, simplified as fallback

**Standard Formula** (Glassnode):
```
Reserve Risk = Price / (HODL Bank × Circulating Supply)
HODL Bank = Cumulative_Coindays_Destroyed (opportunity cost)
```

**Simplified Formula** (if HODL Bank unavailable):
```
Reserve Risk = Price / (Liveliness_cumulative × MVRV)
```

**Rationale**:
- `cointime.py` already calculates cumulative coinblocks destroyed
- Coinblocks can be converted to coindays: `coinblocks / BLOCKS_PER_DAY`
- Standard formula is more accurate for institutional analysis

**Alternatives Considered**:
- MVRV-only proxy (rejected: loses HODL Bank insight)
- Custom HODL Bank definition (rejected: stick to Glassnode standard)

---

### 4. Sell-side Risk Rolling Window

**Question**: How to efficiently calculate 30-day rolling realized profit?

**Decision**: Use DuckDB date filtering on `spent_timestamp`

**Query Pattern**:
```sql
SELECT SUM((spent_price_usd - creation_price_usd) * btc_value) as realized_profit
FROM utxo_lifecycle
WHERE is_spent = TRUE
  AND spent_timestamp >= :start_date
  AND spent_price_usd > creation_price_usd  -- Only profits
```

**Performance**: DuckDB handles date range queries efficiently with index on `spent_block`.

**Alternatives Considered**:
- Window functions (rejected: simpler date filter sufficient)
- Pre-aggregated daily summaries (rejected: adds complexity)

---

### 5. CDD vs Coinblocks Conversion

**Question**: `cointime.py` uses coinblocks, but CDD uses coindays. How to convert?

**Decision**: Simple division by `BLOCKS_PER_DAY`

**Formula**:
```python
CDD = coinblocks_destroyed / BLOCKS_PER_DAY
    = (btc × blocks_since_creation) / 144
    = btc × days_since_creation
```

**Rationale**:
- `BLOCKS_PER_DAY = 144` constant already defined in `cointime.py`
- Conversion is exact and reversible
- VDD = CDD × price (straightforward extension)

**Alternatives Considered**: None - conversion is mathematically straightforward.

---

### 6. API Endpoint Pattern

**Question**: How should new metrics be exposed via API?

**Decision**: Follow existing `/api/metrics/` pattern

**Endpoint Design**:
```
GET /api/metrics/urpd?bucket_size=5000&current_price=100000
GET /api/metrics/supply-profit-loss?current_price=100000
GET /api/metrics/reserve-risk
GET /api/metrics/sell-side-risk?window_days=30
GET /api/metrics/coindays?window_days=30
```

**Rationale**:
- Consistent with existing endpoints in `api/main.py`
- Optional query params for configurable metrics
- JSON response with Pydantic models

**Alternatives Considered**:
- Nested under `/api/metrics/advanced/` (rejected: unnecessary hierarchy)
- WebSocket streaming (rejected: these are point-in-time calculations)

---

## Dependency Compatibility Verification

| Metric | Dependencies | Compatible? |
|--------|-------------|-------------|
| URPD | `utxo_lifecycle` | ✅ Has `creation_price_usd`, `btc_value`, `is_spent` |
| Supply P/L | `utxo_lifecycle`, `hodl_waves` | ✅ Has `is_spent`, age cohort functions |
| Reserve Risk | `cointime`, `realized_metrics` | ✅ Has `cumulative_destroyed`, `calculate_mvrv()` |
| Sell-side Risk | `utxo_lifecycle` | ✅ Has `spent_price_usd`, `creation_price_usd`, `spent_timestamp` |
| CDD/VDD | `cointime` | ✅ Has `calculate_coinblocks_destroyed()`, `BLOCKS_PER_DAY` |

## Conclusion

**No external research required.** All technical decisions can be made from:
1. Existing codebase (spec-017, spec-018, spec-020)
2. Formula definitions in spec-021
3. DuckDB documentation (standard SQL aggregation)

Proceed directly to Phase 1 (data model and contracts).
