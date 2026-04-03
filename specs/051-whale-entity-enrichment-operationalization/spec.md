# spec-051: Whale Entity Enrichment Operationalization

> **Status**: CLOSED
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-03
> **Closed**: 2026-04-03

## Problem Statement

The canonical whale surface on port `:8011` (established in `spec-047`) supports best-effort entity enrichment by querying the `address_clusters` table in QuestDB. However, the existing address clustering pipeline (`spec-013`) and bootstrap scripts write cluster assignments to DuckDB. 

This storage boundary mismatch means the live production API currently degrades to omission (returning `null` for entities) because the QuestDB `address_clusters` table is either unpopulated or statically mocked. We have the heuristics (MIH, CAH, CoinJoin detection), but we lack the operational wiring to serve their output on the canonical host.

## Goals

1. Bridge the storage gap between the DuckDB clustering pipeline and the QuestDB serving plane.
2. Implement a historical backfill workflow to migrate existing `address_clusters` from DuckDB to QuestDB.
3. Define an incremental update mechanism (or daily sync) to keep the QuestDB `address_clusters` table fresh as new blocks are processed.
4. Fulfill the outstanding QuestDB convergence tasks (T021-T023 from `spec-041`).

## Non-Goals

- Reinventing clustering heuristics (MIH, CAH, CoinJoin are already solved in `spec-013`).
- Altering the canonical whale event schema (`whale_event.v1` is frozen in `spec-047`).
- Real-time (sub-block) cluster updates (batch/daily sync is sufficient for entity forensics).

## Dependencies

- **spec-013**: Address Clustering & CoinJoin Detection (Source of clustering logic and DuckDB state).
- **spec-041**: QuestDB Operational Convergence (Target serving infrastructure).
- **spec-047**: Whale Entity Surface Unification (Consumer of the enriched data).

## Design

### 1. QuestDB Schema Verification

The target table in QuestDB must support the `whale_event.v1` enrichment fields.
```sql
CREATE TABLE IF NOT EXISTS address_clusters (
    address SYMBOL INDEX,
    cluster_id SYMBOL INDEX,
    label SYMBOL,
    is_exchange_likely BOOLEAN,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    confidence DOUBLE
)
```
*(Note: Schema must be verified against current `api.questdb_repository` expectations).*

### 2. Historical Backfill (DuckDB -> QuestDB)

A new operational script (`scripts/bootstrap/sync_clusters_to_questdb.py`) is required to:
1. Read the finalized `address_clusters` table from DuckDB.
2. Format the data for QuestDB InfluxDB Line Protocol (ILP) or PostgreSQL bulk insert.
3. Populate the QuestDB table efficiently.

### 3. Incremental Updates

The existing clustering pipeline must be extended to either:
**Option A (Dual-Write)**: Write new cluster assignments to both DuckDB and QuestDB simultaneously.
**Option B (Daily Sync)**: A scheduled job runs the `sync_clusters_to_questdb.py` script daily (or every N blocks) after the DuckDB clustering batch completes.

*Decision*: **Option B (Daily Sync)** is strongly preferred to maintain the separation of concerns. DuckDB remains the analytical/compute plane, and QuestDB remains the read-optimized serving plane.

### 4. Failure Semantics & Freshness

- **Freshness Target**: Latest successful sync from DuckDB (typically daily or weekly depending on clustering batch cadence).
- **Stale State**: If QuestDB `address_clusters` is not updated, the whale API will continue to serve stale labels (acceptable for forensics) or omit new entities (graceful degradation).
- **Empty State**: If the sync fails completely, the API degrades to base `whale_event.v1` without `entity` fields (already handled by `spec-047`).

## Success Criteria

1. The `address_clusters` table in QuestDB is fully populated with real data from the DuckDB pipeline.
2. `GET /api/whale/transactions` on `:8011` successfully returns populated `entity` objects for known clusters.
3. The sync pipeline is documented in the operational runbook.
