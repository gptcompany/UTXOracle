# Tasks: spec-048 Implemented Route Hardening

**Input**: design documents from `/specs/048-implemented-route-hardening/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex route or metric hardening task

---

## Phase 1: RED Trustworthiness Tests

- [x] T001 Add failing tests proving `PRO Risk` currently uses mocked component inputs
- [x] T002 Add failing tests proving `PRO Risk` history currently returns empty data
- [x] T003 Add failing tests proving `Puell Multiple` currently depends on hardcoded baseline constants
- [x] T004 Add failing tests proving `/api/v1/models/power-law/predict` is shadowed by generic route order
- [x] T005 Add failing tests or route-table assertions for live router exposure policy

**Checkpoint**: implementation debt is locked by tests before refactoring.

---

## Phase 2: Keep vs Demote Decisions

- [x] T006 Decide keep-vs-demote for `PRO Risk`
- [x] T007 Decide keep-vs-demote for `Puell Multiple`
- [x] T008 Decide canonical host policy for `/api/v1/live/*`
- [x] T009 Decide technical fix for power-law route order

**Checkpoint**: implementation effort is aligned to product intent.

---

## Phase 3: Implementation

- [x] T010 [E] Wire real inputs and history into `PRO Risk`, or move it behind a demoted/experimental contract
- [x] T011 [E] Replace hardcoded Puell baseline with real historical issuance inputs, or demote the route
- [x] T012 Fix `/api/v1/models/power-law/predict` so the intended handler wins deterministically
- [x] T013 Remove, isolate, or explicitly support duplicate live route exposure on `:8001`

**Checkpoint**: implemented routes no longer rely on documented caveats alone.

---

## Phase 4: Registry and Provenance Update

- [x] T014 Update spec-044 contract entries for hardened or demoted routes
- [x] T015 Update spec-045 provenance entries for hardened or demoted routes
- [x] T016 Update route caveat notes in docs to reflect resolved vs unresolved issues

**Checkpoint**: implementation and contract artifacts agree.

---

## Phase 5: Verification

- [x] T017 Run targeted tests for `PRO Risk`, `Puell Multiple`, models routing, and live host exposure
- [x] T018 Verify route table behavior after routing changes
- [x] T019 Verify final admitted status for all hardened route families

Execution note:

- `M2` was completed through direct hardening and runtime-demotion work.
- The original RED-only historical proof tasks `T001`-`T004` were not preserved as separate failing test artifacts after the implementation path was chosen.
- The checklist is therefore closed administratively against the final hardened state and retained regression coverage, not against preserved standalone RED snapshots.

**Checkpoint**: runtime behavior and documentation are aligned.
