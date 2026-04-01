# Tasks: spec-047 Whale Surface Unification & Entity Foundations

**Input**: design documents from `/specs/047-whale-entity-surface-unification/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or schema task

---

## Phase 1: Surface Inventory

- [x] T001 Inventory all current `/api/whale/*` routes and payloads
- [x] T002 Mark canonical, placeholder, and legacy whale routes
- [x] T003 Choose the retained canonical route family
- [x] T004 Document route conflicts and deprecation candidates

**Checkpoint**: the namespace conflict is explicit before implementation.

---

## Phase 2: Canonical Schema

- [ ] T005 Define canonical `whale_event` schema
- [ ] T006 Define canonical summary response schema
- [ ] T007 Define canonical transaction drill-down schema
- [ ] T008 Define optional entity enrichment fields with provenance/confidence

**Checkpoint**: route cleanup targets one stable payload family.

---

## Phase 3: Route Unification

- [ ] T009 [E] Rework existing whale query routes to conform to the canonical schema
- [x] T010 Remove or deprecate `/api/whale/latest`
- [x] T011 Remove or deprecate `/api/whale/historical`
- [x] T012 Remove or deprecate `/api/whale/history`
- [x] T013 Add explicit deprecation metadata where temporary compatibility is needed

**Checkpoint**: `/api/whale` tells one product story.

---

## Phase 4: Entity Foundations

- [ ] T014 Define entity registry schema with `entity_id`, provenance, and confidence
- [ ] T015 Define observed-vs-inferred field policy for whale responses
- [ ] T016 Add optional enrichment path from clustering/label data into whale events
- [ ] T017 Document omission behavior when entity enrichment is unavailable

**Checkpoint**: future entity work has a stable base without overcommitting attribution.

---

## Phase 5: Contract and Provenance Update

- [x] T018 Update spec-044 contract registry for whale surfaces
- [x] T019 Update spec-045 provenance manifest for whale surfaces
- [x] T020 Publish consumer guidance for canonical whale routes and deprecated aliases

Execution note:

- `M4a` is complete: `/api/whale/{transactions,summary,transaction/{txid}}` is the frozen canonical family.
- Legacy `/api/whale/{latest,historical,history}` routes remain only as explicit `410 Gone` migration stubs.
- Canonical event/entity schema work remains open for `M4b`.

**Checkpoint**: the unified whale surface is reflected in contract and ops docs.
