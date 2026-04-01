# Tasks: spec-044 Feature Service Contract Registry

**Input**: design documents from `/specs/044-feature-service-contract-registry/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex cross-document or validation task

---

## Phase 1: Schema

- [x] T001 Define the registry entry schema and required fields
- [x] T002 Define admission tiers distinct from audit labels
- [x] T003 Define versioning and deprecation semantics for admitted surfaces
- [x] T004 Create `docs/contracts/feature_contract_registry.yaml`

**Checkpoint**: one machine-readable registry shape exists.

---

## Phase 2: Baseline Population

- [x] T005 Export the current route families from the roadmap prep document into the registry
- [x] T006 Assign `current_label` for each route family
- [x] T007 Assign `admission_tier` for each route family
- [x] T008 Add known caveats for `PRO Risk`, `Puell Multiple`, route shadowing, and duplicate live exposure
- [x] T009 Add owner and backend fields for every admitted family

**Checkpoint**: the registry reflects current reality, not desired future state.

---

## Phase 3: First Consumer Contract

- [x] T010 Define the first admitted `nautilus_dev` feature slice
- [x] T011 Create `docs/NAUTILUS_FEATURE_CONTRACT_V1.md`
- [x] T012 Mark excluded or caveated route families explicitly
- [x] T013 Add migration notes for future contract expansion

**Checkpoint**: a downstream consumer can use one document as the contract source.

---

## Phase 4: Validation

- [ ] T014 [E] Add a validator that fails on missing required fields in the YAML registry
- [ ] T015 Add consistency checks between YAML registry and contract markdown
- [x] T016 Verify every `tier_1_production` or `tier_2_production_with_caveats` entry has freshness and stale-state semantics

**Checkpoint**: the registry can be trusted as an operational artifact.

---

## Phase 5: Documentation

- [x] T017 Publish `docs/FEATURE_CONTRACT_REGISTRY.md`
- [x] T018 Link the contract registry from roadmap and Nautilus integration docs
- [x] T019 Document how new specs must update contract state when surfaces change

**Checkpoint**: the registry is part of the normal workflow, not a one-off document.
