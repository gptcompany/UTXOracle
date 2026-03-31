# Tasks: spec-041 QuestDB Operational Convergence & API Boundary

**Input**: design documents from `/specs/041-questdb-operational-convergence/`
**Prerequisites**: `spec.md`, `plan.md`

**Organization**: tasks are grouped by architecture boundary, migration, and deprecation work.

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration change

---

## Phase 1: Inventory

- [ ] T001 Export and review the full `8011` OpenAPI route list
- [ ] T002 Build a route inventory document: production vs legacy vs research
- [ ] T003 Mark every route that still reads DuckDB directly
- [ ] T004 Mark every route that currently returns placeholder data, `501`, or mock values
- [ ] T005 Define the production route set that must survive on `8011`
- [ ] T006 Create a `PROD_ROUTE_REGISTRY` document with source table, writer owner, max staleness, and empty/stale response policy for each production route family

**Checkpoint**: the live surface is fully classified before refactoring begins.

---

## Phase 2: RED Boundary Tests

- [ ] T007 Add failing tests for production app route exposure and `/health` behavior
- [ ] T008 Add failing tests proving placeholder and DuckDB-backed routes are excluded from the production app
- [ ] T009 Add failing tests for parity CLI and dual-read divergence reporting on retained route families

**Checkpoint**: production-boundary behavior is tested before runtime refactoring starts.

---

## Phase 3: Production App Split

- [ ] T010 [E] Create a dedicated production app module for `8011`
- [ ] T011 Move `/api/v1/live/*` and production `/health` behavior into the new production app
- [ ] T012 Move legacy and research-only routes behind a separate app or clearly isolated router tree
- [ ] T013 Update Docker Compose to boot the production app instead of mixed `api.main:app`
- [ ] T014 Update systemd service definitions to make `8001` explicitly legacy or disabled

**Checkpoint**: `8011` no longer boots the mixed legacy surface.

---

## Phase 4: Parity and Dual-Read

- [ ] T015 Define per-route numerical parity tolerances for retained production route families, starting with `<0.1%` for price series and `<2%` for complex derived metrics unless explicitly overridden
- [ ] T016 Implement a parity CLI comparing QuestDB outputs vs DuckDB research baselines over at least 7 days
- [ ] T017 Implement temporary dual-read or dual-compute monitoring for migrating route families
- [ ] T018 Run parity and dual-read checks for all retained route families and record unresolved divergences

**Checkpoint**: production cutover is blocked until parity passes.

---

## Phase 5: QuestDB Convergence

- [ ] T019 [E] For each surviving route, map the QuestDB source table and writer/backfill owner
- [ ] T020 Implement or repair QuestDB ingestion for retained price comparison endpoints
- [ ] T021 Implement or repair QuestDB ingestion for retained whale endpoints
- [ ] T022 Implement or repair QuestDB ingestion for retained operational metric endpoints
- [ ] T023 Define historical backfill requirements and fill historical gaps for all retained route families
- [ ] T024 Tune QuestDB connection-pool and concurrency settings for concurrent API/chart/trading reads
- [ ] T025 Remove DuckDB reads from all retained production routes
- [ ] T026 Add empty-state and stale-state semantics for every retained production dataset

**Checkpoint**: every route still on `8011` is QuestDB-backed and operationally owned.

---

## Phase 6: Deprecation

- [ ] T027 Remove unsupported placeholder routes from the production app
- [ ] T028 Move DuckDB-backed research routes behind the legacy app
- [ ] T029 Add deprecation notices for removed or moved routes
- [ ] T030 Decide and implement final behavior for `8001`: retired, renamed, or manual-only

**Checkpoint**: no ambiguous production/legacy overlap remains.

---

## Phase 7: Documentation and Verification

- [ ] T031 Update `README.md` to describe `8011` as the canonical API
- [ ] T032 Update `docs/ARCHITECTURE.md` with the new app/storage boundary
- [ ] T033 Update `docs/LIVE_STACK_ROLE_MATRIX.md` and runbooks with the new port policy
- [ ] T034 Add a route support matrix documenting production-backed endpoints and their QuestDB sources
- [ ] T035 Run targeted tests, parity checks, and smoke checks against the production app

**Checkpoint**: runtime, docs, and route inventory all agree.

---

## Success Gate

This spec is complete only when:

1. `8011` serves only QuestDB-backed production routes
2. no production route performs synchronous DuckDB reads
3. `8001` is no longer presented as the main API
4. retained route families pass the parity gate
5. documentation and deployment assets match the actual runtime
