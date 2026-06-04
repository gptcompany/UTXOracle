# UTXOracle Production Roadmap

**Audience**: project owner reviewing before approval.
**Status**: draft 2026-06-04. To be confirmed/edited by the operator
before any work starts.
**Scope**: take spec-061 from "code-complete + 2/13 streams live" to
"all 13 streams green in production, with monitoring and recovery".
**Out of scope**: spec-062 (utxo_lifecycle producer migration to QuestDB
SSOT) is referenced but not detailed here — it deserves its own spec.

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

| Stream | Reason MISSING | Producer script |
|---|---|---|
| `whale_transactions` | no systemd unit | `scripts/whale_flow_detector.py` |
| `mempool_predictions` | no systemd unit | `scripts/mempool_whale_monitor.py` |
| `net_flow_metrics` | no systemd unit | `scripts/live/flow_aggregator.py` |
| `entity_flows_daily` | no systemd unit + needs cluster registry seeded | `scripts/clustering/*` |
| `price_analysis` | no systemd unit | `scripts/metrics/exchange_netflow.py` (or dedicated) |
| `utxo_snapshots` | no producer wired to QuestDB | derive from `utxo_lifecycle` at EOD |
| `backtest_whale_signals` | source DuckDB table doesn't exist | `scripts/whale_flow_backtest.py` (manual run, then timer mirrors) |

Upstream issues:

- DuckDB `block_heights` ferma a 2025-12-16. Daily aggregator can't
  produce metrics for any date past that. Whatever pipeline writes
  `block_heights` is not running on this host.
- BRK on host:7071 intermittently disconnects (observed in live worker
  logs). Not blocking but noisy. Likely a BRK config / restart loop.
- Two QuestDB instances coexist (:8812 host + :9912 docker). The mirror
  bridges them. A future unification is preferred but not blocking.

### Open questions for the owner

1. Production deployment target: same host as dev? Separate Linux box?
   Kubernetes? The systemd units below assume single-host Linux.
2. Acceptable downtime for cutover (Phase 1 install)? The endpoint is
   already deployed; new timers can install without restart.
3. Discord webhook or another alerting channel? The runbook expects
   `DISCORD_WEBHOOK_URL` env var; if a different channel is preferred,
   say so.
4. How many concurrent WebSocket clients are expected at p95? This
   gates the Rust/Python decision in §4. We can also instrument first.
5. Is BRK supposed to be running on this host, or is the live worker
   meant to talk to a remote BRK? The 7071 connection issues block
   daily metrics indefinitely otherwise.

---

## 1. Phase 1 — Stabilize what's running (1–2 days)

### Deliverables

1. **Install the live → host mirror timer.**
   Authored in repo as `utxoracle-mirror-live-questdb.{service,timer}`.

   ```bash
   sudo cp utxoracle-mirror-live-questdb.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now utxoracle-mirror-live-questdb.timer
   ```

2. **Replace the ad-hoc nohup supervisors with systemd units.**
   New files (to be added in this phase, with paired tests):

   - `utxoracle-utxo-creation-catchup.service` — wraps the existing
     `scripts/bootstrap/utxo_lifecycle_supervisor.sh creation`, restart
     on failure, exits cleanly when `Already at tip`.
   - `utxoracle-utxo-spent-backfill.service` — symmetric for the
     spent backfill.

   Both `Type=simple Restart=on-failure RestartSec=60s`. They self-exit
   when caught up; systemd records the final state.

3. **Add `Restart=on-failure` to all existing units** that don't have
   it. Audit:

   - `utxoracle-api.service` (currently `Type=simple`, no Restart) → add
     `Restart=on-failure RestartSec=10s`.
   - `utxoracle-live-wave1-materializer.service` → same.
   - All `oneshot` services (timers) — no change needed; the timer itself
     re-triggers.

4. **Add structured logging to the supervisor scripts** so journald can
   ship them to whatever log aggregator the operator chooses.

5. **Discord webhook on terminal state**.
   Already wired in `spec061_post_mirror_chain.sh` (G4). Extend the same
   pattern to the new supervisor units via an `ExecStopPost=` hook that
   curl-pings the webhook on non-zero exit.

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

## 2. Phase 2 — Bring up the 7 missing producers (1 week)

### Approach

For each producer: write a `utxoracle-<name>.service` (continuous) or
`utxoracle-<name>.timer` (periodic) following the template of the
existing `utxoracle-live-wave1-materializer.service`. One commit per
producer with: the unit file, a smoke test against an empty QuestDB
table, and a docstring update on the producer.

### Producer-by-producer plan

| # | Stream | Cadence | Unit | Notes |
|---|---|---|---|---|
| 1 | whale_transactions | continuous | `utxoracle-whale-flow-detector.service` | Reads mempool API + Bitcoin Core RPC; writes to QuestDB. Depends on mempool API on :8999. |
| 2 | mempool_predictions | continuous | `utxoracle-mempool-whale-monitor.service` | ZMQ subscribe to Bitcoin Core; emit predicted whale flows. |
| 3 | net_flow_metrics | continuous | `utxoracle-flow-aggregator.service` | Aggregates whale_transactions into rolling 1h/6h/24h windows. Depends on #1. |
| 4 | entity_flows_daily | daily 02:00 UTC | `utxoracle-entity-flows-daily.timer` | Joins `address_clusters` against `utxo_lifecycle` per-day. Depends on a seeded `address_clusters` table — current dev DB has it (see `tests/test_create_tables_ddl.py`). |
| 5 | price_analysis | daily 02:15 UTC | `utxoracle-price-analysis.timer` | Compares exchange API price vs `live_snapshots.utxoracle_price` daily. |
| 6 | utxo_snapshots | daily 02:30 UTC | `utxoracle-utxo-snapshots.timer` | EOD aggregate of `utxo_lifecycle` into one row per day. Must follow utxo_lifecycle backfill (Phase 1). |
| 7 | backtest_whale_signals | manual + daily mirror | (mirror timer exists) | Operator runs `scripts/whale_flow_backtest.py` once to populate DuckDB; the existing `utxoracle-backtest-mirror.timer` then keeps QuestDB synced. |

### Per-producer template

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
  streams are those gated by upstream DuckDB freshness — see §3).

### Risks

- Producers `whale_flow_detector` and `mempool_whale_monitor` depend
  on the mempool API being stable. The mempool stack restart loop
  observed today (docker-db-1 exited) needs a separate hardening pass
  (see §3).
- `entity_flows_daily` requires `address_clusters` to be populated. If
  the test DB is empty in production, a `scripts/clustering/init_entity_registry.py`
  run is required first (manual one-shot).

### Estimated effort

- 7 producer units + tests + smoke runs: 5 working days
  (~5 h / producer).

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

### 3c. Backup strategy

- **QuestDB**: `BACKUP TABLE` for each spec-061 table daily, rsync to
  cold storage. Retention: 30 days hot, 12 months cold.
- **DuckDB**: `EXPORT DATABASE 'path/'` daily; the host disk is 60 GB so
  this is significant. Consider an incremental approach via Litestream
  or just rotating EXPORT outputs weekly with monthly retention.
- **stream_registry.yaml**: source-controlled, no separate backup
  needed.

### 3d. Source data pipeline

The single biggest production blocker right now:

- `block_heights` in DuckDB ferma a 2025-12-16. Without a fresh feeder,
  `calculate_daily_metrics` cannot produce metrics for any recent date,
  so `mvrv_daily / nupl_daily / realized_cap_daily` will report STALE
  forever.
- Investigation needed: which script previously kept block_heights
  fresh? It must be brought back online OR replaced with a Bitcoin Core
  RPC walker that maintains it.

Concrete deliverable: `scripts/bootstrap/block_heights_catchup_via_rpc.py`
that walks Bitcoin Core blocks from `max(block_heights.timestamp)+1` to
tip and writes (height, timestamp) to DuckDB. Idempotent. Run hourly via
timer.

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

New script `scripts/observe_ws_load.py` that connects to each WS
endpoint as a synthetic client and records:

- `ws_concurrent_connections` (poll via psutil on uvicorn process)
- `ws_messages_per_second` (count receives in a 60 s window)
- `ws_message_size_bytes_p95`
- `ws_cpu_utilization` (per-process)

Run for 1 h during peak. Write the numbers into
`docs/WS_BASELINE_2026-06.md`. **Owner reviews** the numbers and picks
the path below.

### 4b. Option A — Python tuning (1 day, 3–5× gain typical)

- `pip install uvloop orjson`
- Replace the broadcast loop:

  ```python
  import orjson

  async def broadcast(self, message: dict):
      if not self.active_connections:
          return
      payload = orjson.dumps(message)
      await asyncio.gather(
          *(ws.send_bytes(payload) for ws in self.active_connections),
          return_exceptions=True,
      )
  ```

- Configure uvicorn with `--loop uvloop --http httptools`.
- Re-measure after deploy. If the new numbers fit the SLA, stop here.

**When to choose**: < 100 concurrent connections, p99 latency
acceptable, simple op model preferred.

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
| 1. Stabilize | 1–2 d | Code + Operator | none |
| 2. Producers | 1 wk | Code | mempool stack, address_clusters seed |
| 3. Hardening | 1 wk | Code + Operator | Grafana access |
| 4. WS perf | 1 d → up to 4 wk | Code | measurement first |

Total to "everything green in production": **2–3 weeks** assuming the
owner gives the missing ground-truth answers in §0.

---

## 7. Sign-off checklist

Before any code work starts, the owner should confirm:

- [ ] Target deployment host (this dev box, separate, k8s, etc.)
- [ ] Alerting channel (Discord webhook URL, PagerDuty, etc.)
- [ ] Backup destination (S3 bucket name, local disk path)
- [ ] Expected p95 WS concurrent connections
- [ ] BRK on :7071: keep, restart, or repoint to remote
- [ ] DuckDB `block_heights` upstream: who/what restores it?
- [ ] Phase 2 / Phase 3 ordering: parallel or sequential?

Once these are settled, Phase 1 can start immediately; Phase 2 follows
the day after.
