# Quickstart: entity_flows_daily QuestDB Producer Pilot

**Date**: 2026-06-15
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

Operator-facing runbook. Three workflows: manual smoke, rollback, re-enable.

## Prerequisites

- QuestDB host instance reachable on `:8812` (PG-wire). Already verified by spec-062 daily aggregator runs.
- `data/utxoracle.duckdb` present with the source tables `entity_movement_events`, `entity_transfer_edges` populated (pre-condition for `aggregate_flows()` to produce non-empty output).
- `DISCORD_WEBHOOK_URL` set in environment (operator's responsibility; if unset, the helper logs a WARNING and skips webhook posts).

## Manual smoke (FR-011 + AC4 verification)

The canonical post-deploy verification. Run the aggregator once, then verify both stores received the same row set.

### Step 1 — Single run

```bash
cd /media/sam/1TB/UTXOracle
SPEC063_QUESTDB_WRITE=1 uv run python -m scripts.live.flow_aggregator
```

Expected stdout (or systemd journal if invoked via service):
- `Aggregating flows in /media/sam/1TB/UTXOracle/data/utxoracle.duckdb...`
- `Calculating daily flow aggregates...`
- `spec-063 entity_flows_daily dual-write success: date=YYYY-MM-DD duration_s=X.XX rows_written_duckdb=N rows_written_questdb=N`

Expected exit code: 0.

### Step 2 — Verify row-count parity

```bash
# DuckDB side
duckdb data/utxoracle.duckdb "SELECT count(*) FROM entity_flows_daily WHERE date = current_date"
# QuestDB side
curl -s "http://localhost:9000/exec?query=SELECT+count(*)+FROM+entity_flows_daily+WHERE+date%3Dcurrent_date()" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['dataset'][0][0])"
```

Both queries MUST return the same integer.

### Step 3 — Verify `/v1/streams/health`

```bash
curl -s -H "Authorization: Bearer $UTXORACLE_API_TOKEN" \
  http://localhost:8001/v1/streams/health \
  | jq '.streams[] | select(.name=="entity_flows_daily")'
```

Expected: `status: "OK"`, `stale_seconds` ≤ `sla_seconds` (`129600` = 36 h).

### Step 4 — Verify per-row identity

```bash
duckdb data/utxoracle.duckdb \
  "SELECT entity_id, inflow_btc, outflow_btc, netflow_btc FROM entity_flows_daily ORDER BY entity_id LIMIT 5"
curl -s "http://localhost:9000/exec?query=SELECT+entity_id%2C+inflow_btc%2C+outflow_btc%2C+netflow_btc+FROM+entity_flows_daily+ORDER+BY+entity_id+LIMIT+5" \
  | python3 -c "import json,sys; [print(r) for r in json.load(sys.stdin)['dataset']]"
```

The five rows MUST match by `entity_id` and the three DOUBLE values MUST be byte-identical (no rounding, no NaN coercion).

## Rollback runbook (Story 3 / FR-005)

The QuestDB write half can be disabled at the operator's discretion via the env var. The DuckDB write half is untouched.

### Step 1 — Set env var OFF

```bash
# For a systemd-invoked service, edit the unit's EnvironmentFile or set the env var:
sudo systemctl edit <invoker>.service
# Add under [Service]:
#   Environment=SPEC063_QUESTDB_WRITE=0
sudo systemctl daemon-reload
sudo systemctl restart <invoker>.service
```

For a manual invocation:

```bash
export SPEC063_QUESTDB_WRITE=0
uv run python -m scripts.live.flow_aggregator
```

Accepted OFF values (case-insensitive, trimmed): `0`, `false`, `no`. Anything else (including unset) is ON.

### Step 2 — Verify QuestDB connection NOT opened

After the run completes, check journal:

```bash
journalctl -u <invoker>.service -n 50 --no-pager | grep -E "spec-063|QuestDB"
```

Expected: log line `spec-063 entity_flows_daily QuestDB write half disabled by SPEC063_QUESTDB_WRITE=0` (or equivalent). NO log lines mentioning `_open_pg_sync` or `save_entity_flows_daily`.

### Step 3 — Verify existing QuestDB rows NOT deleted (forward-only rollback)

```bash
curl -s "http://localhost:9000/exec?query=SELECT+count(*)+FROM+entity_flows_daily" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['dataset'][0][0])"
```

Expected: the count from before the rollback. spec-063 rollback is forward-only — existing rows stay.

## Re-enable runbook

Reverse of rollback.

```bash
# Systemd:
sudo systemctl edit <invoker>.service
# Remove the Environment=SPEC063_QUESTDB_WRITE=0 line (or set it to 1).
sudo systemctl daemon-reload
sudo systemctl restart <invoker>.service

# Manual:
unset SPEC063_QUESTDB_WRITE
uv run python -m scripts.live.flow_aggregator
```

Then re-run the manual smoke (Steps 1-4 above) to confirm next run writes both stores.

## Failure investigation runbook

If the next run after enabling reports failures:

### Step 1 — Check Discord webhook channel

The webhook is the paging signal. Look for a message of the form:

> :rotating_light: entity_flows_daily QuestDB write failed for 2026-06-15: 47 rows failed (psycopg.OperationalError)

### Step 2 — Pull per-row details from journal

```bash
journalctl -u <invoker>.service --since "1 hour ago" | grep "entity_flows_daily QuestDB save failed"
```

Expected: one ERROR log per failed row, with `entity_id`, `date`, and exception class.

### Step 3 — Classify the failure

- **All rows failed with `psycopg.OperationalError`**: QuestDB unreachable. Check `systemctl status questdb` (or `docker ps | grep questdb`) and confirm `:8812` is listening.
- **Some rows failed with `psycopg.errors.UndefinedColumn`**: DDL drift. Re-run `create_tables_if_not_exist` (which now includes the spec-063 DEDUP UPSERT KEYS ALTER) and re-invoke `aggregate_flows()`.
- **Some rows failed with `psycopg.errors.DataError`**: NaN / Inf in a DOUBLE column. Investigate the source DuckDB rows for the `(entity_id, date)` pairs reported in the ERROR logs.

### Step 4 — Re-run after fix

```bash
uv run python -m scripts.live.flow_aggregator
```

Idempotent via DEDUP UPSERT KEYS — re-running upserts the previously-failed rows without duplicating successful ones.

## Production runtime gap notice

Per [decisions.md](./decisions.md) D6: spec-063 does NOT install a systemd timer for `aggregate_flows()`. The function is invoked ONLY by tests today. The manual smoke (above) is the canonical post-deploy verification path. A follow-up spec will own the scheduling decision.

For the 7-day green observation gate (SC-005), the operator MUST invoke `aggregate_flows()` at least once per 36-hour SLA window (e.g. daily) to keep `entity_flows_daily` reporting OK on `/v1/streams/health`. Suggested approach: wrap the manual smoke in a personal cron entry during the observation window:

```
# crontab -e
0 4 * * * cd /media/sam/1TB/UTXOracle && SPEC063_QUESTDB_WRITE=1 uv run python -m scripts.live.flow_aggregator >> /tmp/spec063_smoke.log 2>&1
```

This is operator-scoped scheduling, NOT a production systemd timer. The follow-up scheduling spec will replace it with a proper unit.
