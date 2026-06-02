# spec-061 — Operational Runbook

**Audience**: on-call operator finishing spec-061 rollout, or reviewing a
post-mortem of the post-mirror chain. Last updated 2026-06-02.

## State machine

The post-mirror chain (`scripts/bootstrap/spec061_post_mirror_chain.sh`)
writes one of these terminal/intermediate states to `/tmp/spec061_chain.state`.

| State | Meaning | Next action |
|---|---|---|
| `waiting_for_mirror` | Polling checkpoint, mirror still running | Nothing; let it work. |
| `verifying_integrity` | Running `verify_utxo_lifecycle_mirror` | Nothing. |
| `duplicates_found` | F1 materialised; running `--fix` | Nothing; dedup is automatic. |
| `running_creation_catchup` | Syncing DuckDB creations to tip, then mirroring delta | Nothing. |
| `computing_spent_backfill_range` | Resolving tip + frontier | Nothing. |
| `running_spent_backfill` | Spent-block backfill against QuestDB | Nothing. |
| `running_daily_metrics_backfill` | Backfilling mvrv/nupl/realized_cap | Nothing. |
| `running_acceptance_gate` | Running T010 integration test | Nothing. |
| `ready_for_issue_closure` | All steps green; suggested `gh issue close` in log | Run the suggested command, then `complete`. |
| `complete` | spec-061 done | Close Issue #8 if not already. |
| `fail_t010_red` | Acceptance gate is RED | Inspect log; identify which stream is not OK and why. |
| `fatal_mirror_crashed` | Mirror PID died before completing | Resume mirror via `--resume`. |
| `fatal_dedup_failed` | `--fix` raised | Inspect log; manual dedup or restore from snapshot. |
| `fatal_integrity_post_dedup` | After `--fix`, duplicates still present | Manual inspection of `utxo_lifecycle` schema. |
| `fatal_catchup_failed` | Creation catch-up raised | Inspect log; check Bitcoin Core + DuckDB health. |
| `fatal_tip_resolve_failed` | Both `bitcoin-cli` and Python RPC failed | Restart `bitcoind`; rerun chain. |
| `fatal_spent_frontier_resolve_failed` | `SELECT max(spent_block)` returned non-int | Inspect QuestDB; the table may be in a partial-write state. |
| `fatal_spent_backfill_failed` | Spent backfill raised | Inspect log; resume via `historical_spent_backfill --resume --target-backend questdb`. |

## Monitoring

```bash
# Live state
cat /tmp/spec061_chain.state

# Live log (preferred — chain is silent in foreground)
tail -f /tmp/spec061_chain.log

# Mirror process health
ps -p $(cat /tmp/mirror_utxo_lifecycle_to_questdb.pid) -o pid,stat,etime,%cpu,%mem

# Mirror checkpoint
jq . data/questdb_utxo_lifecycle_mirror_checkpoint.json

# Watchdog process
ps -ef | grep spec061_post_mirror_chain.sh | grep -v grep
```

## Notifications

The chain emits a single Discord webhook ping on EVERY terminal state
(`complete`, `fatal_*`, `fail_*`) when `DISCORD_WEBHOOK_URL` is set in the
environment. Intermediate states are silent — only the log carries them.

To enable:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." \
  nohup bash scripts/bootstrap/spec061_post_mirror_chain.sh \
    > /tmp/spec061_chain.log 2>&1 &
```

No webhook → silent operation, no error.

## Recovering from a failed terminal state

### `fail_t010_red`

The endpoint returned `overall != "OK"`. Run the same test interactively
to see which streams are not-OK:

```bash
RUN_STREAMS_HEALTH_CONTRACT=1 uv run pytest \
  tests/integration/test_streams_health_contract.py -v -m integration --tb=short
```

For each STALE / MISSING stream, inspect freshness directly:

```sql
-- max_ts streams
SELECT max(ts) FROM <table>;

-- tip_lag_blocks (utxo_lifecycle_full)
SELECT max(creation_block), max(spent_block) FROM utxo_lifecycle;
```

Common causes:
- daily aggregator timer not installed (T026 sudo step)
- mirror finished but backtest_whale_signals never ran (T026c not installed)
- Bitcoin Core lagging on the chain (the tip moved during the run)

### `fatal_mirror_crashed`

Inspect the mirror log:

```bash
tail -n 100 /tmp/mirror_utxo_lifecycle_to_questdb.log
```

Resume:

```bash
setsid uv run python -m scripts.bootstrap.mirror_utxo_lifecycle_to_questdb \
  --batch-size 50000 --block-batch-size 1000 --resume \
  >> /tmp/mirror_utxo_lifecycle_to_questdb.log 2>&1 &
echo $! > /tmp/mirror_utxo_lifecycle_to_questdb.pid

# Then restart the chain
nohup bash scripts/bootstrap/spec061_post_mirror_chain.sh \
  > /tmp/spec061_chain.log 2>&1 &
```

### Duplicate rows in `utxo_lifecycle` (F1 risk)

If `verify_utxo_lifecycle_mirror` detects duplicates after a clean run,
the F1 mid-chunk crash semantics likely materialised. Run:

```bash
uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror --fix
```

This deduplicates in-place via QuestDB's `LATEST ON ts PARTITION BY outpoint`
semantics. The operation is single-statement and atomic at the API surface.

## Closing Issue #8

When `STATE=complete`:

```bash
# 1. Generate the commit list per deliverable
git log --oneline 061-stream-consumption-contract ^main \
  > /tmp/spec061_commits.txt

# 2. Post the closure comment + close (template below)
gh issue close 8 --repo gptcompany/UTXOracle --comment "$(cat <<'EOF'
spec-061 complete. Deliverables landed across branch
`061-stream-consumption-contract`:

1. **10 canonical stream names acknowledged** + 3 daily aggregates →
   `docs/contracts/stream_registry.yaml` (13 entries).
2. **`GET /v1/streams/health`** → `api/routes/streams.py` +
   `api/models/streams.py`. Wire shape:
   `specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml`.
3. **Backend target** documented + implemented → QuestDB single-tenant via PG-wire
   per `specs/061-stream-consumption-contract/decisions.md::D1`.
4. **`schema_version` + 30-day soft-deprecation** → `docs/SCHEMA_VERSIONING.md`
   + every registry entry carries `schema_version: 1.0.0`.
5. **`utxoracle-daily-aggregator.timer`** + companion
   `utxoracle-backtest-mirror.timer` → at repo root, units pass
   `systemd-analyze verify`.

Acceptance test green: `pytest -m integration tests/integration/test_streams_health_contract.py`.

Consumer adoption guide: `docs/NAUTILUS_DEV_ADOPTION.md`.
Cross-ref: gptcompany/nautilus_dev#146.
EOF
)"
```

## Test gates (idempotent re-run safe)

```bash
# Full spec-061 unit suite (no live deps)
uv run pytest \
  tests/test_stream_registry.py \
  tests/test_streams_health.py \
  tests/test_streams_health_perf.py \
  tests/test_calculate_daily_metrics_questdb.py \
  tests/test_calculate_daily_metrics_idempotent.py \
  tests/test_mirror_backtest_whale_signals.py \
  tests/test_historical_spent_backfill_target_backend.py \
  tests/test_verify_utxo_lifecycle_mirror.py \
  tests/test_mirror_utxo_lifecycle_to_questdb.py \
  tests/test_catchup_utxo_lifecycle_to_tip.py \
  -q

# DDL coverage (requires live QuestDB)
uv run pytest tests/test_create_tables_ddl.py -v

# Acceptance gate (requires live QuestDB + full backfill)
RUN_STREAMS_HEALTH_CONTRACT=1 uv run pytest \
  tests/integration/test_streams_health_contract.py -v -m integration
```

## File index

| File | Purpose |
|---|---|
| `scripts/bootstrap/mirror_utxo_lifecycle_to_questdb.py` | DuckDB → QuestDB initial mirror |
| `scripts/bootstrap/catchup_utxo_lifecycle_to_tip.py` | Creation tip catch-up |
| `scripts/bootstrap/historical_spent_backfill.py` | Spent backfill with `--target-backend` |
| `scripts/bootstrap/verify_utxo_lifecycle_mirror.py` | F1 integrity check + `--fix` |
| `scripts/bootstrap/spec061_post_mirror_chain.sh` | Automation watchdog (this runbook's primary tenant) |
| `utxoracle-daily-aggregator.{service,timer}` | Daily mvrv/nupl/realized_cap aggregator |
| `utxoracle-backtest-mirror.{service,timer}` | DuckDB → QuestDB backtest mirror |
