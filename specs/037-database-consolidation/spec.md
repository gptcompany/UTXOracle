# spec-037: Database Consolidation & Metric Pipeline

> **Status**: DRAFT
> **Priority**: CRITICAL
> **Effort**: Medium (2-3 days)
> **Created**: 2024-12-27

## Problem Statement

UTXOracle has accumulated **database proliferation debt** causing:

1. **Validation failures**: MetricLoader falls back to golden data (false positives)
2. **Empty metric tables**: Calculation functions exist but no persistence pipeline
3. **Path confusion**: 4+ database files with hardcoded absolute paths
4. **Schema duplication**: Same tables in multiple databases

### Current Chaos

```
/media/sam/2TB-NVMe/prod/apps/utxoracle/data/
├── utxo_lifecycle.duckdb → SYMLINK to 1TB
└── utxoracle_cache.db (611 MB) ← Production

/media/sam/1TB/UTXOracle/data/
├── utxo_lifecycle.duckdb (57 GB) ← Actual UTXO data
├── utxoracle_cache.db (12 KB) ← DUPLICATE (nearly empty!)
├── utxoracle.duckdb (320 MB) ← ORPHANED
└── mempool_predictions.db (274 KB)
```

### Impact

- `MetricLoader` looks for `sopr_metrics`, `nupl_metrics`, `realized_metrics` tables
- These tables **DO NOT EXIST** in any database
- Validation compares golden data to itself → r=1.0, MAPE=0% (meaningless)
- 2.3M spent UTXOs bootstrapped but metrics never calculated/persisted

## Goals

1. **Single database**: Consolidate to `data/utxoracle.duckdb`
2. **Environment config**: `UTXORACLE_DB_PATH` for all scripts
3. **Metric pipeline**: Batch calculation from `utxo_lifecycle` → metric tables
4. **Working validation**: Real metrics compared against RBN

## Non-Goals

- Changing calculation algorithms (spec-016, spec-018)
- Adding new metrics
- Production deployment automation

## Design

### Phase 1: Database Consolidation

#### 1.1 Target Schema

Single database `data/utxoracle.duckdb` with tables:

```sql
-- Core UTXO data (existing, migrate from utxo_lifecycle.duckdb)
utxo_lifecycle          -- 164M rows, UTXO creation/spend data
address_clusters        -- 55M rows, address clustering
daily_prices            -- 5.4K rows, historical prices
block_heights           -- 928K rows, block metadata

-- Metric tables (NEW - to be populated by pipeline)
sopr_daily              -- Daily SOPR values
nupl_daily              -- Daily NUPL values
realized_cap_daily      -- Daily Realized Cap
mvrv_daily              -- Daily MVRV/MVRV-Z
cointime_daily          -- Daily Cointime metrics (liveliness, AVIV)

-- Cache/operational (migrate from utxoracle_cache.db)
price_analysis          -- 744 rows, price comparisons
alert_events            -- 332 rows, alert history
metrics                 -- Monte Carlo fusion results
```

#### 1.2 Migration Script

```python
# scripts/migrations/consolidate_databases.py
def migrate():
    """Migrate all data to single database."""
    target = "data/utxoracle.duckdb"

    # 1. Rename utxo_lifecycle.duckdb → utxoracle.duckdb
    # 2. ATTACH utxoracle_cache.db and copy tables
    # 3. Create new metric tables (empty, ready for pipeline)
    # 4. Update symlink in /media/sam/2TB-NVMe/...
    # 5. Remove orphaned files
```

#### 1.3 Environment Configuration

```python
# scripts/config.py
import os
from pathlib import Path

UTXORACLE_DB_PATH = Path(os.getenv(
    "UTXORACLE_DB_PATH",
    "data/utxoracle.duckdb"
))

def get_connection(read_only: bool = False):
    """Get database connection."""
    import duckdb
    return duckdb.connect(str(UTXORACLE_DB_PATH), read_only=read_only)
```

Update all scripts to use:
```python
from scripts.config import get_connection, UTXORACLE_DB_PATH
```

### Phase 2: Metric Pipeline

#### 2.1 Daily Metric Calculator

```python
# scripts/metrics/calculate_daily_metrics.py
"""
Calculate and persist daily metrics from utxo_lifecycle data.

Usage:
    python -m scripts.metrics.calculate_daily_metrics --date 2024-12-27
    python -m scripts.metrics.calculate_daily_metrics --backfill 30  # Last 30 days
"""

def calculate_daily_metrics(target_date: date, conn) -> dict:
    """Calculate all metrics for a single day."""

    # 1. Get block range for date
    start_block, end_block = get_blocks_for_date(target_date, conn)

    # 2. Calculate Realized Cap (from utxo_lifecycle)
    realized_cap = calculate_realized_cap(conn, end_block)

    # 3. Calculate Market Cap (supply * price)
    supply = get_total_unspent_supply(conn, end_block)
    price = get_price_for_date(target_date, conn)
    market_cap = supply * price

    # 4. Calculate derived metrics
    mvrv = market_cap / realized_cap if realized_cap > 0 else None
    nupl = (market_cap - realized_cap) / market_cap if market_cap > 0 else None

    # 5. Calculate SOPR (requires spent UTXOs with prices)
    sopr = calculate_daily_sopr(conn, start_block, end_block)

    # 6. Calculate Cointime (liveliness, AVIV)
    cointime = calculate_cointime_metrics(conn, end_block)

    return {
        "date": target_date,
        "realized_cap": realized_cap,
        "market_cap": market_cap,
        "mvrv": mvrv,
        "nupl": nupl,
        "sopr": sopr,
        **cointime
    }

def persist_metrics(metrics: dict, conn):
    """Persist calculated metrics to respective tables."""
    # INSERT OR REPLACE into sopr_daily, nupl_daily, etc.
```

#### 2.2 Integration with daily_analysis.py

```python
# In daily_analysis.py main():

# After calculating metrics...
if PERSIST_METRICS:
    from scripts.metrics.calculate_daily_metrics import persist_metrics
    persist_metrics(calculated_metrics, conn)
```

### Phase 3: Update MetricLoader

```python
# scripts/integrations/metric_loader.py

METRIC_CONFIG = {
    "mvrv_z": {
        "table": "mvrv_daily",      # Changed from cointime_metrics
        "column": "mvrv_z",
        "calculate_fn": calculate_mvrv_z,  # NEW: on-demand fallback
    },
    "sopr": {
        "table": "sopr_daily",      # Changed from sopr_metrics
        "column": "sopr",
        "calculate_fn": calculate_daily_sopr,
    },
    # ... etc
}

def _load_from_duckdb(self, metric_id, start_date, end_date):
    """Load from DB, calculate on-demand if table empty."""
    config = METRIC_CONFIG[metric_id]

    # Try loading from table
    result = self._query_table(config["table"], config["column"], ...)

    if result.empty and config.get("calculate_fn"):
        # Calculate on-demand from utxo_lifecycle
        result = self._calculate_on_demand(config["calculate_fn"], ...)

    return result
```

## Tasks

### T001: Create migration script
- [ ] `scripts/migrations/consolidate_databases.py`
- [ ] Backup existing databases
- [ ] Migrate UTXO data
- [ ] Migrate cache data
- [ ] Create new metric tables

### T002: Create config module
- [ ] `scripts/config.py` with `UTXORACLE_DB_PATH`
- [ ] `get_connection()` helper
- [ ] Update all scripts to use config

### T003: Create metric pipeline
- [ ] `scripts/metrics/calculate_daily_metrics.py`
- [ ] SOPR daily calculation
- [ ] NUPL daily calculation
- [ ] MVRV daily calculation
- [ ] Cointime daily calculation

### T004: Backfill metrics
- [ ] Run pipeline for last 30 days
- [ ] Verify data consistency

### T005: Update MetricLoader
- [ ] Point to new table names
- [ ] Add on-demand calculation fallback
- [ ] Test validation with real data

### T006: Cleanup
- [ ] Remove orphaned `utxoracle.duckdb`
- [ ] Remove duplicate `utxoracle_cache.db`
- [ ] Update symlinks
- [ ] Update ARCHITECTURE.md

## Success Criteria

1. **Single database**: Only `data/utxoracle.duckdb` exists
2. **No hardcoded paths**: All scripts use `UTXORACLE_DB_PATH`
3. **Metrics populated**: `sopr_daily`, `nupl_daily`, etc. have data
4. **Validation works**: RBN comparison shows real correlation (not 1.0)
5. **Tests pass**: All existing tests continue to work

## Risks

| Risk | Mitigation |
|------|------------|
| Data loss during migration | Full backup before migration |
| Script breakage | Grep for all DB paths, update systematically |
| Performance regression | Benchmark before/after |
| Symlink issues | Test on both paths after migration |

## References

- [ARCHITECTURE.md - Database Architecture Debt section](../docs/ARCHITECTURE.md)
- [spec-016: SOPR calculation](./016-sopr)
- [spec-017: UTXO Lifecycle](./017-utxo-lifecycle)
- [spec-018: Cointime Economics](./018-cointime-economics)
- [spec-035: RBN API Integration](./035-rbn-api-integration)
