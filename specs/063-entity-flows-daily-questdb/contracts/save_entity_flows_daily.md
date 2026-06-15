# Contract: `save_entity_flows_daily` Repository Method

**Date**: 2026-06-15
**Spec**: [../spec.md](../spec.md)
**Plan**: [../plan.md](../plan.md)
**Owner**: spec-063
**Module**: `api/questdb_repository.py`

## Signature

```python
from datetime import date as _date

def save_entity_flows_daily(
    *,
    entity_id: str,
    date: _date,
    inflow_btc: float,
    outflow_btc: float,
    netflow_btc: float,
    is_exchange: bool,
) -> None:
    """Idempotent per (date, entity_id) via QuestDB DEDUP UPSERT KEYS.

    Raises psycopg.Error (or subclasses) on transport / SQL failure.
    Caller MUST wrap in try/except per FR-002 + FR-003.
    """
```

All arguments are keyword-only. This matches the existing `save_mvrv_daily`/`save_nupl_daily`/`save_realized_cap_daily` pattern that spec-061/062 established.

## Idempotency contract

- Re-invoking with the same `(date, entity_id)` and identical other fields is a no-op at the row level (QuestDB DEDUP UPSERT KEYS collapses to a single row).
- Re-invoking with the same `(date, entity_id)` and DIFFERENT other fields overwrites the existing row (UPSERT semantics).
- Concurrent invocations against the same `(date, entity_id)` converge to the last-arriving write deterministically (spec.md FR-006).

## Cast contract

The implementation MUST apply the per-column casts enumerated in [../data-model.md](../data-model.md):

```sql
INSERT INTO entity_flows_daily (entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange, ts)
VALUES (%s, %s, %s, %s, %s, %s, %s)
```

Parameters substituted by psycopg:
- `entity_id`: passed through (string identity → SYMBOL)
- `date`: `datetime.combine(date, datetime.min.time())` (DATE → TIMESTAMP at midnight, treated as UTC; QuestDB designated timestamp is `ts` so partition lookup uses `ts`, not `date`)
- `inflow_btc, outflow_btc, netflow_btc, is_exchange`: passed through
- `ts`: `datetime.utcnow()` at call time (the designated timestamp for partitioning; consumer-facing day key remains `date`)

## Failure modes

| Failure | Raises | Caller behaviour (per FR-002, FR-003) |
|---|---|---|
| QuestDB unreachable | `psycopg.OperationalError` | Log per-row ERROR, increment failure counter, continue with next row, post one aggregated webhook at end of run |
| Schema mismatch (column missing) | `psycopg.errors.UndefinedColumn` or `psycopg.ProgrammingError` | Same as above, but the failure indicates DDL drift — escalate to operator via the webhook |
| Constraint violation (would be impossible given DEDUP semantics) | `psycopg.errors.IntegrityError` | Same — log and continue |
| Type coercion failure (e.g. NaN in DOUBLE) | `psycopg.errors.DataError` | Same — log row contents in ERROR log (no PII present) |

The method MUST NOT swallow exceptions internally. Per-row error isolation lives in the CALLER, not in the save method, so the save method stays single-purpose and testable.

## Lifecycle within `aggregate_flows()`

```python
# Pseudocode for the new dual-write block (full implementation in flow_aggregator.py)
if _should_write_questdb():
    failed_rows = []
    rows = conn.execute(
        "SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange "
        "FROM entity_flows_daily WHERE date = ?", [target_date]
    ).fetchall()
    for row in rows:
        try:
            save_entity_flows_daily(
                entity_id=row[0],
                date=row[1],
                inflow_btc=row[2],
                outflow_btc=row[3],
                netflow_btc=row[4],
                is_exchange=row[5],
            )
            rows_written_questdb += 1
        except psycopg.Error as exc:
            failed_rows.append((row[0], row[1], type(exc).__name__))
            logger.error("entity_flows_daily QuestDB save failed: entity_id=%s date=%s exc=%s",
                         row[0], row[1], exc, exc_info=True)
    if failed_rows:
        _post_aggregated_webhook(target_date, failed_rows)
```

The caller block:
1. Reads back the DuckDB-aggregated rows for the target date.
2. Iterates and calls `save_entity_flows_daily` per row.
3. Catches `psycopg.Error` per row, logs ERROR, accumulates failure metadata.
4. At end-of-run, posts exactly one aggregated webhook if `failed_rows` is non-empty.

## Test guards (FR-008, FR-009)

`tests/test_flow_aggregator_questdb.py` MUST include:

1. **Deterministic payload guard (guard b)**: patch `save_entity_flows_daily` to record calls, invoke `aggregate_flows()`, assert each call's keyword args match exactly the DuckDB row that `aggregate_flows()` produced for the same `(entity_id, date)`.
2. **Failure isolation guard (guard c)**: patch `save_entity_flows_daily` to raise `psycopg.OperationalError`, invoke `aggregate_flows()`, assert: (a) the DuckDB row count for the target date matches what the run would have produced without spec-063, (b) the DuckDB transaction was committed, (c) the run did NOT raise upward.
3. **Save method import guard (guard e)**: `tests/test_flow_aggregator_questdb.py::test_save_method_signature` asserts the signature in this contract is what the code exposes (catches accidental signature drift in future refactors).
