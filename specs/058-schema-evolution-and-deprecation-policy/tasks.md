# Tasks: spec-058 Schema Evolution and Deprecation Policy

**Input**: design documents from `/specs/058-schema-evolution-and-deprecation-policy/`
**Prerequisites**: `spec.md`, `plan.md`, `spec-054`, `spec-055`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: contract or compatibility-impacting governance change

---

## Phase 1: Change-Class Freeze

- [x] T001 Freeze the scope: execution-grade contract evolution only, not every internal helper model
- [x] T002 Freeze the execution-grade change-class vocabulary to `docs_only`, `additive_non_breaking`, `behavioral_tightening`, `breaking`, and map it to the broader `spec-044` governance terms
- [x] T003 Freeze the definition of what counts as a breaking shape change
- [x] T004 Freeze the definition of what counts as a breaking semantic change
- [x] T005 Freeze the first-slice `v1` rule as additive-only by default

**Checkpoint**: the policy for safe versus unsafe change is explicit.

---

## Phase 2: Versioning and Deprecation Rules

- [x] T006 Freeze the rule that breaking changes require a new major version
- [x] T007 Freeze the minimum deprecation window for execution-grade surfaces
- [x] T008 Define when a parallel overlap period is expected for replacement surfaces
- [x] T009 Define emergency override behavior for exceptional breaking changes
- [x] T010 Define the minimum migration note content for breaking replacements

**Checkpoint**: version change discipline is no longer ad hoc.

---

## Phase 3: Compatibility Gates

- [x] T011 Define route-contract verification requirements before promotion of schema-affecting or `behavioral_tightening` changes
- [x] T012 Define replay compatibility verification requirements before promotion of schema-affecting or `behavioral_tightening` changes
- [x] T013 Define `NT` adapter compatibility verification requirements before promotion of schema-affecting or `behavioral_tightening` changes
- [x] T014 Define which change classes require explicit compatibility signoff versus registry/docs-only updates
- [x] T015 Define how compatibility evidence is recorded

**Checkpoint**: schema-affecting changes now have a real gate.

---

## Phase 4: Governance Alignment

- [x] T016 [E] Align the feature contract registry with the frozen change classes, their `spec-044` mapping, and the version policy
- [x] T017 [E] Align provenance and contract docs where schema version semantics need to be explicit
- [x] T018 Update operator and consumer guidance with the change and deprecation policy
- [x] T019 Define the review checklist item that enforces this spec for future execution-grade contract changes

**Checkpoint**: the policy is attached to real governance artifacts.

---

## Phase 5: Verification

- [x] T020 Verify all current execution-grade `v1` surfaces are covered by the additive-only rule
- [x] T021 Verify breaking or `behavioral_tightening` changes cannot be introduced silently under this policy
- [x] T022 Verify deprecation windows and emergency exceptions are both explicit
- [x] T023 Verify the compatibility gate is practical enough to enforce in normal review
- [x] T024 Verify the policy remains small enough for long-term use

**Checkpoint**: schema discipline is enforceable rather than aspirational.
