# Feature Specification: Stream Consumption Contract for nautilus_dev

**Feature Branch**: `061-stream-consumption-contract`
**Created**: 2026-05-31
**Status**: Final (post-clarify, post-analyze remediation)
**Input**: Issue #8 — nautilus_dev integration: Consumption contract for 10 onchain streams + ops remediation. Source: gptcompany/nautilus_dev PR #146 (`specs/089-utxoracle-live-context-integration/feature-request-2026-05-29.md`).

## Clarifications

### Session 2026-05-31

- Q: Registry shape — does the consumer expect exactly 10 stream entries, the 3 daily aggregates as separate addressable entries (= 13), or a split response? → A: 13 separate streams. The 3 daily aggregates carry their own SLA (≤48h) distinct from `price_analysis` (≤36h), so they are independent surfaces, not columns of `price_analysis`.
- Q: How should the freshness endpoint distinguish "table empty" from "backend unreachable"? → A: Both map to status `MISSING`. The endpoint MAY include an optional `error` field carrying the underlying cause for diagnostics, but the consumer's downstream decision is identical in both cases (block strict-mode).
- Q: What SLA value applies to `backtest_whale_signals` given the source contract leaves it unspecified? → A: 168h (7 days). Backtest signals are research-batch workload aligned with a weekly review cadence, not live decision input — 48h would force unjustified re-runs.

## Background

The downstream consumer `nautilus_dev` reads 10 onchain data streams from UTXOracle via its `onchain_context.py` adapter. Today those streams have no public contract: stream names are implicit, freshness is unverifiable, and silent staleness has already caused upstream regressions (`utxo_lifecycle` ~150 days behind tip, `mvrv_daily`/`nupl_daily`/`realized_cap_daily` 5 months stale, `utxo_snapshots` empty). Internal SLO/schema/observability infrastructure already exists (delivered by specs 056-059) but is not exposed to external consumers in a single, contractual surface.

This spec lands the thin consumer-facing adapter that turns the existing internal infrastructure into a public, versioned contract. It does not re-implement SLO, schema versioning, or observability — it adapts them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Consumer gates strict-mode runs on overall freshness (Priority: P1)

A `nautilus_dev` execution-grade run starts. Before reading the 13 onchain streams, it polls a single public endpoint to verify that every stream the strategy depends on is fresh enough to be safely consumed. If any stream is `STALE` or `MISSING`, the consumer either downgrades to research-only mode or refuses to start, instead of silently consuming stale data.

**Why this priority**: This is the entire reason Issue #8 exists. Without it, the consumer cannot distinguish "fresh enough to trade" from "5 months stale". This deliverable alone unblocks today's strict-mode runs.

**Independent Test**: A single HTTP request to the health endpoint, with a valid token, returns a JSON document listing all 13 streams with their per-stream freshness and a single rollup status. The consumer asserts `overall == "OK"` and proceeds. No other deliverable is required for this story to deliver value.

**Acceptance Scenarios**:

1. **Given** all 13 streams are within their freshness SLA, **When** the consumer polls the health endpoint, **Then** every stream reports `status: "OK"` and the rollup reports `overall: "OK"`.
2. **Given** one stream is past its SLA, **When** the consumer polls, **Then** that stream reports `status: "STALE"` with the actual `stale_seconds`, and the rollup reports `overall` as not-OK.
3. **Given** a stream's backing table is empty or unreachable, **When** the consumer polls, **Then** that stream reports `status: "MISSING"` and the rollup reports `overall` as not-OK.
4. **Given** the request carries no valid token, **When** the consumer polls, **Then** the request is rejected at the auth layer with no stream data leaked.

---

### User Story 2 — Daily aggregations stay fresh automatically (Priority: P1)

The three daily aggregates (`mvrv_daily`, `nupl_daily`, `realized_cap_daily`) are produced by a single batch script. Today that script is invoked manually and has silently regressed. After this spec lands, a scheduled job runs the aggregation every day after the underlying source data is fresh, and the resulting rows land in the consumer-visible backend within the SLA window.

**Why this priority**: Items 1 and 5 of Issue #8 are P0. Without a scheduled aggregator, the freshness contract in Story 1 cannot be satisfied for the three daily streams, and the regression mode (silent staleness) returns the moment a human forgets to run the script.

**Independent Test**: Disable the manual invocation path. Wait one scheduled cycle. The three daily streams report `status: "OK"` via the health endpoint, and the most recent row timestamp advances within 48 hours wall-clock.

**Acceptance Scenarios**:

1. **Given** the scheduled job is enabled, **When** one scheduled cycle elapses, **Then** the three daily aggregates have at least one new row each, with a timestamp at most 48 hours behind wall-clock.
2. **Given** the job has not run for more than 48 hours, **When** the consumer polls the health endpoint, **Then** the three daily streams report `status: "STALE"` — the regression is visible, not silent.

---

### User Story 3 — Schema changes never silently break the consumer (Priority: P2)

Every stream in the contract carries a `schema_version` attribute. When the producer needs to make a breaking change (rename a column, change a column's semantics), the consumer is given a minimum 30-day window during which both the old and the new schema are served, so the consumer can migrate without downtime. Additive changes (new columns) do not bump the version.

**Why this priority**: This is the durable-contract half of Issue #8 (item 4). It does not block today's strict-mode runs, but without it the freshness contract decays the first time someone refactors a column.

**Independent Test**: Inspect a single stream registry document. Confirm that each of the 13 streams declares a `schema_version`, that the soft-deprecation rule is documented, and that the consumer can read the version at connect time.

**Acceptance Scenarios**:

1. **Given** the stream registry is published, **When** the consumer reads it, **Then** every stream declares a `schema_version` and a current SLA in seconds.
2. **Given** a breaking change is proposed, **When** the change is reviewed, **Then** the review confirms a minimum 30-day overlap window is planned before the old version is retired.

---

### User Story 4 — Backend target is a single explicit choice (Priority: P2)

UTXOracle commits to one backend target for the public contract surface, documents that choice, and stops the consumer from having to guess which backend any given stream lives in.

**Why this priority**: Item 3 of Issue #8. The consumer can adapt to any backend the producer chooses, but it cannot adapt to "it depends per stream". This is a one-time decision, not ongoing work.

**Independent Test**: A single decision record names the backend, the transport, and the authentication surface. All 13 streams can be queried through that one surface.

**Acceptance Scenarios**:

1. **Given** the contract is published, **When** the consumer inspects the registry, **Then** exactly one backend is declared as the consumption surface for all streams.

---

### Edge Cases

- A stream has rows but its most recent timestamp is older than its SLA → reports `STALE` with the real `stale_seconds`, not silently `OK`.
- A stream's backing table exists but is empty → reports `MISSING`, not `OK with stale_seconds = +inf`.
- A stream's backing store is unreachable (connection lost, query timeout, transient error) → reports `MISSING` with an optional `error` field for diagnostics. The consumer treats this identically to an empty table: strict-mode blocked.
- The freshness endpoint is itself slow or unreachable → consumer treats this as a hard failure (cannot prove freshness), equivalent to `overall != OK`.
- A backfill is mid-flight: the affected stream reports its real (stale) state during the backfill. No fallback to a legacy datastore is permitted — transparency is preferred over hidden recovery.
- The downstream-consumer-tracked column set in `onchain_context.py` is the contract for what columns must keep existing. Adding columns is non-breaking. Removing or renaming is breaking and triggers Story 3's 30-day window.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST publish a single, named registry of the streams it commits to serving. The registry MUST contain exactly 13 entries: the 10 canonical streams named in the contract document, plus the 3 daily aggregates (`mvrv_daily`, `nupl_daily`, `realized_cap_daily`) that the contract's SLA table references explicitly.
- **FR-002**: For each registry entry, the system MUST declare a stream name, a current `schema_version` starting at `"1.0.0"`, a freshness SLA expressed in seconds, the backing table or surface, the columns the consumer pins (matched to `onchain_context.py`), and a reference to the internal SLO source spec.
- **FR-003**: The system MUST expose a single freshness endpoint that, on a single authenticated request, returns the current per-stream freshness for all 13 streams plus a rollup status. Per-stream payload MUST include the most recent row timestamp (UTC), the staleness in seconds, the SLA in seconds, and a status of `OK`, `STALE`, or `MISSING`. Per-stream payload MAY include an optional `error` field carrying a diagnostic message when the status is `MISSING` due to a backend failure (as opposed to an empty table); the consumer's downstream decision is identical in both cases. The rollup status MUST be `OK` only if every stream is `OK`.
- **FR-004**: The freshness endpoint MUST authenticate using the existing public-API auth surface. Unauthenticated requests MUST be rejected without leaking stream-level data.
- **FR-005**: The system MUST NOT rename any of the 13 streams once published. Renames are breaking changes under Story 3.
- **FR-006**: The system MUST NOT remove any column that the downstream consumer pins in `onchain_context.py`. Removals and semantic renames are breaking changes under Story 3. Additive columns are non-breaking.
- **FR-007**: The three daily aggregates MUST be produced by a scheduled job that runs at least once per day. The job MUST run on a schedule that, under normal operation, keeps the aggregates within 48 hours of wall-clock.
- **FR-008**: The system MUST commit to a single backend target for the public consumption surface and MUST document that choice in a single decision record. Default: a single relational backend reached via the existing public API surface.
- **FR-009**: When a breaking schema change is introduced, the system MUST serve both the old and the new schema in parallel for a minimum of 30 days, and MUST publish the deprecation window in the registry before removing the old shape.
- **FR-010**: Each stream's underlying surface MUST expose a UTC timestamp column with monotonic semantics, and a key set under which two consecutive reads with the same key yield identical rows (idempotent re-reads).
- **FR-011**: For streams whose backing data is currently behind SLA at the time this spec lands (notably `utxo_lifecycle_full` and the three daily aggregates), the freshness endpoint MUST report their real state truthfully. The system MUST NOT serve a fallback from a deprecated datastore to hide an in-flight backfill.
- **FR-012**: An automated acceptance test MUST exist that polls the freshness endpoint and asserts the rollup status is `OK`. This test MUST be part of the gate before Issue #8 is closed.

### Key Entities

- **Stream Registry**: The single, named document declaring the 13 streams the producer commits to. Carries per-stream name, version, SLA, backing surface, pinned columns, and source reference.
- **Stream Health Reading**: The per-stream snapshot returned by the freshness endpoint: name, last row timestamp, stale seconds, SLA seconds, status. Always grouped under a rollup status for the whole registry.
- **Schema Version**: A per-stream attribute that the consumer pins at connect time. Bumped only by breaking changes. Old version stays valid for 30 days minimum after a new version is announced.
- **Daily Aggregation Job**: A scheduled job that materialises the three daily aggregates from upstream source data. Owns the freshness guarantee for those three streams.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this spec lands and the operational prerequisites complete, a single authenticated request to the freshness endpoint returns rollup status `OK`, and the downstream consumer's strict-mode run starts without manual intervention.
- **SC-002**: For the 13 streams collectively, the freshness endpoint reports the real per-stream state on at least 99% of polls under normal operation — silent staleness (a stream reporting `OK` while actually past SLA) occurs in zero observed polls.
- **SC-003**: The three daily aggregates report `status: OK` on at least 99% of polls measured over a 14-day window after the scheduled aggregator is enabled.
- **SC-004**: The downstream consumer can complete a full integration check (read all 13 streams, validate schema versions, complete one strict-mode run) in under 5 minutes, without consulting an operator.
- **SC-005**: When a breaking schema change is introduced after this spec lands, the consumer has at least 30 days of overlap during which both the old and the new shape are served, and zero consumer-side breakage is observed during the overlap window.

## Assumptions

- The downstream consumer treats `overall != OK` from the freshness endpoint as a hard signal: strict-mode runs do not start, research-mode runs tag their output as research-only.
- The registry exposes exactly 13 entries (10 canonical + 3 daily aggregates as separate addressable entries). See Clarifications session 2026-05-31. The 3 daily aggregates carry independent ≤48h SLA distinct from `price_analysis` ≤36h, confirming they are independent consumption surfaces.
- The freshness measurement is `now() - max(stream_timestamp_column)`. The system clock and the data timestamp column are both UTC.
- The backend target is a single relational backend reached via the existing public API surface. Mixed backends are explicitly out of scope for this spec.
- The schema_version baseline of `"1.0.0"` reflects the shape `nautilus_dev`'s `onchain_context.py` pins on the day this spec lands. No retroactive version bumps for prior shapes.
- The operational prerequisites (catch-up backfill for `utxo_lifecycle`, dual-write of daily aggregates to the chosen backend) are tracked as blocking but are not themselves Issue #8 deliverables. Their completion is a precondition for SC-001, not an item this spec produces.
- The `backtest_whale_signals` stream is included in the 13 with SLA = 168h (7 days). Source contract is silent on this stream; the value reflects a research-batch workload aligned with a weekly review cadence. See Clarifications session 2026-05-31.

## Dependencies

- **Specs 056–059** (all `IMPLEMENTED`) provide the internal SLO classes, schema policy, and observability surface this spec adapts. Without them this spec would need to build those foundations first.
- **`docs/contracts/CHANGE_POLICY.md`** is the source of the soft-deprecation rules referenced by FR-009.
- **`docs/contracts/service_slo_and_capacity.yaml`** is the source of the internal tier_1 freshness classes referenced by the per-stream SLA values.
- **`nautilus_dev/strategies/common/flow_discovery/onchain_context.py`** is the contract for what columns must keep existing per FR-006.
- **gptcompany/nautilus_dev PR #146** is the source of the canonical stream-name list, SLA table, and schema-versioning rule.

## Out of Scope

- Multi-backend serving of the consumption contract.
- Re-implementing internal SLO, schema versioning, or observability (already delivered by specs 056-059).
- Versioning every internal helper model. Only the 13 public streams are versioned under this contract.
- Commercial SLA commitments. Only internal SLO targets apply.
- Migrating historical data from the deprecated DuckDB legacy datastore. The contract is forward-looking from the day the backfill catches up to tip.
