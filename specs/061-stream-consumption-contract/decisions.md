# spec-061 - Decision Record

**Branch**: `061-stream-consumption-contract`
**Status**: Final
**Audience**: future maintainers, the `nautilus_dev` consumer team, the
`/speckit.implement` reviewer.

This document captures the durable, irreversible-on-a-week-scale
decisions taken while implementing the stream consumption contract.
Reversibility for each decision is graded so that a future maintainer
can see the cost of revisiting it.

---

## D1 - Backend target = QuestDB single-tenant via PG-wire

**Issue #8 item 3**; satisfies FR-008.

**Decision**: every entry in `docs/contracts/stream_registry.yaml` is
backed by a **QuestDB table reached over the PG-wire port (`:8812`)**
and exposed to the consumer through the existing FastAPI surface in
`api/main.py` with the existing `auth_middleware.HTTPBearer` security
dependency. There is no per-stream backend selection.

**Why**:

- *Column-store fits the shape of every probe*. The freshness endpoint
  issues 13 parallel `SELECT max(<column>) FROM <table>` queries. On a
  column-oriented store with a timestamp index this is microseconds of
  query work - the per-call cost is dominated by network RTT, which the
  same instance is already paying for the other endpoints.
- *Pool already exists*. `api/questdb_repository.py` already wires an
  asyncpg pool with `QUESTDB_POOL_MIN_SIZE=5` / `MAX_SIZE=20`. No new
  connection-management code is introduced by this spec.
- *Auth and transport are reused*. The existing public API surface
  already terminates JWT-bearer and runs behind the project's CORS and
  rate-limit middleware. Adding a parallel REST channel per stream
  would require duplicating that envelope 13x.
- *Live data already flows here*. The two streams that today report
  fresh - `live_snapshots` and `whale_transactions` - already land in
  QuestDB via the live worker and the docker-compose live stack. Daily
  aggregates land here via the new `utxoracle-daily-aggregator.timer`
  (T024 / T025). Backfilled `utxo_lifecycle` rows land here once the
  bootstrap script is invoked with `--target-backend questdb` (T034 /
  T036). One backend keeps the operational story coherent.

**Alternatives rejected**:

- *REST endpoints per stream* (e.g. `/v1/streams/<name>`): rejected.
  Duplicates the auth + JSON envelope for every stream; turns a
  single-route bug into 13 routes worth of regressions; gives the
  consumer 13 surfaces to poll instead of one.
- *Versioned Parquet on a shared volume*: rejected. No atomic
  transactional contract for the daily aggregator's writes; the consumer
  would need to learn the partition layout; doesn't match `nautilus_dev`'s
  consumer model which is request/response over PG-wire or REST.
- *Mixed backends per stream*: rejected. The consumer cannot adapt to
  "it depends per stream"; the contract document is explicit that one
  uniform health surface is required.

**Reversibility**: low cost. The registry's `table` field is the only
binding to QuestDB names. To switch the backend wholesale would mean
(a) standing up the new store, (b) replaying the producer paths,
(c) rewriting `api/routes/streams.py` to dispatch against the new probe,
(d) bumping `schema_version` per FR-009 with the 30-day window. Days of
work, not weeks; not blocked by any consumer change.

---

## D2 - Per-stream freshness strategy (`max_ts` vs `tip_lag_blocks`)

Satisfies FR-011 against the regression mode that originally motivated
Issue #8.

**Decision**: each registry entry declares a `freshness_strategy` field
with one of two values:

- `max_ts` (default; 12 of 13 streams) - `stale_seconds = now() - max(timestamp_column)`.
- `tip_lag_blocks` (`utxo_lifecycle_full` only) - `stale_seconds = (getblockcount() - max(block_column)) * 600`.

The default would have been to apply `max_ts` everywhere. The exception
is necessary because `utxo_lifecycle.ts` is the **row-creation time** in
the backfill loop, not the data-time of the underlying block. During a
backfill the script writes today's `ts` for a row representing a block
150 days behind tip - `max(ts)` would silently report `OK` while the
actual data lag is ~22k blocks. That is exactly the silent-stale-failure
class Issue #8 asked us to eliminate.

**Why this design, not "fix the producer"**:

- *Producer rewrite is destructive*. Mutating `utxo_lifecycle.ts` to
  carry block-time would require schema migration over a 164M-row table
  + reindex. Days of operational downtime against a feature the consumer
  reads opportunistically. The per-stream strategy buys the same
  correctness for hours of work.
- *Generality*. Any future stream whose `ts` is "when we wrote it" can
  add `freshness_strategy: tip_lag_blocks` without further surface
  changes.

**Reversibility**: free. The strategy lives in the YAML registry; a
breaking change to it is a `behavioral_tightening` per
`docs/SCHEMA_VERSIONING.md` and triggers a MINOR bump on the affected
entry.

**Cross-references**: research.md R7 revised; data-model.md
`freshness_strategy` field; `api/routes/streams.py::_probe_stream`
dispatch.

---

## D3 - `backtest_whale_signals` mirror (DuckDB -> QuestDB)

Satisfies FR-008 for the one stream whose producer is not yet wired to
QuestDB.

**Decision**: the producer `scripts/whale_flow_backtest.py` continues to
write DuckDB only. A new timed job
(`scripts/metrics/mirror_backtest_whale_signals.py` invoked by
`utxoracle-backtest-mirror.timer` at 03:00 UTC) reads the DuckDB rows,
converts the `timestamp BIGINT` column to a UTC `TIMESTAMP`, and writes
into the new `backtest_whale_signals` QuestDB table (DDL added by T022,
WAL + DEDUP UPSERT KEYS(ts)).

**Why a mirror, not a producer rewrite**:

- *Out of scope for spec-061*. Rewriting the backtest producer is a
  cross-cutting change against spec-016 and its callers. Owning that
  inside spec-061 would inflate the diff and delay the consumer.
- *Strangler-fig*. The mirror lets us flip the consumer over now; the
  producer can be migrated later without touching the contract.
- *SLA budget allows it*. The stream's SLA is 168h (see D4); a daily
  mirror leaves a 24h margin against the 48h floor we'd otherwise need.

**Reversibility**: free. Once a producer rewrite lands, the mirror unit
is disabled with one `systemctl disable` and the script is removed.

**Cross-references**: research.md R8; tasks T022 (DDL), T026a (script),
T026b (test), T026c (timer).

---

## D4 - `backtest_whale_signals` SLA = 168h (7 days)

Resolves spec.md Clarifications Q3 (session 2026-05-31).

**Decision**: `sla_seconds: 604800` for `backtest_whale_signals` in the
registry. The source contract (PR #146) leaves the SLA unspecified for
this stream.

**Why 168h, not 48h**:

- *Workload class*. Backtest signals are research-batch output, not
  live-decision input. The consumer reads them as priors for replicable
  backtests, not for execution gates.
- *Cadence alignment*. The internal research review cycle is weekly. A
  168h SLA matches the cadence and avoids forcing daily re-runs that
  would not change downstream decisions.
- *Producer cost*. A daily re-run produces near-identical rows; weekly
  cadence respects the producer's compute envelope.

**Reversibility**: free. SLA tuning is a config knob, not a schema
change (per `docs/SCHEMA_VERSIONING.md`). The consumer team can
negotiate down (to 48h or 24h) without a version bump.

---

## D5 - No in-process cache of stream readings

Satisfies FR-011 (transparency over hidden recovery).

**Decision**: the freshness endpoint recomputes every stream's verdict
on every request - no module-level cache of `StreamHealthReading` values,
no TTL gate that would mask a STALE -> OK transition during recovery.

Only the **Bitcoin Core tip** is cached, with a 60-second TTL
(`_TIP_CACHE` in `api/routes/streams.py`). The tip changes ~every 10
minutes and the cache exists purely to bound RPC load when many polls
arrive within the same minute.

**Why**:

- *FR-011 explicitly forbids hiding the real state.* A 30-second cache
  would mean a stream that just recovered still reports STALE for up to
  30 more seconds; a backend that just failed continues to report OK
  for the same window. Both are silent staleness, which is the failure
  mode this entire spec exists to eliminate.
- *Cost is low*. Each probe is microseconds at the column store; with
  the asyncpg pool the per-poll cost is well inside the 500ms p95
  budget.

**Reversibility**: free. A cache could be added later if metrics show
QuestDB load is dominated by these polls; doing so would require
articulating against FR-011 in a new decision record.

**Cross-references**: research.md R1; FR-011; spec.md "Edge Cases".

---

## D6 - Stream-level `MISSING` covers both empty-table and backend-down

Resolves spec.md Clarifications Q2 (session 2026-05-31).

**Decision**: when a stream's probe returns `None` (empty table) OR
raises (backend unreachable / query timeout / permission denied), the
stream's status is `MISSING`. The optional `error` field carries the
exception class name when the cause is a backend failure; it is null
when the cause is an empty table. The consumer's downstream decision is
identical in both cases (block strict-mode).

**Why not a 4th status `ERROR`**:

- *Equivalent consumer action*. The consumer branches on `overall != OK`;
  it never distinguishes ERROR from MISSING at the gating layer.
- *Simpler response model*. Three statuses fit the OpenAPI enum cleanly
  and keep the consumer's adapter code tighter.
- *Diagnostics are preserved*. The optional `error` field gives the
  operator (not the consumer) what they need to root-cause.

**Reversibility**: a future spec could promote `error`-bearing streams
to a 4th status `ERROR` without breaking the existing `OK/STALE/MISSING`
contract - that would be `additive_pinned` per the versioning policy
(MINOR bump only).

**Cross-references**: spec.md Clarifications Q2; OpenAPI schema in
`contracts/streams_health.openapi.yaml`; `api/routes/streams.py::_probe_stream`.

---

## Decisions intentionally not made here

These belong to future specs or are kept out of scope to keep this one
shippable:

- **In-process Prometheus metrics for the route itself**. Logged today
  (T016), Prometheus surface defers to whatever spec-059 exposes next.
- **Multi-backend serving** (REST + QuestDB simultaneously). Out of
  scope per FR-008.
- **Producer rewrite for `backtest_whale_signals`** to write QuestDB
  directly. Tracked against spec-016 as a future enhancement; the
  mirror in D3 makes the contract green today.
- **Schema migration for `utxo_lifecycle.ts`** to carry block-time
  instead of row-creation-time. Tracked against spec-017; the
  per-stream strategy in D2 makes the contract green today.

---

## Audit references

- spec.md: FR-008, FR-009, FR-011, Clarifications session 2026-05-31
- research.md: R1, R5, R7, R8, R9
- plan.md: Constitution Check, Technical Context, Structure Decision
- docs/SCHEMA_VERSIONING.md: change classes, deprecation windows
- gptcompany/nautilus_dev PR #146: source contract
- gptcompany/UTXOracle Issue #8: closure ritual
