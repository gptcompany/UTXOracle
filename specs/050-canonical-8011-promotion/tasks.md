# Tasks: spec-050 Canonical 8011 Promotion for QuestDB-Backed Families

**Input**: design documents from `/specs/050-canonical-8011-promotion/`
**Prerequisites**: `spec.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or boundary change

---

## Phase 1: Promotion Slice Freeze

- [ ] T001 Freeze the promotion slice to `/api/prices/*`, `/api/metrics/latest`, and canonical whale routes only
- [ ] T002 Freeze the non-goals: no DuckDB metric families, no Wave 1 route promotion, no macro-metric reopening
- [ ] T003 Record current read-path owners and QuestDB tables for the promoted slice

**Checkpoint**: the slice is narrow before implementation begins.

---

## Phase 2: RED Boundary Tests

- [ ] T004 Add failing tests proving the production app on `8011` exposes `/api/prices/*`
- [ ] T005 Add failing tests proving the production app on `8011` exposes `/api/metrics/latest`
- [ ] T006 Add failing tests proving the production app on `8011` exposes canonical whale routes
- [ ] T007 Add failing tests for migration/deprecation behavior on `8001` once a family is promoted
- [ ] T008 Add failing tests proving no DuckDB-backed family is accidentally admitted by this promotion

**Checkpoint**: the expansion is constrained by tests.

---

## Phase 3: Production-App Serving

- [ ] T009 [E] Add production-app routers or handlers for `/api/prices/*`
- [ ] T010 [E] Add production-app handler for `/api/metrics/latest`
- [ ] T011 [E] Add production-app router or handler for canonical whale routes
- [ ] T012 Freeze route-level empty, stale, and degraded semantics for the promoted slice on `8011`
- [ ] T013 Preserve whale entity omission semantics during promotion

**Checkpoint**: the promoted slice is available on `8011` without weakening boundary rules.

---

## Phase 4: Legacy Host Migration Policy

- [ ] T014 Decide exact migration behavior for `8001`: deprecation headers, metadata, or explicit legacy alias docs
- [ ] T015 Implement `8001` migration behavior for `/api/prices/*`
- [ ] T016 Implement `8001` migration behavior for `/api/metrics/latest`
- [ ] T017 Implement `8001` migration behavior for canonical whale routes

**Checkpoint**: `8001` is secondary, not ambiguous.

---

## Phase 5: Contract and Docs Alignment

- [ ] T018 Update spec-044 contract registry to move the promoted slice canonical host to `8011`
- [ ] T019 Update spec-045 provenance manifest to reflect `8011` production read paths
- [ ] T020 Update architecture, scope-lock, and disposition docs for the new canonical host policy
- [ ] T021 Update any consumer-facing docs that still describe `8001` as canonical for the promoted slice

**Checkpoint**: runtime and docs tell the same story.

---

## Phase 6: Verification

- [ ] T022 Run targeted tests for the promoted production routes on `8011`
- [ ] T023 Run smoke verification that DuckDB-backed research families remain absent from `8011`
- [ ] T024 Verify final `8001` migration behavior for the promoted slice

**Checkpoint**: `8011` gains real consumer breadth without reopening the mixed-surface problem.
