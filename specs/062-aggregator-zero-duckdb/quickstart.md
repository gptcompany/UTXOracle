# Quickstart: Aggregator Zero-DuckDB Read Path

**Date**: 2026-06-05
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

Operator-facing runbook. Assumes the host has:
- The Phase 1 utxo_lifecycle backfill complete (`SELECT count(*) FROM utxo_lifecycle` > 170 M).
- The Phase 1.5-v2 timers installed (`utxoracle-block-heights-catchup.timer`, `utxoracle-daily-prices-refresh.timer`).
- QuestDB reachable on `:8812` (PG-wire) and `:9009` (ILP).

## Run for a single date (production mode)

```bash
uv run python -m scripts.metrics.calculate_daily_metrics \
    --date 2026-06-04 \
    --questdb-reads \
    --questdb-only
```

Expected output (truncated):
```
2026-06-05 00:36:25 - INFO - Calculating metrics for 2026-06-04...
2026-06-05 00:36:50 - INFO -   Realized Cap: $1.047T, MVRV: 1.631
2026-06-05 00:36:51 - INFO - spec-062 aggregator success: date=2026-06-04 duration_s=26.14 rows_written=3
```

Verify zero DuckDB holders during/after:
```bash
fuser data/utxoracle.duckdb
# expected: no output (or only unrelated processes)
```

Verify the row landed:
```bash
curl -s "http://localhost:9000/exec?query=SELECT+ts,mvrv,realized_cap,market_cap+FROM+mvrv_daily+WHERE+ts='2026-06-04'" \
    | jq '.dataset'
```

## Dry-run (no persistence)

```bash
uv run python -m scripts.metrics.calculate_daily_metrics \
    --date 2026-06-04 \
    --questdb-reads --questdb-only --dry-run
```

Logs a dry-run completion line and writes nothing.

## Historical backfill (last 30 days)

```bash
uv run python -m scripts.metrics.calculate_daily_metrics \
    --backfill 30 \
    --questdb-reads --questdb-only
```

Or for a range ending on a specific date:
```bash
uv run python -m scripts.metrics.calculate_daily_metrics \
    --backfill 30 --end-date 2026-05-31 \
    --questdb-reads --questdb-only
```

In production mode (`--questdb-reads --questdb-only`), the first failed date logs an ERROR with traceback, sends the Discord failure webhook, and aborts the backfill with a non-zero exit code. Legacy/non-production backfills keep the historical best-effort behavior.

## Legacy DuckDB mode (still supported during transition)

```bash
# Read AND write through DuckDB exclusively — pre-spec-062 behaviour.
uv run python -m scripts.metrics.calculate_daily_metrics --date 2026-06-04
```

This mode is preserved for ad-hoc callers (tests, notebooks). Production callers (the systemd timer) MUST use `--questdb-reads --questdb-only`.

## Systemd timer

The aggregator runs daily at 02:30 UTC via `utxoracle-daily-aggregator.timer` (installed by spec-061; out of scope for spec-062). Verify status:

```bash
systemctl status utxoracle-daily-aggregator.timer
systemctl list-timers | grep utxoracle-daily-aggregator
journalctl -u utxoracle-daily-aggregator.service -n 50 --no-pager
```

The timer's `ExecStart` passes `--questdb-reads --questdb-only` so the zero-DuckDB property (SC-002) holds in production.

## Failure handling

On failure, the script writes a structured ERROR log with traceback to journal and POSTs a one-line summary to `DISCORD_WEBHOOK_URL`:

```bash
# Tail recent failures
journalctl -u utxoracle-daily-aggregator.service -p err -n 20 --no-pager

# Check Discord channel for webhook notification.
```

The `/v1/streams/health` endpoint (spec-061) reports `mvrv_daily` / `nupl_daily` / `realized_cap_daily` as STALE within minutes of the SLA window expiring. That is the canonical "is the daily window fresh?" surface — do not poll the systemd timer state for that signal.

## Manual recovery for a missed date

If the timer skipped a date (e.g. QuestDB was down during the scheduled fire):

```bash
# Run for the missed date manually. Idempotent — re-running the same date upserts.
uv run python -m scripts.metrics.calculate_daily_metrics \
    --date 2026-06-04 \
    --questdb-reads --questdb-only
```

A concurrent timer fire targeting the same date is safe (FR-013): both runs converge to the same row via QuestDB `DEDUP UPSERT KEYS(ts)`.

## Testing locally before merging changes

```bash
# Unit tests (all mocked, fast)
uv run pytest \
    tests/test_calculate_daily_metrics.py \
    tests/test_calculate_daily_metrics_questdb.py \
    tests/test_calculate_daily_metrics_idempotent.py \
    -q

# Source-grep guard alone (catches duckdb_free regression)
uv run pytest tests/test_calculate_daily_metrics_questdb.py::test_aggregator_never_opens_duckdb_under_dual_flags -v
```

29 tests are expected to pass across the mocked aggregator suites. The source-grep guard (`test_aggregator_never_opens_duckdb_under_dual_flags`) is the load-bearing one: it fails the build if a future refactor removes the `duckdb_free` shortcut in `main()`.
