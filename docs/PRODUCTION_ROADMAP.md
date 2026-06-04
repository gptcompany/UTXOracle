# UTXOracle Production Roadmap

**Audience**: project owner reviewing before approval.
**Status**: draft revision 2 — 2026-06-04 (revised after codex review).
**Scope**: take spec-061 from "code-complete + 2/13 streams live" to
"all 13 streams green in production, with monitoring and recovery".
**Out of scope**: spec-062 (utxo_lifecycle producer migration to QuestDB
SSOT) is referenced but not detailed here — it deserves its own spec.

**Gate status snapshot (2026-06-04 — post Codex sign-off)**:

| # | Gate | Status |
|---|---|---|
| 1 | Target host | ✅ RESOLVED: same single Linux host for Phase 1/2 |
| 2 | Alerting channel | ✅ RESOLVED: Discord webhook via `DISCORD_WEBHOOK_URL` for Phase 1 |
| 3 | Backup destination | ⏸️ DEFERRED: tracked under spec-063, not blocking Phase 1/1.5/2/3a/3b/3d/3e |
| 4 | WS p95 connections | ✅ RESOLVED as "unknown, instrument first" — no Rust decision before §4a |
| 5 | BRK :7071 | ✅ RESOLVED: keep local, restart/harden, unless owner provides a remote BRK endpoint |
| 6 | block_heights + daily_prices upstream | ✅ RESOLVED: `build_block_heights.py --use-rpc` + `build_price_table.py` |
| 7 | Phase ordering | ✅ RESOLVED: Phase 1 → Phase 1.5 → Phase 2 → Phase 3 (observability allowed in parallel once producers are underway) |

**Sign-off state (revised 2026-06-04, post-implementation review):**
- ✅ **Phase 1**: signed off, **implemented**. The two UTXO supervisors
  (`utxoracle-utxo-creation-catchup.service`,
  `utxoracle-utxo-spent-backfill.service`) wrap QuestDB-direct scripts
  (`tip_catchup_lifecycle_via_rpc.py`,
  `tip_spent_backfill_via_rpc.py`); no DuckDB write path. Mirror timer
  documented for operator install.
- ⛔ **Phase 1.5 sign-off REVOKED** after Codex review of the
  implementation. The new units
  `utxoracle-block-heights-catchup.service` and
  `utxoracle-daily-prices-refresh.service` schedule **DuckDB writers**
  (`build_block_heights.py` and `build_price_table.py` both default to
  `data/utxoracle.duckdb` in write mode via
  `scripts/config/database.py:24`). The smoke run in
  `docs/PRODUCTION_PHASE1_SMOKE.md:135` already proved the failure mode
  — DuckDB lock conflict with the live wave1 materializer — and the
  current report's "BLOCKED ... not by the new unit definitions" line at
  `docs/PRODUCTION_PHASE1_SMOKE.md:150` understates the cause: the unit
  definitions ARE what schedules the conflicting DuckDB writes.
  - The two Phase 1.5 services and timers MUST NOT be installed in
    production as-is.
  - Phase 1.5 is replaced by **Phase 1.5-v2** below: QuestDB-native
    `block_heights` and `daily_prices` producers, plus a reader
    migration in `calculate_daily_metrics`.
- ⏸️ Phase 3.c (backup) stays deferred and does not block green
  production.

**Changelog vs r1**:
- §1 Phase 1: dropped the "add Restart=on-failure" task — already
  present on the two long-lived units (`utxoracle-api.service:24` has
  `Restart=on-failure`; `utxoracle-live-wave1-materializer.service:22`
  has `Restart=always`). Replaced with a unit-state audit distinguishing
  `absent` vs `not enabled` vs `not running`.
- §2 Phase 2: rewrote the producer mapping after verifying each script
  by hand. 4 of the 7 streams need NEW writer code (not just a systemd
  unit). Effort revised from 1 week to ~2 weeks.
- §3.d: `block_heights` upstream is NOT unknown —
  `scripts/bootstrap/build_block_heights.py` exists and writes via
  Bitcoin Core RPC. Added `daily_prices` as the second stale DuckDB
  source.
- §4: measurement spec moves from psutil to app-level counters
  (active_connections, broadcast p50/p95/p99, dropped, msg/s, bytes).
  Flagged that switching from `send_text` to `send_bytes` is a breaking
  client-side change unless every consumer handles binary frames.
- §0.3 and §7: aligned to a single 7-question gate (was 5 vs 7).

## 0. Ground truth at 2026-06-04 13:50 UTC

### What works

- `utxoracle-api.service` (enabled, running on :8001) — production
  endpoint deployed; `/v1/streams/health` answers per spec FR-003.
- `utxoracle-live-wave1-materializer.service` (enabled, running) —
  produces `urpd_features_daily` to live QuestDB :9912.
- `docker-compose.live.yml::utxoracle-live-worker` — produces
  `live_snapshots` to live QuestDB :9912 (recovered today after the
  mempool stack outage).
- `utxoracle-daily-aggregator.timer` (enabled, daily @ 03:30 UTC) — runs
  `calculate_daily_metrics --questdb-only`.
- `utxoracle-backtest-mirror.timer` (enabled, daily @ 04:00 UTC) —
  attempts `mirror_backtest_whale_signals`; no-ops when source DuckDB
  table is missing (current state).
- Host QuestDB on :8812 — sole backend for `/v1/streams/health`.
- Two RPC backfills running under shell supervisors: tip catchup and
  spent backfill for `utxo_lifecycle`. They will finish in hours.
- The new mirror service `scripts/bootstrap/mirror_live_questdb_to_host.py`
  bridges live QuestDB :9912 → host QuestDB :8812 every 60 s.

### What does not work

| Stream | Reason MISSING | Existing script (verified) | What is actually missing |
|---|---|---|---|
| `whale_transactions` | no producer writes to QuestDB | `scripts/whale_flow_detector.py` is a CLI/block analyzer that prints a signal (line 914); no `Sender`, no `save_whale_transaction`, no `repo.async_send_row` anywhere in it | **NEW writer** + systemd unit |
| `mempool_predictions` | producer exists but is not running as a service | `scripts/mempool_whale_monitor.py` writes via `repo.async_send_row("mempool_predictions", ...)` at line 400 — already QuestDB-ready | **Systemd unit only** (the existing `utxoracle-whale-detection.service` may already cover this — verify in Phase 1 audit) |
| `net_flow_metrics` | producer writes the wrong table to the wrong store | `scripts/live/flow_aggregator.py:121` writes `entity_flows_daily` to **DuckDB**, not `net_flow_metrics` to QuestDB | **NEW writer** + systemd unit |
| `entity_flows_daily` | producer writes DuckDB; QuestDB target is empty | `scripts/live/flow_aggregator.py:121` writes DuckDB `entity_flows_daily` | **Mirror DuckDB→QuestDB** (analogous to `mirror_backtest_whale_signals.py`) + systemd timer; OR teach `flow_aggregator.py` to dual-write |
| `price_analysis` | no producer writes QuestDB | `scripts/metrics/exchange_netflow.py` has no QuestDB calls; no other script writes `price_analysis` | **NEW writer** + systemd unit |
| `utxo_snapshots` | no producer wired | derive from `utxo_lifecycle` at EOD | **NEW writer** + systemd timer |
| `backtest_whale_signals` | source DuckDB table doesn't exist | `scripts/whale_flow_backtest.py` (manual run); mirror timer exists | Manual one-shot of the backtest, then the existing `utxoracle-backtest-mirror.timer` keeps QuestDB synced |

Upstream issues:

- DuckDB `block_heights` ferma a 2025-12-16 14:55:50 UTC (928,139 rows,
  max height 928,138). Daily aggregator cannot produce metrics for any
  date past that. The producer exists and works:
  `scripts/bootstrap/build_block_heights.py` walks Bitcoin Core RPC
  (`getblockhash` + `getblockheader`, 2 calls per block, local). It is
  not currently scheduled. §3.d schedules it.
- DuckDB `daily_prices` ferma a 2025-12-14 (5,462 rows). The producer
  exists and works: `scripts/bootstrap/build_price_table.py` fetches
  BTC/USD from the mempool.space `/api/v1/historical-price` endpoint
  (2011 → present). It is idempotent: creates `daily_prices` if absent,
  skips existing dates, defaults `--end-date` to yesterday. Phase 1.5
  schedules it.
- BRK on host:7071 intermittently disconnects (observed in live worker
  logs). Not blocking but noisy. Likely a BRK config / restart loop.
- Two QuestDB instances coexist (:8812 host + :9912 docker). The mirror
  bridges them. A future unification is preferred but not blocking.

### Open questions for the owner (7 — same set as §7)

1. **Deployment target**: same host as dev, separate Linux box, or
   Kubernetes? The systemd units below assume single-host Linux and
   hard-code `User=sam` + `WorkingDirectory=/media/sam/1TB/UTXOracle`.
2. **Alerting channel**: Discord webhook, PagerDuty, or other? Phase 1
   defaults to Discord via `DISCORD_WEBHOOK_URL` env var.
3. **Backup destination**: S3 bucket name, NAS path, or separate disk?
   Must be settled before Phase 3 backup tests.
4. **Expected WS p95 concurrent connections**: gates the Rust/Python
   decision in §4. If unknown, the answer is "measure first".
5. **BRK on :7071**: keep local, restart, or repoint to remote? The
   7071 connection issues block daily metrics indefinitely.
6. **`block_heights` + `daily_prices` upstream**: RESOLVED 2026-06-04.
   - `block_heights`: `scripts/bootstrap/build_block_heights.py --use-rpc`.
   - `daily_prices`: `scripts/bootstrap/build_price_table.py` (idempotent,
     skips existing dates, defaults end-date to yesterday).
   Phase 1.5 wraps both in hourly/daily systemd timers.
7. **Phase ordering**: parallel or sequential? Codex's recommendation
   (which I endorse): Phase 1 → source-freshness mini-pass for
   `block_heights` and `daily_prices` → Phase 2 → rest of Phase 3.
   Observability work in Phase 3 can run in parallel.

---

## 1. Phase 1 — Stabilize what's running (1–2 days)

### Deliverables

1. **Unit-state audit** — produce `docs/PRODUCTION_UNIT_AUDIT.md`
   classifying every `utxoracle-*` unit found in the repo against three
   states:

   - `absent`: no unit file exists yet (the 7 producer streams in §2).
   - `present-not-enabled`: file exists, `systemctl is-enabled` returns
     `disabled` (e.g. `utxoracle-snapshot-refresh.service`, the new
     `utxoracle-mirror-live-questdb.{service,timer}`).
   - `present-enabled-not-running`: enabled but `is-active` returns
     `inactive` (timers waiting for next fire, or a oneshot between runs).
   - `present-enabled-running`: green (`utxoracle-api.service`,
     `utxoracle-live-wave1-materializer.service`).

   No restart-policy change in Phase 1 — existing units already carry
   `Restart=on-failure` / `Restart=always` (see Changelog).

2. **Install the live → host mirror timer.**
   Already authored: `utxoracle-mirror-live-questdb.{service,timer}`.

   ```bash
   sudo cp utxoracle-mirror-live-questdb.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now utxoracle-mirror-live-questdb.timer
   ```

3. **Replace the ad-hoc nohup supervisors with systemd units.**
   New files (to be added in this phase, with paired tests):

   - `utxoracle-utxo-creation-catchup.service` — wraps
     `scripts/bootstrap/utxo_lifecycle_supervisor.sh creation`,
     `Restart=on-failure RestartSec=60s`. Self-exits when `Already at
     tip`.
   - `utxoracle-utxo-spent-backfill.service` — symmetric.

4. **Add structured logging to the supervisor scripts** so journald can
   ship them to whatever log aggregator the operator chooses.

5. **Discord webhook on terminal state.** Already wired in
   `spec061_post_mirror_chain.sh` (G4). Extend the same pattern to the
   new supervisor units via an `ExecStopPost=` hook that curl-pings the
   webhook on non-zero exit.

### Success criteria

- `systemctl list-timers utxoracle-*` shows mirror-live-questdb.timer
  green every minute.
- `/tmp/spec061_mirror_checkpoint.json` advances monotonically.
- After 6 h of operation, host QuestDB max_ts for `live_snapshots` and
  `urpd_features_daily` is within 5 min of live QuestDB max_ts.

### Risks

- Sandbox blocked `/etc` writes during dev (operator must run the
  installs manually). Documented in the unit headers.

### Estimated effort

- Code/file authoring: 2 hours.
- Operator install + smoke test: 30 min.
- Soak window: 6 h passive observation.

---

## 1.5-v2. Source freshness on QuestDB (replaces revoked Phase 1.5) — 2–3 days

**Why v2:** the original Phase 1.5 routed `block_heights` and
`daily_prices` refresh through DuckDB writers, reintroducing the very
DuckDB write-lock bottleneck spec-061 eliminated for `utxo_lifecycle`.
v2 removes DuckDB from the daily-metrics critical path entirely. The
daily aggregator (`mvrv_daily`, `nupl_daily`, `realized_cap_daily`) is
the last component that depends on DuckDB reference data; after v2 it
reads from QuestDB.

### Deliverables

1. **QuestDB DDL** for two new reference tables, added to
   `api/questdb_repository.py::create_tables_if_not_exist`:

   ```sql
   -- height -> wall-clock timestamp (UTC). Idempotent on height.
   CREATE TABLE IF NOT EXISTS block_heights (
       height LONG,
       ts TIMESTAMP,
       fetched_at TIMESTAMP
   ) TIMESTAMP(ts) PARTITION BY YEAR WAL
     DEDUP UPSERT KEYS(ts, height);

   -- date -> BTC/USD price. Idempotent on date.
   CREATE TABLE IF NOT EXISTS daily_prices (
       date TIMESTAMP,
       price_usd DOUBLE,
       source SYMBOL,
       fetched_at TIMESTAMP
   ) TIMESTAMP(date) PARTITION BY YEAR WAL
     DEDUP UPSERT KEYS(date);
   ```

   `DEDUP UPSERT KEYS` makes re-runs absorb cleanly without any explicit
   "skip existing date" logic on the writer side.

2. **NEW QuestDB-native writers** under `scripts/bootstrap/`:

   - `scripts/bootstrap/build_block_heights_questdb.py` — same RPC
     walking logic as the existing `build_block_heights.py`, but writes
     to QuestDB via ILP. CLI: `--start-block N` (defaults to
     `max(height)+1 FROM block_heights`), `--end-block N` (defaults to
     `bitcoin-cli getblockcount`), `--workers N`.
   - `scripts/bootstrap/build_price_table_questdb.py` — same
     mempool.space `/api/v1/historical-price` fetch as the existing
     `build_price_table.py`, but writes to QuestDB. CLI: `--start-date
     YYYY-MM-DD` (defaults to `max(date)+1d FROM daily_prices`),
     `--end-date` (defaults to yesterday).

   Both scripts are unit-tested with mocked QuestDB Sender and RPC/HTTP
   clients. The existing DuckDB scripts stay in the repo as the
   historical-only path (manual one-shot for backfills); they get a
   docstring banner pointing to the QuestDB variants as the production
   path.

3. **Reader migration in `calculate_daily_metrics.py`**:

   - `get_blocks_for_date(target_date, conn)` rewritten to query QuestDB
     `block_heights` via psycopg (the same sync path the daily metrics
     code already uses for `save_*_daily`). Falls back to DuckDB only
     in the legacy `--no-questdb-reads` flag (default OFF in
     production, ON in unit tests that mock the DuckDB conn).
   - `get_price_for_date(target_date, conn)` rewritten analogously
     against QuestDB `daily_prices`.
   - The aggregator no longer opens DuckDB in read mode for these two
     lookups; DuckDB only stays open for `utxo_lifecycle_full` reads
     until spec-062 lands.

4. **Replace the two REVOKED Phase 1.5 timers** with QuestDB-only
   versions:

   - `utxoracle-block-heights-catchup.{service,timer}` — same cadence
     (hourly), but `ExecStart` points to the new
     `scripts.bootstrap.build_block_heights_questdb` module.
     `After=questdb.service` instead of `network-online.target` is
     enough; Bitcoin Core is implicitly available via bitcoin-cli at
     the host level.
   - `utxoracle-daily-prices-refresh.{service,timer}` — same cadence
     (daily 01:00 UTC), `ExecStart` points to the new
     `scripts.bootstrap.build_price_table_questdb` module.
     `After=questdb.service docker-api-1.service` (the latter being the
     mempool API that supplies historical prices).

   Both timers do **not** touch DuckDB. The old service files
   (`utxoracle-block-heights-catchup.service` and
   `utxoracle-daily-prices-refresh.service`) are **removed from the
   repo** in the same commit that adds the v2 versions, so there is no
   risk of an operator installing the wrong file.

5. **Update `docs/PRODUCTION_PHASE1_SMOKE.md`** to reflect the revoked
   sign-off and explicitly attribute the row-count blocker to the unit
   definitions themselves, not to "external lock contention".

### Sequencing inside v2

a → c → b → d → e:

- **a** DDL ships first; CI tests cover idempotent re-creation.
- **c** Reader migration in `calculate_daily_metrics` ships with a
  feature flag (`--questdb-reads` default false in this commit) so the
  legacy DuckDB path still works for unit tests.
- **b** Writer scripts ship. Smoke runs against a live QuestDB on dev
  prove monotonic `max(height)` and `max(date)` advance.
- **d** Timers ship. Operator installs.
- **e** Smoke report rewrite + sign-off vote.

### Success criteria

- After 24 h of running both v2 timers: QuestDB `block_heights.max(ts)`
  is within 1 h of `bitcoin-cli getblockcount`-implied wall time; QuestDB
  `daily_prices.max(date)` equals yesterday.
- The systemd timer for `utxoracle-daily-aggregator` produces a row
  into `mvrv_daily` for today **with no DuckDB write occurring** during
  the run (verified by `fuser data/utxoracle.duckdb` returning empty
  while the aggregator runs).

### Risks

- Writer rewrites are not 1:1 — the original DuckDB scripts use the
  DuckDB CSV bulk insert path; the QuestDB variants stream rows via
  ILP. Behaviour parity must be verified per row count and per
  edge-case (e.g. blocks with the same height re-emitted on chain
  reorg).
- `calculate_daily_metrics` reader migration changes the SQL dialect
  (DuckDB SQL → QuestDB PG-wire dialect). Most queries are simple
  `SELECT WHERE date = ?` style and port directly; ones that use
  DuckDB-specific functions (`EPOCH_MS`, `DATE_TRUNC` quirks) need
  attention.

### Estimated effort

- DDL + DDL tests: 2 hours.
- 2 NEW writer scripts + unit tests + smoke: 1 day.
- Reader migration in `calculate_daily_metrics` + tests: 1 day.
- New timers + replacing the revoked files: 2 hours.
- Smoke report rewrite: 1 hour.
- **Total: 2–3 working days.**

---

## 2. Phase 2 — Bring up the 7 missing producers (~2 weeks)

### Approach

The deliverable per stream is now **producer/writer code + unit file +
smoke test**, not just a systemd unit. 4 of the 7 streams have no
QuestDB writer at all today; they require new code, not just packaging.

One commit per stream: the writer code (if needed), the systemd unit,
a smoke test against an empty target table, and a docstring trail.

### Producer-by-producer plan

| # | Stream | What's needed | Cadence | Unit | Effort |
|---|---|---|---|---|---|
| 1 | `whale_transactions` | **NEW writer** (`scripts/live/whale_transactions_writer.py`): reads mempool API + Bitcoin Core RPC, classifies whale tx (≥100 BTC), writes to QuestDB. Existing `whale_flow_detector.py` provides the classification logic; the new module ports it to a long-running async loop with `repo.async_send_row("whale_transactions", ...)`. | continuous | `utxoracle-whale-transactions.service` | 3 d |
| 2 | `mempool_predictions` | **Systemd unit only.** `scripts/mempool_whale_monitor.py` already calls `repo.async_send_row("mempool_predictions", ...)` at line 400. Verify it isn't already running under the existing `utxoracle-whale-detection.service` first. | continuous | `utxoracle-mempool-predictions.service` (or reuse `utxoracle-whale-detection.service`) | 0.5 d |
| 3 | `net_flow_metrics` | **NEW writer** (`scripts/metrics/net_flow_writer.py`): aggregate from `whale_transactions` into rolling 1h/6h/24h windows; emit one row per closed window to QuestDB `net_flow_metrics`. Depends on #1 being live. | continuous | `utxoracle-net-flow-metrics.service` | 2 d |
| 4 | `entity_flows_daily` | **Mirror DuckDB → QuestDB.** Existing `scripts/live/flow_aggregator.py:121` writes DuckDB `entity_flows_daily`. Write a mirror analogous to `mirror_backtest_whale_signals.py`. Alternatively dual-write inside `flow_aggregator.py` itself — leaves it to the implementer's preference. | daily 02:00 UTC | `utxoracle-entity-flows-mirror.timer` | 1 d |
| 5 | `price_analysis` | **NEW writer** (`scripts/metrics/price_analysis_writer.py`): compares exchange API price vs `live_snapshots.utxoracle_price` daily, writes one row to QuestDB `price_analysis`. No existing producer touches this table. | daily 02:15 UTC | `utxoracle-price-analysis.timer` | 1.5 d |
| 6 | `utxo_snapshots` | **NEW writer** (`scripts/metrics/utxo_snapshots_writer.py`): EOD aggregate of `utxo_lifecycle` into one row per day. Must follow utxo_lifecycle backfill in Phase 1. | daily 02:30 UTC | `utxoracle-utxo-snapshots.timer` | 1.5 d |
| 7 | `backtest_whale_signals` | Manual one-shot of `scripts/whale_flow_backtest.py` populates DuckDB; the existing `utxoracle-backtest-mirror.timer` already mirrors to QuestDB and was hardened to be non-fatal on missing source (commit 256eac9). | manual + daily mirror | (mirror timer exists) | 0.5 d |

Total writer code + units: **~10 working days** (≈ 2 weeks with smoke +
review).

### Per-producer systemd template

```ini
# utxoracle-<name>.service
[Unit]
Description=UTXOracle <stream> producer (spec-061)
After=network-online.target docker.service utxoracle-api.service
Wants=network-online.target

[Service]
Type=simple
User=sam
Group=sam
WorkingDirectory=/media/sam/1TB/UTXOracle
Environment="PATH=/home/sam/.local/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-/media/sam/1TB/UTXOracle/.env
Restart=on-failure
RestartSec=60s
StartLimitIntervalSec=600
StartLimitBurst=5
ExecStart=/usr/bin/env uv run python -m <module path>

[Install]
WantedBy=multi-user.target
```

### Success criteria

- After 24 h of running all 7 units: every stream reports rows in
  QuestDB, and `/v1/streams/health::overall == "OK"` (or only stale
  streams are those gated by upstream DuckDB freshness — see §3.d).

### Risks

- Producers #1 and #2 depend on the mempool API being stable. The
  mempool stack restart loop observed today (docker-db-1 exited) needs
  a separate hardening pass — see §3.
- `entity_flows_daily` requires `address_clusters` to be populated. If
  the production DB is empty, a `scripts/clustering/init_entity_registry.py`
  run is required first (manual one-shot).
- For #2: avoid double-running mempool_whale_monitor if
  `utxoracle-whale-detection.service` already covers it. Phase 1 audit
  surfaces this.

---

## 3. Phase 3 — Production hardening (1 week)

### 3a. Health monitoring

- **Prometheus exporter** in `api/main.py` exposing:
  - per-stream `utxoracle_stream_last_row_ts_seconds`
  - per-stream `utxoracle_stream_stale_seconds`
  - `utxoracle_streams_health_overall{status=OK|DEGRADED}` (counter)
  - producer-side `utxoracle_producer_runs_total{name, status}`
- **Grafana dashboard** (one panel per stream + overall rollup + per-producer
  cadence). Imported as JSON in `docs/grafana/utxoracle-spec061.json`.
- **Alertmanager rules**:
  - Stream STALE > 2 × SLA for > 10 min → page.
  - Producer service entered `failed` state → page.
  - QuestDB unreachable from API → page.

### 3b. Log aggregation

- journald → Loki (or Promtail → existing log infra). One file in
  `docs/grafana/` for the log query templates.

### 3c. Backup strategy — DEFERRED

Owner decision 2026-06-04: backup destination is not chosen yet, so this
sub-phase is removed from the critical path. Tracked as a follow-up
under the eventual spec-063 (operational readiness).

When it returns, the candidate scope (kept here for reference):
- **QuestDB**: `BACKUP TABLE` per spec-061 table daily, rsync to
  cold storage. Retention: 30 days hot, 12 months cold.
- **DuckDB**: `EXPORT DATABASE 'path/'` daily (host disk is 60 GB so
  this is significant — likely an incremental approach via Litestream
  or rotating EXPORT outputs weekly with monthly retention).
- **stream_registry.yaml**: source-controlled, no separate backup
  needed.

Phase 3 still ships **3a observability + 3b log aggregation + 3d source
pipeline + 3e DR procedures** without 3c.

### 3d. Source data pipeline (also runs as a mini-pass between Phase 1 and Phase 2)

The single biggest production blocker right now is DuckDB source
freshness. Two tables are stale:

- `block_heights` ferma a 2025-12-16 14:55:50 UTC (928,139 rows, max
  height 928,138).
- `daily_prices` ferma a 2025-12-14 (5,462 rows).

Without both refreshed, `calculate_daily_metrics` cannot produce
metrics for any recent date, so `mvrv_daily / nupl_daily /
realized_cap_daily` will report STALE forever.

Producers identified — scheduling needed:

- **block_heights**: `scripts/bootstrap/build_block_heights.py` exists
  and uses Bitcoin Core RPC (`getblockhash` + `getblockheader`, 2 calls
  per block, local). Wrap it in a thin hourly timer
  `utxoracle-block-heights-catchup.timer` that runs
  `build_block_heights.py --use-rpc` with `--start max(block_heights.height)+1`.
- **daily_prices**: producer TBD — Phase 1 audit must identify it
  (probably under `scripts/metrics/` or `scripts/clustering/`). Once
  identified, wrap in a daily timer.

This work belongs **between Phase 1 and Phase 2** per Codex's
recommendation: without it, the §2 daily aggregator producers can't
emit fresh rows even after their writer code lands.

### 3e. Disaster recovery procedures

Document in `docs/RUNBOOK_SPEC061.md`:

- Total QuestDB loss: how to rebuild from scratch (run mirror script
  for spec-061 tables + re-run catchup).
- DuckDB corruption: restore from latest EXPORT + replay live worker.
- API outage: systemd already restarts; manual restart procedure.

### Success criteria

- Grafana shows all 13 streams green over a 24 h window.
- Alert tripping on simulated outage (manually stop one producer) →
  alert fires within 10 min.
- Backup restore test: restore yesterday's QuestDB snapshot to a scratch
  instance and verify row counts match.

### Estimated effort

- 4–5 working days.

---

## 4. Phase 4 — WebSocket performance

### Premise

The existing WS surface is dual-endpoint inside the FastAPI/uvicorn
process:

- `api/routes/execution.py /stream` — simple broadcast list.
- `api/whale_websocket.py` — per-user routing.

Both share the same uvicorn worker. Whether Rust is justified is a
function of the **measured** load, not gut feel. Step 1 is therefore to
instrument.

### 4a. Measure before deciding (1 day)

Counters live **inside the app**, not via psutil. The MempoolWhaleMonitor
runs inside FastAPI (`api/apps/live.py:132`) and broadcasts via
`api/routes/execution.py::stream_manager.broadcast` (current
implementation at `api/routes/execution.py:41` does `json.dumps(message)`
then `connection.send_text(payload)` with a 100 ms `asyncio.wait_for`
timeout).

Add the following Prometheus counters/gauges to `stream_manager`:

- `utxoracle_ws_active_connections` (gauge)
- `utxoracle_ws_broadcast_messages_total` (counter)
- `utxoracle_ws_broadcast_latency_seconds` (histogram p50/p95/p99)
- `utxoracle_ws_dropped_clients_total` (counter)
- `utxoracle_ws_broadcast_message_bytes` (histogram)

Also expose `utxoracle_ws_send_text_timeouts_total` so the current
100 ms timeout's blast radius is visible.

New helper script `scripts/observe_ws_load.py` connects N synthetic
clients (configurable) and records the same counters from the Prometheus
endpoint over a 1 h window. Output to `docs/WS_BASELINE_2026-06.md`.
**Owner reviews** the numbers and picks the path below.

### 4b. Option A — Python tuning (1 day, 3–5× gain typical)

- `uv add uvloop orjson`
- Replace the broadcast loop. **The simplest variant keeps `send_text`**
  to avoid a client-side breaking change (binary frames are not
  guaranteed to be handled by every consumer; switching to `send_bytes`
  must be a coordinated migration with the clients):

  ```python
  import orjson

  async def broadcast(self, message: dict):
      if not self.active_connections:
          return
      payload = orjson.dumps(message).decode("utf-8")  # serialise once
      await asyncio.gather(
          *(
              asyncio.wait_for(ws.send_text(payload), timeout=0.1)
              for ws in self.active_connections
          ),
          return_exceptions=True,
      )
  ```

- If a client migration to binary frames is feasible, the bigger gain
  comes from `send_bytes(payload)` (skip the encode round-trip). Track
  that as a separate change with a client compatibility matrix.

- Configure uvicorn with `--loop uvloop --http httptools`.

- Re-measure after deploy. If the new numbers fit the SLA, stop here.

**When to choose**: < 100 concurrent connections per measurement, p99
latency acceptable, simple op model preferred.

### 4c. Option B — Rust sidecar broadcaster (5–10 days, 5–15× gain)

A separate Rust process owns the WS endpoints. FastAPI keeps REST,
auth, and the spec-061 endpoint. The two communicate via Redis pub/sub
(or NATS, or QuestDB CDC — pick one).

Stack:

- `axum 0.7` + `tokio-tungstenite 0.21` + `redis 0.24`
- Single binary, deployed as `utxoracle-ws-broadcaster.service` next to
  the existing API service.
- Wire format on Redis pub/sub: msgpack (smaller + faster than JSON).
- Build: `cargo build --release`, ships as a Docker image or static
  binary.

New systemd unit `utxoracle-ws-broadcaster.service` listening on a
separate port (e.g. `:8002`). Reverse-proxy (nginx, caddy, or tcp
forwarder) routes `wss://utxoracle/ws/*` to the Rust process.

**When to choose**: 100–1k concurrent connections, p99 < 50 ms
required, willing to maintain a second language.

### 4d. Option C — Full rewrite (3–4 weeks, 10–20× gain)

Replace the entire FastAPI WS surface in Rust. Heavy. Justified only if
Option B is empirically insufficient.

### Recommendation

Default plan: **§4a always, §4b only if measured load demands it**.
Code in §4b is straightforward once the measurement justifies it.

### Success criteria for the WS track

- §4a deployed and verified: CPU drop ≥ 50 % on the API process under
  the same synthetic load.
- p99 broadcast latency below the agreed SLA (TBD — current spec-061
  doesn't enforce a WS SLA).

### Estimated effort

- 4a: 1 day measure + 1 day implement + 1 day verify.
- 4b: 5–10 days dev + 2 days deploy + 2 days soak.

---

## 5. Spec-062 placeholder (out of scope for this roadmap)

The next major work after Phase 3 is to migrate
`utxo_lifecycle` writes to QuestDB SSOT, eliminating DuckDB lock
contention permanently. Out of scope for this document; tracked
separately.

---

## 6. Summary table

| Phase | Effort | Owner | Blockers |
|---|---|---|---|
| 1. Stabilize + unit audit | 1–2 d | Code + Operator | none |
| 1.5. Source freshness (block_heights + daily_prices) | 1 d | Code + Operator | identify daily_prices producer |
| 2. Producers (4 NEW writers + 3 packaging) | ~2 wk | Code | mempool stack stability, address_clusters seed |
| 3. Hardening (Prometheus, Grafana, backups, DR) | 1 wk | Code + Operator | Grafana access, backup destination |
| 4. WS perf | 1 d measure → 1 d Option A → up to 4 wk Option C | Code | numbers from §4a measurement |

Total to "everything green in production": **3–4 weeks** assuming the
owner gives the missing ground-truth answers in §0 and Codex's
sequencing (Phase 1 → Phase 1.5 → Phase 2 → Phase 3) is approved.

---

## 7. Sign-off checklist (the same 7 as §0.3)

Before any code work starts, the owner should confirm:

- [ ] **1.** Target deployment host: same single Linux host as dev,
      separate Linux box, or Kubernetes. (Codex default: same single
      host for Phase 1/2; units hard-code `sam` +
      `/media/sam/1TB/UTXOracle`.)
- [ ] **2.** Alerting channel: Discord webhook URL (default for Phase 1),
      PagerDuty, or other.
- [x] **3. DEFERRED (owner decision 2026-06-04).** Backup destination
      is explicitly deferred. §3.c (backup strategy) is removed from
      the critical path and tracked as a follow-up under the eventual
      spec-063 (operational readiness). This does NOT block Phase 1,
      Phase 1.5, Phase 2, or the rest of Phase 3 (3a observability,
      3b log aggregation, 3d source pipeline, 3e DR procedures).
- [ ] **4.** Expected p95 WS concurrent connections. (If unknown:
      "instrument first, don't choose Rust yet" — Codex's stance, which
      I endorse.)
- [ ] **5.** BRK on :7071: keep local, restart, or repoint to a remote
      healthy BRK.
- [x] **6. RESOLVED 2026-06-04.** Both refreshers identified:
      `scripts/bootstrap/build_block_heights.py --use-rpc` and
      `scripts/bootstrap/build_price_table.py`. Phase 1.5 schedules both.
- [ ] **7.** Phase ordering: Codex's recommendation —
      Phase 1 → source-freshness mini-pass (block_heights + daily_prices)
      → Phase 2 → Phase 3 observability in parallel with Phase 2.

Once these are settled, Phase 1 can start immediately; Phase 1.5 the
same day; Phase 2 in series after Phase 1.5 lands.
