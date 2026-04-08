# Design: Materialization and Security

Date: 2026-04-07
Spec: spec-053

## 1. Materialization Scope (QuestDB)

To support low-latency consumer lookups, the following artifacts will be materialized from the local authoritative source (DuckDB/Curated files) into QuestDB.

### 1.1 `entity_registry_serving`
Collapsed view for API lookup.
- `entity_id` (SYMBOL INDEX)
- `entity_kind` (SYMBOL)
- `registry_status` (SYMBOL)
- `display_label` (SYMBOL)
- `confidence_overall` (DOUBLE)
- `last_seen` (TIMESTAMP)
- `ts` (TIMESTAMP - materialization time)

### 1.2 `entity_flows_daily`
Daily net and gross flows.
- `entity_id` (SYMBOL INDEX)
- `date` (TIMESTAMP)
- `inflow_btc` (DOUBLE)
- `outflow_btc` (DOUBLE)
- `netflow_btc` (DOUBLE)
- `is_exchange` (BOOLEAN)

### 1.3 `entity_balance_snapshots_daily`
Historical balance tracking.
- `entity_id` (SYMBOL INDEX)
- `date` (TIMESTAMP)
- `balance_btc` (DOUBLE)

## 2. Writer and Backfill Jobs

- **Registry Sync**: `scripts/bootstrap/sync_entities_to_questdb.py`
    - Idempotent sync of local entity registry to QuestDB.
    - Triggered daily or after clustering batch.
- **Flow Aggregator**: `scripts/live/flow_aggregator.py`
    - Computes daily aggregates from DuckDB `utxo_lifecycle` and `address_clusters`.
    - Writes to QuestDB.

## 3. Freshness and Failure Vocabulary

- **Freshness Target**: 24h (aligned with daily clustering).
- **Stale State**: If `ts` (materialization time) is > 48h old, API returns `service_status: "stale"`.
- **Degraded State**: If a subset of clusters for an entity failed to sync, returns `service_status: "degraded"`.
- **Empty State**: Returns `200 OK` with `items: []` and `service_status: "empty"` if tables are unpopulated.

## 4. Security Posture

### 4.1 Host Policy
- **Production Plane (`:8011`)**: Exposes `/api/entities/{id}` and `/api/entities/flows` (materialized).
- **Research Plane (`:8001`)**: Exposes raw movement events and unverified heuristics.

### 4.2 Auth and Rate Limiting
- **`:8011`**: No authentication required for public GET forensic routes (matching whale baseline). Rate limited at 100 req/min per IP.
- **`:8001`**: Standard internal auth requirement for research endpoints.
