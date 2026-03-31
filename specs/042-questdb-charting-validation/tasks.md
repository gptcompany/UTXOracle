# Tasks: spec-042 QuestDB Charting & Visual Validation

**Input**: design documents from `/specs/042-questdb-charting-validation/`
**Prerequisites**: `spec.md`, `plan.md`, spec-041 completion

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex query or UI task

---

## Phase 0: RED Contract Tests

- [ ] T001 Add failing tests for chart catalog and normalized chart schema behavior
- [ ] T002 Add failing tests for compare-mode payloads, parity metrics, and freshness metadata
- [ ] T003 Add failing tests for downsampling behavior and `2s` overlay timeout degradation

**Checkpoint**: chart behavior is test-defined before implementation starts.

---

## Phase 1: Contract

- [ ] T004 Define the chart catalog and chart id naming convention
- [ ] T005 Define the normalized chart response schema with `ts`, `series`, `overlays`, `is_downsampled`, and `source_health_summary`
- [ ] T006 Define compare-mode payloads including parity metrics such as MAE and parity score
- [ ] T007 Select the initial chart families allowed in the first release
- [ ] T008 Document freshness and degraded-state fields for chart payloads

**Checkpoint**: chart API contract is frozen before implementation.

---

## Phase 2: Query Layer

- [ ] T009 Build QuestDB queries for live comparison history
- [ ] T010 Build QuestDB queries for deviation bps history
- [ ] T011 Build QuestDB queries for ingestion latency/freshness history
- [ ] T012 Build QuestDB queries for curated BRK feature overlays
- [ ] T013 [E] Define and implement downsampling by series type: LTTB for continuous lines, time-bucket aggregation for aggregated series
- [ ] T014 Implement `catalog`, `latest`, and `history` chart endpoints

**Checkpoint**: chart data can be served without frontend work.

---

## Phase 3: Validation

- [ ] T015 Map overlapping local series to BRK overlay equivalents
- [ ] T016 Add compare endpoint or compare mode payload for supported chart ids
- [ ] T017 Define numeric parity tolerances and validation statuses
- [ ] T018 Implement BRK overlay caching/materialization or `2s` hard-timeout degraded fallback
- [ ] T019 Add visual validation workflow documentation and operator notes

**Checkpoint**: at least one chart family supports parity validation.

---

## Phase 4: Frontend

- [ ] T020 Create one canonical chart dashboard route/page
- [ ] T021 Implement live comparison chart with source-health and freshness badges
- [ ] T022 Implement ingestion latency/freshness chart
- [ ] T023 Implement overlay toggles for BRK and external references
- [ ] T024 Implement time window and downsampling controls
- [ ] T025 Retire or demote scattered chart entry points that are no longer canonical

**Checkpoint**: the chart surface is coherent and usable.

---

## Phase 5: Verification

- [ ] T026 Add tests for chart API schema and downsampling behavior
- [ ] T027 Add tests for compare-mode parity metrics and degraded overlay behavior
- [ ] T028 Run validation on at least one BRK-overlapped chart and record numerical parity outputs
- [ ] T029 Update `README` and architecture docs with the canonical chart entry point

**Checkpoint**: chart API, frontend, and docs align.
