# CLI Contract: `calculate_daily_metrics`

**Date**: 2026-06-05
**Spec**: [spec.md](../spec.md)
**Plan**: [plan.md](../plan.md)
**Entrypoint**: `uv run python -m scripts.metrics.calculate_daily_metrics`

## Flags

| Flag | Type | Default | Owned by | Effect |
|---|---|---|---|---|
| `--date YYYY-MM-DD` | string | (yesterday) | pre-spec-062 | Single-date run for the named date. |
| `--backfill N` | int | (none) | pre-spec-062 | Run for the last N days ending at `--end-date` or yesterday. |
| `--end-date YYYY-MM-DD` | string | (yesterday) | pre-spec-062 | Upper bound for `--backfill`. |
| `--recalculate` | bool | False | pre-spec-062 | Recalculate every date present in `daily_prices`. |
| `--dry-run` | bool | False | pre-spec-062 | Compute but do not persist. |
| `--db-path PATH` | string | `data/utxoracle.duckdb` | pre-spec-062 | DuckDB file to use for the legacy branch. Ignored when `duckdb_free=True`. |
| `--questdb-only` | bool | False | spec-061 | Skip the DuckDB persist path; only write to QuestDB daily tables. Opens DuckDB read-only when used alone. |
| `--questdb-reads` | bool | False | **spec-062** | Read source tables (`utxo_lifecycle`, `utxo_snapshots`) from QuestDB instead of DuckDB. |

## Flag combinations

| Combination | Reads from | Writes to | DuckDB opened? |
|---|---|---|---|
| (no flags) | DuckDB | DuckDB + QuestDB (dual-write per spec-061) | yes (read-write) |
| `--questdb-only` | DuckDB (read-only) | QuestDB only | yes (read-only) |
| `--questdb-reads` | QuestDB | DuckDB + QuestDB | yes (read-write, for the write path) |
| `--questdb-reads --questdb-only` | QuestDB | QuestDB only | **NO — `duckdb_free=True` path** |
| `--dry-run` | DuckDB | nothing | yes (read-only) |
| `--questdb-reads --dry-run` | QuestDB | nothing | yes (read-only — to be closed in follow-up; not a spec-062 regression) |

The `--questdb-reads --questdb-only` combination is the production target for the systemd timer. It is the only combination that satisfies SC-002 (zero DuckDB file holders).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — all requested dates produced and persisted (or computed in dry-run). |
| non-zero | Python exception propagated. Includes: QuestDB unreachable (FR-006), missing `block_heights` row for date, missing `daily_prices` row for date, any unhandled exception in calculation. |

The script does NOT use distinct numeric exit codes per error class. The structured ERROR log on stderr/journal is the authoritative source for failure type. Discord webhook (FR-012) carries a one-line summary.

## stdout / stderr surface

**stdout / journal (INFO)**:
```
2026-06-05 00:36:25 - INFO - Calculating metrics for 2026-06-04...
2026-06-05 00:36:50 - INFO -   Realized Cap: $1.047T, MVRV: 1.631
2026-06-05 00:36:51 - INFO - QuestDB-only metrics mirrored for 2026-06-04
2026-06-05 00:36:51 - INFO - Metrics persisted for 2026-06-04
```

**stderr / journal (ERROR on failure, FR-011)**:
```
2026-06-05 00:36:25 - ERROR - Aggregator failed for 2026-06-04
Traceback (most recent call last):
  ...
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Discord webhook payload on failure (FR-012)**:
```json
{
  "content": "🚨 UTXOracle aggregator failed for 2026-06-04: OperationalError — could not connect to QuestDB on :8812"
}
```

No webhook is sent on success.

## Observability invariants (FR-011 / FR-012)

| Event | INFO log | ERROR log | Discord webhook |
|---|---|---|---|
| Successful single-date run | yes | no | no |
| Failed single-date run | (initial INFO may exist) | yes (with traceback) | yes (one-line) |
| Successful backfill range | yes per date | no | no |
| Failed date inside backfill | yes for prior dates | yes for failing date | yes |
| Dry-run | yes (computed values) | only on calc failure | only on calc failure |

## Daily-table write contract (consumed by spec-061 health endpoint)

Each successful single-date run MUST write at most one row per target table per `ts`:

| Table | Required columns written | DEDUP key |
|---|---|---|
| `mvrv_daily` | `ts`, `mvrv`, `mvrv_z`, `market_cap`, `realized_cap` | `ts` |
| `nupl_daily` | `ts`, `nupl`, `market_cap`, `realized_cap` | `ts` |
| `realized_cap_daily` | `ts`, `realized_cap` | `ts` |

`mvrv_z_rbn` is NOT a required column at the write contract level — when the snapshot history is too short, the field is absent from the payload (spec FR-005). The consumer-facing `mvrv_daily` schema either has the column nullable, or the writer omits it from the INSERT — both are acceptable; the contract is "absent, not fabricated".

## Concurrency contract (FR-013)

Two concurrent invocations against the same `--date` MUST both exit 0 and the QuestDB `DEDUP UPSERT KEYS(ts)` constraint collapses the two writes to a single row. The producers MUST be free to retry, run side-by-side, or be re-invoked manually during a timer fire without coordination.

This invariant holds only while the calculation is deterministic in `(target_date, as_of_block)`. If a future change introduces non-deterministic inputs, this contract is voided and a follow-up spec must replace it (see spec Clarifications Q2).
