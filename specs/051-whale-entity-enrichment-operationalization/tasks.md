# Tasks: spec-051 Whale Entity Enrichment Operationalization

**Input**: design documents from `/specs/051-whale-entity-enrichment-operationalization/`
**Prerequisites**: `spec.md`, `plan.md` (implicit)

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or schema task

---

## Phase 1: Schema Verification & Wiring

- [x] T001 Verify QuestDB schema requirements for `address_clusters` match `api.questdb_repository` expectations.
- [x] T002 Ensure `QuestDBRepository` has the necessary bulk-insert or ILP methods for `address_clusters`.
- [x] T003 Ensure `api/mempool_whale_endpoints.py` correctly handles missing `address_clusters` table gracefully during bootstrap.

**Checkpoint**: The QuestDB serving plane is ready to receive and serve cluster data.

---

## Phase 2: Historical Backfill

- [x] T004 Create `scripts/bootstrap/sync_clusters_to_questdb.py` to read `address_clusters` from DuckDB.
- [x] T005 Implement batching logic to handle large cluster datasets efficiently (e.g., chunks of 100k rows).
- [x] T006 Write formatted data to QuestDB via ILP or Postgres bulk insert.
- [x] T007 Add logging and error handling for incomplete or corrupted DuckDB cluster state.

**Checkpoint**: Existing DuckDB cluster data is fully replicated in QuestDB.

---

## Phase 3: Incremental Updates

- [x] T008 [E] Modify existing clustering pipeline (`scripts/clustering/address_clustering.py` or equivalent runner) to trigger `sync_clusters_to_questdb.py` upon completion.
- [x] T009 Ensure the sync script supports "upsert" or "truncate-and-load" semantics appropriate for QuestDB's time-series nature.
- [x] T010 Add integration tests verifying that new DuckDB clusters eventually appear in QuestDB.

**Checkpoint**: The data pipeline is closed: DuckDB analytics automatically populate the QuestDB serving plane.

---

## Phase 4: Validation & Docs (spec-041 closure)

- [x] T011 Run end-to-end tests against `GET /api/whale/transactions` on `:8011` to confirm `entity` enrichment is populated.
- [x] T012 Mark T021-T023 in `specs/041-questdb-operational-convergence/tasks.md` as complete.
- [x] T013 Update `docs/OPERATIONAL_RUNBOOK.md` with instructions for running and debugging the cluster sync job.
- [x] T014 Update `docs/contracts/feature_provenance_manifest.yaml` to reflect the active sync pipeline as the `writer_owner`.

**Checkpoint**: Whale entity enrichment is fully operationalized, documented, and contract-aligned.

Execution note:

- Post-close regression fix verified on 2026-04-04: the QuestDB `address_clusters` refresh path now stages and cuts over atomically enough to avoid serving a partially rebuilt table after an ILP failure; targeted pytest coverage was re-run after the fix.
