# Cost Basis Promotion to Production Consumer Service

Date: 2026-04-07
Spec: 052
Phase: 4

## Consumer-Use Statement (T019)
The `cost_basis` signal has been promoted from the local Wave 2 DuckDB execution context to the robust, production-grade QuestDB tier on `:8011`. 

### Admitted Field Subset (T018)
To maintain the strict boundaries set in the Phase 1 freeze, only the highest-signal macro fields have been admitted to the production service. Volumetric/supply breakdown fields have been explicitly omitted to reduce payload bloat.

**Admitted Fields:**
- `total_cost_basis`: Overall market cost basis
- `sth_cost_basis`: Short-Term Holder cost basis
- `lth_cost_basis`: Long-Term Holder cost basis
- `sth_mvrv`: Market Value to Realized Value for Short-Term Holders
- `lth_mvrv`: Market Value to Realized Value for Long-Term Holders
- `sth_supply_btc`: Short-Term Holder supply in BTC
- `lth_supply_btc`: Long-Term Holder supply in BTC
- `current_price_usd`: Evaluation price
- `block_height`: Canonical chain reference
- `timestamp`: Snapshot timestamp
- `confidence`: Data quality indicator

## Serving-Grade Path Decision (T021)
The `cost_basis` slice is materialized daily into QuestDB (`cost_basis_daily` table) rather than being served directly from DuckDB. This ensures zero latency under load and decouples consumer reads from heavy analytical queries.

Operational note: this promotion is only complete when the Wave 1 materializer is actually running in the live environment. The admitted `:8011` cohort/signal/execution path depends on a scheduled materialization pass that reads DuckDB in `read_only` mode and writes serving snapshots into QuestDB.

## Reproducibility Checks (T020)
The metric is perfectly reproducible from the DuckDB `utxo_lifecycle` table:
```sql
-- STH Cost Basis query (155-day cutoff)
SELECT SUM(realized_value_usd) / SUM(btc_value) 
FROM utxo_lifecycle_full 
WHERE is_spent = FALSE AND creation_block > {current_block - 22320} AND btc_value > 0;

-- LTH Cost Basis query
SELECT SUM(realized_value_usd) / SUM(btc_value) 
FROM utxo_lifecycle_full 
WHERE is_spent = FALSE AND creation_block <= {current_block - 22320} AND btc_value > 0;
```
These formulas are executed exactly once during the daily materialization run and served atomically from QuestDB.
