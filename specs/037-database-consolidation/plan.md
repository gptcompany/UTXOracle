# spec-037: Implementation Plan

## Execution Order

```
Phase 1: Database Consolidation (Day 1)
├── T001: Migration script
│   ├── Backup all databases
│   ├── Rename utxo_lifecycle.duckdb → utxoracle.duckdb
│   ├── ATTACH and copy from utxoracle_cache.db
│   └── Create empty metric tables
│
├── T002: Config module
│   ├── Create scripts/config.py
│   └── Update ~30 scripts with hardcoded paths
│
└── T006: Cleanup (partial)
    └── Update symlinks

Phase 2: Metric Pipeline (Day 2)
├── T003: Daily metric calculator
│   ├── calculate_daily_sopr()
│   ├── calculate_daily_nupl()
│   ├── calculate_daily_mvrv()
│   └── calculate_cointime_daily()
│
└── T004: Backfill 30 days
    └── Run pipeline for 2024-11-27 to 2024-12-27

Phase 3: Validation Fix (Day 3)
├── T005: Update MetricLoader
│   ├── Point to new tables
│   ├── Add on-demand fallback
│   └── Test against RBN
│
└── T006: Final cleanup
    ├── Remove orphaned files
    └── Update documentation
```

## Quick Win: Immediate Validation Fix

Before full migration, we can make validation work by:

1. **Update MetricLoader** to calculate on-demand from `utxo_lifecycle.duckdb`
2. No migration needed, just code change
3. Validation will use real calculated data

```python
# Quick fix in metric_loader.py
def _load_metric_on_demand(self, metric_id, start_date, end_date):
    """Calculate metric on-demand from utxo_lifecycle."""
    utxo_conn = duckdb.connect("data/utxo_lifecycle.duckdb", read_only=True)

    if metric_id == "mvrv_z":
        from scripts.metrics.realized_metrics import calculate_mvrv
        # ... calculate and return
```

## Dependencies

```
T001 (migration) ──┬──▶ T002 (config)
                   │
                   └──▶ T003 (pipeline) ──▶ T004 (backfill)
                                                   │
                                                   ▼
                                           T005 (MetricLoader)
                                                   │
                                                   ▼
                                           T006 (cleanup)
```

## Estimated Effort

| Task | Effort | Notes |
|------|--------|-------|
| T001 | 2h | Careful migration with backup |
| T002 | 1h | Find/replace ~30 files |
| T003 | 3h | Metric calculations |
| T004 | 1h | Run backfill (mostly wait time) |
| T005 | 2h | MetricLoader refactor |
| T006 | 1h | Cleanup and docs |
| **Total** | **~10h** | 2-3 days with testing |
