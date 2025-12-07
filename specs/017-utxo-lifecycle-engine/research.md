# Research: UTXO Lifecycle Engine

**Spec**: spec-017
**Date**: 2025-12-06

---

## R1: Storage Strategy

### Question
How to efficiently store UTXO lifecycle data?

### Options

| Option | Storage | Query Speed | Complexity |
|--------|---------|-------------|------------|
| DuckDB | ~5GB/6mo | Fast (indexed) | Low |
| PostgreSQL | ~8GB/6mo | Fast | Medium |
| SQLite | ~5GB/6mo | Medium | Low |
| LevelDB | ~3GB/6mo | Fast (key) | Medium |

### Decision
**DuckDB** with 6-month retention and automatic pruning

### Rationale
- Already used by UTXOracle
- Columnar storage efficient for analytics
- Easy SQL queries
- No separate database server

---

## R2: Sync Approach

### Question
How to handle initial sync and incremental updates?

### Options

1. **Full rescan**: Process entire blockchain from genesis
   - Time: 2-3 months
   - Complete accuracy
   - High resource usage

2. **Recent history only**: Start from 6 months ago
   - Time: ~2 weeks
   - Sufficient for STH metrics
   - Lower resource usage

3. **Incremental from checkpoint**: Resume from last processed block
   - Time: Minutes per day
   - Production-ready
   - Requires state tracking

### Decision
**Option 2 for initial sync** + **Option 3 for ongoing**

### Rationale
- 6 months covers all STH metrics (< 155 days)
- Incremental keeps system current
- Checkpoint enables crash recovery

---

## R3: UTXO Identification

### Question
How to uniquely identify UTXOs?

### Decision
Use `outpoint` format: `{txid}:{vout_index}`

### Rationale
- Bitcoin standard
- Globally unique
- Efficient string key
- Easy to parse

---

## R4: Age Cohort Definitions

### Question
What age cohorts to track?

### Decision
10 cohorts following Glassnode standard:

```python
AGE_COHORTS = [
    ("<1d", 0, 1),
    ("1d-1w", 1, 7),
    ("1w-1m", 7, 30),
    ("1m-3m", 30, 90),
    ("3m-6m", 90, 180),
    ("6m-1y", 180, 365),
    ("1y-2y", 365, 730),
    ("2y-3y", 730, 1095),
    ("3y-5y", 1095, 1825),
    (">5y", 1825, float("inf")),
]
```

### Rationale
- Industry standard
- Enables CheckOnChain comparison
- Covers full HODL Waves spectrum

---

## R5: Realized Metrics Formulas

### Realized Cap
```
Realized Cap = Σ(UTXO_value × creation_price_usd)
```

### MVRV
```
MVRV = Market Cap / Realized Cap
```

### NUPL
```
NUPL = (Market Cap - Realized Cap) / Market Cap
```

### Decision
Implement all three with rolling updates

---

## R6: Pruning Strategy

### Question
How to manage storage growth?

### Decision
- Prune spent UTXOs older than retention period
- Keep unspent UTXOs indefinitely
- Run pruning daily during low-activity hours

### Configuration
```bash
UTXO_RETENTION_DAYS=180
UTXO_PRUNING_ENABLED=true
UTXO_PRUNE_HOUR=4  # 4 AM local time
```

---

## Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | DuckDB | Already used, analytics-friendly |
| Sync | 6mo initial + incremental | Balances completeness and speed |
| ID format | outpoint (txid:vout) | Bitcoin standard |
| Cohorts | 10 Glassnode-standard | Industry compatibility |
| Pruning | Daily, spent only | Manages growth |
