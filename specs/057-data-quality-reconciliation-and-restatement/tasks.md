# Tasks: spec-057 Data Quality, Reconciliation, and Restatement

**Input**: design documents from `/specs/057-data-quality-reconciliation-and-restatement/`
**Prerequisites**: `spec.md`, `plan.md`, `spec-054`, `spec-055`, `spec-056`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: execution-impacting data-governance or storage task

---

## Phase 1: Quality-State Model Freeze

- [x] T001 Freeze the scope: this spec governs data quality state, reconciliation, quarantine, and restatement for execution-relevant surfaces
- [x] T002 Freeze the bounded quality vocabulary to exactly `valid`, `suspect`, `quarantined`, `restated`, with `restated` treated as a historical correction overlay
- [x] T003 Define where the quality state applies in the first slice: live snapshot, bundles, signals, and execution inputs
- [x] T004 Freeze the rule that visibility and execution eligibility are separate concepts
- [x] T005 Define the relationship between current runtime quality state and historical `restated` corrections
- [x] T006 Freeze what kinds of corrections require explicit restatement artifacts

**Checkpoint**: data-quality vocabulary is bounded before detailed rules begin.

---

## Phase 2: Validation Layers

- [ ] T007 Define ingest validation checks for tier-1 inputs
- [ ] T008 Define materialization validation checks for persisted bundles and signals
- [ ] T009 Define serve-time validation checks for latest and history reads
- [ ] T010 Define continuity checks for timestamps, freshness, and sequence monotonicity
- [ ] T011 Define cross-source reconciliation checks where comparison is meaningful
- [ ] T012 Define how reconciliation follows the metric source-of-truth manifest instead of treating all upstream disagreement equally

**Checkpoint**: validation happens at the right layers, not only at the end.

---

## Phase 3: Suspect and Quarantine Rules

- [ ] T013 Freeze the escalation rule from `valid` to `suspect`
- [ ] T014 Freeze the escalation rule from `suspect` to `quarantined`
- [ ] T015 Define which quarantined conditions must immediately block execution
- [ ] T016 Define operator visibility requirements for suspect and quarantined data
- [ ] T017 Define whether quarantined data remains readable for operator and forensic use

**Checkpoint**: unsafe data cannot continue as normal silently.

---

## Phase 4: Restatement Model

- [ ] T018 Freeze the minimum restatement artifact shape
- [ ] T019 Define how affected surfaces and time ranges are referenced
- [ ] T020 Define how a restatement points to the superseded artifact or reference
- [ ] T021 Define severity classes for restatements
- [ ] T022 Define whether and how restatements propagate to tier-1 `latest` and `history` consumers

**Checkpoint**: historical corrections are explicit and auditable.

---

## Phase 5: Execution Coupling

- [ ] T023 Define how `suspect` state affects `spec-055` execution modes
- [ ] T024 Define how `quarantined` state affects `spec-055` execution modes
- [ ] T025 Define how unresolved critical `restated` state affects `spec-055`
- [ ] T026 Define how continuity or sequence failures escalate into data-quality consequences
- [ ] T027 Define the minimal operator acknowledgment or resolution flow before execution may resume

**Checkpoint**: data quality now has direct execution meaning.

---

## Phase 6: Storage, Serving, and Governance

- [ ] T028 [E] Decide where quality-state and restatement artifacts are persisted
- [ ] T029 [E] Decide how tier-1 surfaces reference quality and restatement status
- [ ] T030 Update provenance and contract artifacts so data-quality semantics are discoverable
- [ ] T031 Update service and operator docs with the quality-state vocabulary and restatement rules

**Checkpoint**: governance artifacts and service behavior align.

---

## Phase 7: Verification

- [ ] T032 Verify tier-1 surfaces have a bounded quality-state model
- [ ] T033 Verify suspected data cannot silently remain execution-safe without explicit rule support
- [ ] T034 Verify quarantined and critical restated data fail closed for execution
- [ ] T035 Verify historical corrections produce explicit audit artifacts
- [ ] T036 Verify the whole quality model stays small enough for operators to reason about

**Checkpoint**: data quality is now operational, not implied.
