# Design: Materialization and Security

Date: 2026-04-07
Spec: spec-053

## 1. Materialization Scope (QuestDB)

To support low-latency consumer lookups, the following artifacts will be materialized from the local authoritative source (DuckDB/Curated files) into QuestDB.

### 1.1 `entity_registry_serving`
Collapsed view for API lookup.
- `entity_id` (SYMBOL INDEX)
- `entity_id_aliases_json` (STRING)
- `entity_kind` (SYMBOL)
- `registry_status` (SYMBOL)
- `display_label` (SYMBOL)
- `cluster_confidence` (DOUBLE)
- `mapping_confidence` (DOUBLE)
- `label_confidence` (DOUBLE)
- `confidence_overall` (DOUBLE)
- `first_seen` (TIMESTAMP)
- `last_seen` (TIMESTAMP)
- `source_status` (SYMBOL)
- `ts` (TIMESTAMP - materialization time)

### 1.2 `entity_provenance_serving`
Collapsed provenance summary for metadata APIs.
- `entity_id` (SYMBOL INDEX)
- `provenance_summary_json` (STRING)
- `primary_source_kind` (SYMBOL)
- `review_status` (SYMBOL)
- `ts` (TIMESTAMP - materialization time)

### 1.3 `entity_flows_daily`
Daily net and gross flows.
- `entity_id` (SYMBOL INDEX)
- `date` (TIMESTAMP)
- `inflow_btc` (DOUBLE)
- `outflow_btc` (DOUBLE)
- `netflow_btc` (DOUBLE)
- `is_exchange` (BOOLEAN)
- `ts` (TIMESTAMP - materialization time)

### 1.4 `entity_balance_snapshots_daily`
Historical balance tracking.
- `entity_id` (SYMBOL INDEX)
- `date` (TIMESTAMP)
- `balance_btc` (DOUBLE)
- `ts` (TIMESTAMP - materialization time)

### 1.5 `entity_counterparty_edges_daily`
Serving-grade aggregate flow rows for `/api/entities/*/flows`.
- `window_start` (TIMESTAMP)
- `window_end` (TIMESTAMP)
- `source_entity_id` (SYMBOL INDEX)
- `target_entity_id` (SYMBOL INDEX)
- `movement_classification` (SYMBOL)
- `btc_amount` (DOUBLE)
- `attribution_confidence` (DOUBLE)
- `is_internal` (BOOLEAN)
- `materialization_status` (SYMBOL)
- `ts` (TIMESTAMP - materialization time)

Raw `entity_movement_events` and `entity_transfer_edges` remain local-authoritative and research-first unless a later slice explicitly admits them to the serving plane.

## 2. Writer and Backfill Jobs

- **Registry Sync**: `scripts/bootstrap/sync_entities_to_questdb.py`
    - Idempotent sync of local entity registry and provenance summaries to QuestDB.
    - Triggered daily or after clustering batch.
- **Flow Aggregator**: `scripts/live/flow_aggregator.py`
    - Computes daily aggregates from local authoritative registry/clustering artifacts and `utxo_lifecycle`.
    - Produces local authoritative movement/aggregate artifacts that are later materialized to QuestDB by `scripts/bootstrap/sync_entities_to_questdb.py`.
- **Backfill Order**:
    - Local registry/backfill must run before flow aggregation so aggregate rows use stable canonical `entity_id` values; QuestDB materialization can follow after local artifacts are consistent.

## 3. Freshness and Failure Vocabulary

- **Freshness Target**: 24h (aligned with daily clustering).
- **Metadata Lookup States**:
    - `not_found`: no registry row exists after canonicalizing the supplied identifier or read-only alias.
    - `ambiguous`: the supplied lookup key expands to multiple candidate entities; do not coerce to one result.
    - `stale`: `ts` (materialization time) is > 48h old.
    - `degraded`: a registry row exists but component confidence, provenance summary, or sync inputs are incomplete.
- **Flow Query States**:
    - `empty`: bounded query returns no rows; return `200 OK` with `items: []`.
    - `partial_materialization`: the requested window is only partially materialized; return partial rows and make the status explicit.
    - `ambiguous`: unresolved counterparty/entity attribution remains explicit in row classification and must not be coerced into directional certainty.

Metadata routes should expose typed `source_status`. Flow routes should expose a top-level query status plus row-level `materialization_status` when partial windows are returned.

## 4. Security Posture

### 4.1 Host Policy
- **Serving-Grade Target (`:8011`)**: Materialized entity metadata and aggregate flow routes are candidates for `:8011` only after Phase 7 freezes route families and spec-044/spec-045 governance artifacts are updated.
- **Research Plane (`:8001`)**: Raw movement events, unverified heuristics, and other exploratory forensics remain on `:8001`.

### 4.2 Auth and Rate Limiting
- **`:8011`**: No authentication required for admitted public GET forensic routes (matching whale baseline). Rate limited at 100 req/min per IP.
- **`:8001`**: Standard internal auth requirement for research endpoints.

### 4.3 Input Validation
- `entity_id` path/query input accepts canonical `btc:entity:*` identifiers plus the legacy read-only alias `cluster:*`; reject unknown namespaces and identifiers longer than 256 characters.
- Aggregate flow queries on `:8011` must use bounded windows only; reject open-ended scans and cap the maximum query window at 366 days.
- Pagination and list limits must be explicit and bounded; default to a small limit and reject values above 500.
- Filters and sort keys must be allowlisted; do not accept free-form query fragments.
