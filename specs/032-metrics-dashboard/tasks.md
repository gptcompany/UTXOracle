# Tasks: Metrics Dashboard Pages

**Input**: Design documents from `/specs/032-metrics-dashboard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: No automated tests requested. Validation via visual comparison with CheckOnChain (spec-031).

**Organization**: Tasks are grouped by chart page (user story equivalent) to enable independent implementation and visual testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[US#]**: Which user story/chart page this task belongs to

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create shared utilities and styling before building individual pages

- [X] T001 Create metrics directory structure at frontend/metrics/
- [X] T002 [P] Create shared chart theme configuration in frontend/js/chart-themes.js
- [X] T003 [P] Create shared fetch/render utilities in frontend/js/metrics-common.js
- [X] T004 [P] Create shared CSS styling in frontend/css/metrics.css

**Checkpoint**: Shared infrastructure ready - individual pages can now be built

---

## Phase 2: User Story 1 - MVRV-Z Score (Priority: P1) MVP

**Goal**: Create MVRV-Z chart page that matches CheckOnChain visual style

**Independent Test**: Open http://localhost:8080/metrics/mvrv.html and compare with https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html

### Implementation for User Story 1

- [X] T005 [US1] Create MVRV page HTML structure in frontend/metrics/mvrv.html
- [X] T006 [US1] Implement MVRV data fetch from /api/metrics/wasserstein/history?days=365 in frontend/metrics/mvrv.html
- [X] T007 [US1] Add MVRV zone coloring (green <0, neutral 0-3, yellow 3-7, red >7) in frontend/metrics/mvrv.html
- [X] T008 [US1] Add BTC price overlay on secondary y-axis in frontend/metrics/mvrv.html

**Checkpoint**: MVRV page functional and visually matches reference

---

## Phase 3: User Story 2 - NUPL (Priority: P1)

**Goal**: Create NUPL chart page with zone coloring

**Independent Test**: Open http://localhost:8080/metrics/nupl.html and compare with https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html

### Implementation for User Story 2

- [X] T009 [US2] Create NUPL page HTML structure in frontend/metrics/nupl.html
- [X] T010 [US2] Implement NUPL data fetch from /api/metrics/nupl in frontend/metrics/nupl.html
- [X] T011 [US2] Add NUPL zone coloring (capitulation/hope/optimism/belief/euphoria) in frontend/metrics/nupl.html

**Checkpoint**: NUPL page functional and visually matches reference

---

## Phase 4: User Story 3 - SOPR (Priority: P1)

**Goal**: Create SOPR chart page with profit/loss coloring

**Independent Test**: Open http://localhost:8080/metrics/sopr.html and compare with https://charts.checkonchain.com/btconchain/realised/sopr/sopr_light.html

### Implementation for User Story 3

- [X] T012 [US3] Create SOPR page HTML structure in frontend/metrics/sopr.html
- [X] T013 [US3] Implement SOPR data fetch from /api/metrics/advanced in frontend/metrics/sopr.html
- [X] T014 [US3] Add SOPR reference line at 1.0 and profit/loss coloring in frontend/metrics/sopr.html

**Checkpoint**: SOPR page functional and visually matches reference

---

## Phase 5: User Story 4 - Cost Basis (Priority: P1)

**Goal**: Create Cost Basis chart with realized price vs market price

**Independent Test**: Open http://localhost:8080/metrics/cost_basis.html and compare with https://charts.checkonchain.com/btconchain/realised/realised_price/realised_price_light.html

### Implementation for User Story 4

- [X] T015 [US4] Create Cost Basis page HTML structure in frontend/metrics/cost_basis.html
- [X] T016 [US4] Implement data fetch from /api/metrics/cost-basis in frontend/metrics/cost_basis.html
- [X] T017 [US4] Add STH/LTH cost basis lines and market price overlay in frontend/metrics/cost_basis.html

**Checkpoint**: Cost Basis page functional and visually matches reference

---

## Phase 6: User Story 5 - Hash Ribbons (Priority: P1)

**Goal**: Create Hash Ribbons chart with MA crossover and capitulation zones

**Independent Test**: Open http://localhost:8080/metrics/hash_ribbons.html and compare with https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html

### Implementation for User Story 5

- [X] T018 [US5] Create Hash Ribbons page HTML structure in frontend/metrics/hash_ribbons.html
- [X] T019 [US5] Implement data fetch from /api/metrics/mining-pulse in frontend/metrics/hash_ribbons.html
- [X] T020 [US5] Add 30d/60d MA lines and capitulation zone highlighting in frontend/metrics/hash_ribbons.html

**Checkpoint**: Hash Ribbons page functional and visually matches reference

---

## Phase 7: User Story 6 - Binary CDD (Priority: P2)

**Goal**: Create Binary CDD chart with signal indicators

**Independent Test**: Open http://localhost:8080/metrics/binary_cdd.html and verify data displays correctly

### Implementation for User Story 6

- [X] T021 [US6] Create Binary CDD page HTML structure in frontend/metrics/binary_cdd.html
- [X] T022 [US6] Implement data fetch from /api/metrics/binary-cdd in frontend/metrics/binary_cdd.html
- [X] T023 [US6] Add CDD signal visualization (30d/60d indicators) in frontend/metrics/binary_cdd.html

**Checkpoint**: Binary CDD page functional

---

## Phase 8: User Story 7 - Wallet Waves (Priority: P2)

**Goal**: Create Wallet Waves chart with cohort distribution

**Independent Test**: Open http://localhost:8080/metrics/wallet_waves.html and verify cohorts display correctly

### Implementation for User Story 7

- [X] T024 [US7] Create Wallet Waves page HTML structure in frontend/metrics/wallet_waves.html
- [X] T025 [US7] Implement data fetch from /api/metrics/wallet-waves in frontend/metrics/wallet_waves.html
- [X] T026 [US7] Add stacked area chart for cohort visualization in frontend/metrics/wallet_waves.html

**Checkpoint**: Wallet Waves page functional

---

## Phase 9: User Story 8 - Exchange Netflow (Priority: P2)

**Goal**: Create Exchange Netflow chart with inflow/outflow balance

**Independent Test**: Open http://localhost:8080/metrics/exchange_netflow.html and verify netflow displays correctly

### Implementation for User Story 8

- [X] T027 [US8] Create Exchange Netflow page HTML structure in frontend/metrics/exchange_netflow.html
- [X] T028 [US8] Implement data fetch from /api/metrics/exchange-netflow in frontend/metrics/exchange_netflow.html
- [X] T029 [US8] Add inflow/outflow bars and netflow line in frontend/metrics/exchange_netflow.html

**Checkpoint**: Exchange Netflow page functional

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements and integration

- [X] T030 Add navigation links between all metric pages in frontend/metrics/*.html
- [X] T031 Add page titles and metadata for SEO in frontend/metrics/*.html
- [X] T032 Test responsive layout on mobile devices for all pages
- [x] T033 Run visual validation with alpha-visual agent (spec-031 integration)

---

## Phase 11: Dashboard Expansion (Added 2025-12-29)

**Purpose**: Add missing high-value metrics and improve UX

### Index & Navigation

- [x] T034 Create metrics index page (frontend/metrics/index.html) with card grid
- [x] T035 Add metric categories (Valuation, Profitability, Supply, Mining)
- [x] T036 Add search/filter functionality for metrics

### New Metric Pages (Priority Order)

- [x] T037 [P] Create Pro Risk page (frontend/metrics/pro_risk.html) - composite risk indicator
- [x] T038 [P] Create Power Law page (frontend/metrics/power_law.html) - price model
- [x] T039 [P] Create Puell Multiple page (frontend/metrics/puell_multiple.html) - mining metric
- [x] T040 [P] Create Reserve Risk page (frontend/metrics/reserve_risk.html) - HODL confidence
- [x] T041 [P] Create P/L Ratio page (frontend/metrics/pl_ratio.html) - profit/loss indicator
- [x] T042 [P] Create Liveliness page (frontend/metrics/liveliness.html) - cointime metric

### UX Improvements

- [x] T043 Add dark/light theme toggle to all pages
- [x] T044 Add date range selector (7d, 30d, 90d, 1y, all)
- [x] T045 Add export to PNG/CSV functionality
- [x] T046 Add real-time data refresh indicator

**Checkpoint**: Full dashboard with 14+ metrics and improved UX

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **User Stories (Phases 2-9)**: Depend on Setup completion
- **Polish (Phase 10)**: Depends on all user stories being complete

### User Story Dependencies

All user stories (US1-US8) are **independent** - they can be implemented in parallel after Setup phase.

Recommended order (by priority):
1. US1 (MVRV) - Template for all other pages
2. US2 (NUPL), US3 (SOPR), US4 (Cost Basis), US5 (Hash Ribbons) - Core validation
3. US6 (Binary CDD), US7 (Wallet Waves), US8 (Exchange Netflow) - Additional metrics

### Parallel Opportunities

After Phase 1 (Setup) completes:

```bash
# All Priority 1 pages can be built in parallel:
Task: "T005-T008 MVRV page"
Task: "T009-T011 NUPL page"
Task: "T012-T014 SOPR page"
Task: "T015-T017 Cost Basis page"
Task: "T018-T020 Hash Ribbons page"

# All Priority 2 pages can be built in parallel:
Task: "T021-T023 Binary CDD page"
Task: "T024-T026 Wallet Waves page"
Task: "T027-T029 Exchange Netflow page"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: MVRV page (T005-T008)
3. **STOP and VALIDATE**: Compare with CheckOnChain reference
4. Use MVRV as template for remaining pages

### Incremental Delivery

1. Setup → Foundation ready
2. Add MVRV → Test visually → First validation possible
3. Add NUPL, SOPR, Cost Basis, Hash Ribbons → Core validation complete
4. Add Binary CDD, Wallet Waves, Exchange Netflow → Full dashboard

---

## Summary

| Phase | Tasks | Description | Status |
|-------|-------|-------------|--------|
| 1 | T001-T004 | Setup (shared infrastructure) | ✅ |
| 2 | T005-T008 | MVRV (MVP) | ✅ |
| 3 | T009-T011 | NUPL | ✅ |
| 4 | T012-T014 | SOPR | ✅ |
| 5 | T015-T017 | Cost Basis | ✅ |
| 6 | T018-T020 | Hash Ribbons | ✅ |
| 7 | T021-T023 | Binary CDD | ✅ |
| 8 | T024-T026 | Wallet Waves | ✅ |
| 9 | T027-T029 | Exchange Netflow | ✅ |
| 10 | T030-T033 | Polish | 3/4 |
| 11 | T034-T046 | Dashboard Expansion | 13/13 ✅ |

**Total**: 46 tasks across 11 phases
**Completed**: 45/46 (98%)
**MVP**: T001-T008 (8 tasks) ✅
**Core Validation**: T001-T020 (20 tasks) ✅
**Full Dashboard**: T001-T046 (46 tasks) - 98% complete (T033 visual validation pending)
