# Tasks: spec-047 Whale Surface Unification & Entity Foundations

**Input**: design documents from `/specs/047-whale-entity-surface-unification/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or schema task

---

## Phase 1: Surface Inventory

- [ ] T001 Inventory all current `/api/whale/*` routes and payloads
- [ ] T002 Mark canonical, placeholder, and legacy whale routes
- [ ] T003 Choose the retained canonical route family
- [ ] T004 Document route conflicts and deprecation candidates

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
- [ ] T010 Remove or deprecate `/api/whale/latest`
- [ ] T011 Remove or deprecate `/api/whale/historical`
- [ ] T012 Remove or deprecate `/api/whale/history`
- [ ] T013 Add explicit deprecation metadata where temporary compatibility is needed

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

- [ ] T018 Update spec-044 contract registry for whale surfaces
- [ ] T019 Update spec-045 provenance manifest for whale surfaces
- [ ] T020 Publish consumer guidance for canonical whale routes and deprecated aliases

**Checkpoint**: the unified whale surface is reflected in contract and ops docs.

