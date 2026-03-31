# Tasks: spec-042 QuestDB Charting & Visual Validation

**Input**: design documents from `/specs/042-questdb-charting-validation/`
**Prerequisites**: `spec.md`, `plan.md`, spec-041 completion

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex query or UI task

---

## Phase 0: RED Contract Tests

- [x] T001 Add failing tests for chart catalog exposing only `live-price-comparison` in the first slice
- [x] T002 Add failing tests for normalized `latest` and `history` payloads for `live-price-comparison`
- [x] T003 Add failing tests for freshness, degraded-state metadata, empty-state behavior, and unknown chart ids

**Checkpoint**: chart behavior is test-defined before implementation starts.

---

## Phase 1: Contract

- [x] T004 Freeze the first chart id as `live-price-comparison` and define the initial catalog entry
- [x] T005 Define the normalized chart response schema with `ts`, `series`, `is_downsampled`, and source metadata for the first slice
- [x] T006 Define the first-slice endpoint contract for `catalog`, `latest`, and `history`
- [x] T007 Freeze the initial series set from `live_snapshots`: UTXOracle, mempool, Hyperliquid oracle, Hyperliquid mark
- [x] T008 Document freshness, degraded-state, and unsupported-chart semantics for the first slice

**Checkpoint**: chart API contract is frozen before implementation.

---

## Phase 2: Query Layer

- [x] T009 Build QuestDB queries for `live-price-comparison` history from `live_snapshots`
- [x] T010 Build QuestDB queries for `live-price-comparison` latest from `live_snapshots`
- [x] T011 Build chart payload assembly and freshness metadata from `live_snapshots`
- [x] T012 Implement `GET /api/v1/charts/catalog`
- [x] T013 Implement `GET /api/v1/charts/{chart_id}/latest`
- [x] T014 Implement `GET /api/v1/charts/{chart_id}/history`

**Checkpoint**: chart data can be served without frontend work.

---

## Phase 3: Validation

- [x] T015 Freeze BRK / CheckOnChain mapping candidates and explicitly mark `live-price-comparison` as internal-reference-only
- [x] T016 Add compare endpoint or compare mode payload for supported chart ids
- [x] T017 Define numeric parity tolerances and validation statuses
- [x] T018 Implement BRK overlay caching/materialization or `2s` hard-timeout degraded fallback
- [x] T019 Add visual validation workflow documentation and operator notes

**Checkpoint**: at least one chart family supports parity validation.

---

## Phase 4: Frontend

- [x] T020 Create one canonical chart dashboard route/page as a thin client over the chart API
- [x] T021 Implement the `live-price-comparison` chart with source-health and freshness badges
- [x] T022 Add a minimal time-window control for the supported history windows
- [x] T023 Add overlay toggles for later BRK/external references without blocking the base chart
- [x] T024 Implement downsampling controls when long-window support is added
- [x] T025 Retire or demote scattered chart entry points that are no longer canonical

**Checkpoint**: the chart surface is coherent and usable.

---

## Phase 5: Verification

- [x] T026 Add tests for chart API schema and first-slice QuestDB behavior
- [x] T027 Add tests for compare-mode parity metrics and degraded overlay behavior; extend coverage for downsampling when T024 lands
- [x] T028 Run validation on at least one BRK-overlapped chart and record numerical parity outputs
- [x] T029 Update `README` and architecture docs with the canonical chart entry point

**Checkpoint**: chart API, frontend, and docs align.
