# Research: Wallet Waves & Absorption Rates

**Date**: 2025-12-17
**Spec**: spec-025

## 1. Data Availability

### Decision: Use existing `utxo_lifecycle_full` VIEW
**Rationale**: VIEW already contains `address` column from Tier 1 chainstate import.

**Verification**:
```sql
SELECT address, btc_value, is_spent FROM utxo_lifecycle_full LIMIT 1;
```

### VIEW Schema (relevant columns)
| Column | Type | Source |
|--------|------|--------|
| `address` | VARCHAR | chainstate CSV (decoded scriptPubKey) |
| `btc_value` | DOUBLE | computed (amount / 1e8) |
| `is_spent` | BOOLEAN | tracking column |
| `creation_block` | INTEGER | chainstate CSV |

**Alternatives Considered**:
- Create separate address_balances materialized view → Rejected (adds complexity)
- Store pre-aggregated snapshots → Rejected (YAGNI - can add later if perf issue)

## 2. Aggregation Strategy

### Decision: Real-time aggregation with DuckDB
**Rationale**: DuckDB is OLAP-optimized, handles ~50M address aggregation efficiently.

### Query Pattern
```sql
-- Step 1: Aggregate balance per address
WITH address_balances AS (
    SELECT
        address,
        SUM(btc_value) AS balance
    FROM utxo_lifecycle_full
    WHERE is_spent = FALSE AND address IS NOT NULL
    GROUP BY address
    HAVING balance > 0
)
-- Step 2: Aggregate by wallet band
SELECT
    CASE
        WHEN balance < 1 THEN 'shrimp'
        WHEN balance < 10 THEN 'crab'
        WHEN balance < 100 THEN 'fish'
        WHEN balance < 1000 THEN 'shark'
        WHEN balance < 10000 THEN 'whale'
        ELSE 'humpback'
    END AS band,
    COUNT(*) AS address_count,
    SUM(balance) AS total_btc
FROM address_balances
GROUP BY band;
```

**Alternatives Considered**:
- Pre-compute daily snapshots → Rejected (adds maintenance, YAGNI)
- Use Redis cache → Rejected (already have DuckDB caching)

## 3. Wallet Band Thresholds

### Decision: Standard industry thresholds (Glassnode/IntoTheBlock aligned)
**Rationale**: Enables comparison with external data sources.

| Band | Name | Range | Rationale |
|------|------|-------|-----------|
| 1 | Shrimp | < 1 BTC | Sub-retail, casual holders |
| 2 | Crab | 1-10 BTC | Retail accumulation target |
| 3 | Fish | 10-100 BTC | High net worth individuals |
| 4 | Shark | 100-1,000 BTC | Small institutions, funds |
| 5 | Whale | 1,000-10,000 BTC | Major institutions |
| 6 | Humpback | > 10,000 BTC | Exchanges, ETF custodians |

**Alternatives Considered**:
- Logarithmic bands (0.1, 1, 10, 100...) → Rejected (less intuitive)
- More granular bands (8-10) → Rejected (YAGNI, adds complexity)

## 4. Absorption Rate Calculation

### Decision: Delta-based calculation with mined supply normalization
**Rationale**: Shows how much of new supply each cohort absorbs.

### Formula
```
absorption_rate = (band_supply_t - band_supply_t-n) / new_supply_mined
new_supply_mined = 6.25 BTC/block * 144 blocks/day * n days
```

### Implementation Approach
- Requires two snapshots: current and t-n
- Store snapshots in memory (no persistence needed for MVP)
- If historical data unavailable, return `null` for absorption rates

**Alternatives Considered**:
- Store daily snapshots in DuckDB → Rejected for MVP (can add later)
- Use block-based deltas → Rejected (day-based more intuitive)

## 5. Performance Optimization

### Decision: Single-pass aggregation with index hints
**Rationale**: DuckDB optimizes CTE automatically.

### Expected Performance
- Address aggregation: ~2-3 seconds (50M addresses)
- Band aggregation: <100ms (6 rows)
- Total: <5 seconds

### Index Requirements
- Existing `idx_utxo_address` on address column (if not exists, create)

**Verification**:
```sql
-- Check index existence
SELECT * FROM duckdb_indexes() WHERE table_name = 'utxo_lifecycle';
```

## 6. Edge Cases

### NULL Addresses
- Some UTXOs have no decodable address (OP_RETURN, non-standard scripts)
- **Decision**: Exclude from wallet waves (WHERE address IS NOT NULL)
- Track as separate "unclassified" category if needed later

### Dust UTXOs
- Many addresses have < 546 satoshis (dust limit)
- **Decision**: Include in shrimp band (no dust filter)
- Rationale: Dust removal changes totals, harder to verify

### Exchange Addresses
- Exchanges inflate whale/humpback bands
- **Decision**: Note in API response, defer filtering to spec-026
- Rationale: Exchange address database not available yet

## 7. API Design

### Decision: Follow existing metric endpoint patterns

**Endpoints**:
```
GET /api/metrics/wallet-waves
GET /api/metrics/wallet-waves/history?days=30
GET /api/metrics/absorption-rates?window=30d
```

**Response Format** (wallet-waves):
```json
{
    "timestamp": "2025-12-17T12:00:00Z",
    "block_height": 876543,
    "total_supply_btc": 19700000.0,
    "bands": [
        {"name": "shrimp", "supply_btc": 1234567.89, "supply_pct": 6.27, "address_count": 45000000},
        {"name": "crab", "supply_btc": 2345678.90, "supply_pct": 11.91, "address_count": 2500000},
        ...
    ],
    "retail_supply_pct": 25.5,
    "institutional_supply_pct": 74.5,
    "confidence": 0.85
}
```

## 8. Summary of Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Data source | utxo_lifecycle_full VIEW | Existing, has address column |
| Aggregation | Real-time DuckDB query | OLAP-optimized, no new tables |
| Thresholds | Standard 6-band (Glassnode-aligned) | Industry comparable |
| Absorption | Delta-based, normalized to mined supply | Shows cohort conviction |
| Performance | Single-pass CTE, <5s target | DuckDB handles 50M addresses |
| Edge cases | Exclude NULL addresses, include dust | Simple, verifiable |
| API | Follow existing patterns | UX consistency (Principle III) |
