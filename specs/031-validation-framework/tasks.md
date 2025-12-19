# Tasks: Validation Framework

**Input**: Design documents from `/specs/031-validation-framework/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Include tests for validation framework components (TDD per constitution).

**Organization**: Tasks grouped by validation layer (Numerical, Visual, CI/CD) with independent implementation.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[US#]**: Which user story/validation layer this task belongs to

### Existing Implementation Status

| Component | Status |
|-----------|--------|
| validator.py | ✅ EXISTS |
| checkonchain_fetcher.py | ✅ EXISTS |
| comparison_engine.py | ✅ EXISTS |
| visual_validator.py | ❌ MISSING |
| baselines/*.json | ❌ EMPTY |
| tests/*.py | ❌ EMPTY |

---

## Phase 1: Setup (Complete Existing Gaps)

**Purpose**: Fill gaps in existing infrastructure before new development

- [X] T001 Verify existing framework modules compile and import correctly in validation/framework/
- [X] T002 [P] Create URL mapping configuration in validation/framework/config.py
- [X] T003 [P] Update comparison_engine.py with spec-032 frontend URL paths

**Checkpoint**: Existing framework verified, configuration complete

---

## Phase 2: User Story 1 - Baselines Population (Priority: P0)

**Goal**: Populate all baseline files from CheckOnChain reference data

**Independent Test**: Run `python -c "from validation.framework.checkonchain_fetcher import CheckOnChainFetcher; f = CheckOnChainFetcher(); print(f.update_all_baselines())"`

### Implementation for User Story 1

- [X] T004 [US1] Populate mvrv_baseline.json using CheckOnChainFetcher in validation/baselines/
- [X] T005 [P] [US1] Populate nupl_baseline.json in validation/baselines/
- [X] T006 [P] [US1] Populate sopr_baseline.json in validation/baselines/
- [X] T007 [P] [US1] Populate cdd_baseline.json in validation/baselines/
- [X] T008 [P] [US1] Populate hash_ribbons_baseline.json in validation/baselines/
- [X] T009 [P] [US1] Populate cost_basis_baseline.json in validation/baselines/

**Checkpoint**: All 6 baseline files populated with CheckOnChain reference values

---

## Phase 3: User Story 2 - Numerical Validation Tests (Priority: P1)

**Goal**: Add tests for existing validation framework components

**Independent Test**: Run `uv run pytest validation/tests/ -v`

### Tests for User Story 2

- [X] T010 [US2] Create test fixtures with mock HTTP responses in validation/tests/conftest.py
- [X] T011 [P] [US2] Write tests for MetricValidator.compare() in validation/tests/test_validator.py
- [X] T012 [P] [US2] Write tests for MetricValidator.validate_mvrv() in validation/tests/test_validator.py
- [X] T013 [P] [US2] Write tests for CheckOnChainFetcher._extract_plotly_from_html() in validation/tests/test_fetcher.py
- [X] T014 [P] [US2] Write tests for CheckOnChainFetcher.fetch_metric_data() with cache in validation/tests/test_fetcher.py
- [X] T015 [US2] Write tests for ComparisonEngine.run_numerical_validation() in validation/tests/test_comparison.py

**Checkpoint**: All validation framework components have passing tests

---

## Phase 4: User Story 3 - Visual Validator (Priority: P1)

**Goal**: Implement screenshot-based visual comparison using Playwright MCP

**Independent Test**: Run visual validation on MVRV chart and verify screenshots generated

### Implementation for User Story 3

- [X] T016 [US3] Create VisualValidator class skeleton in validation/framework/visual_validator.py
- [X] T017 [US3] Implement capture_our_screenshot() using Playwright MCP in validation/framework/visual_validator.py
- [X] T018 [US3] Implement capture_reference_screenshot() using Playwright MCP in validation/framework/visual_validator.py
- [X] T019 [US3] Implement compare_screenshots() for trend/zone matching in validation/framework/visual_validator.py
- [X] T020 [US3] Implement compare_metric() orchestration method in validation/framework/visual_validator.py
- [X] T021 [US3] Add VisualComparisonResult to comparison_engine.py report generation

**Checkpoint**: Visual validation working for all metrics with screenshots saved

---

## Phase 5: User Story 4 - Integration & CLI (Priority: P2)

**Goal**: Create CLI entry point for running full validation suite

**Independent Test**: Run `python -m validation.run --help`

### Implementation for User Story 4

- [X] T022 [US4] Create CLI entry point in validation/__main__.py
- [X] T023 [US4] Add --numerical flag for numerical-only validation in validation/__main__.py
- [X] T024 [US4] Add --visual flag for visual-only validation in validation/__main__.py
- [X] T025 [US4] Add --metric flag for single-metric validation in validation/__main__.py
- [X] T026 [US4] Add --update-baselines flag to refresh baselines in validation/__main__.py
- [X] T027 [US4] Generate combined report (numerical + visual) in validation/__main__.py

**Checkpoint**: CLI fully functional, `python -m validation` runs complete suite

---

## Phase 6: User Story 5 - CI/CD Integration (Priority: P3)

**Goal**: GitHub Action for automated nightly validation

**Independent Test**: Push to branch and verify GitHub Action runs

### Implementation for User Story 5

- [X] T028 [US5] Create GitHub Action workflow in .github/workflows/validation.yml
- [X] T029 [US5] Configure scheduled run (nightly) in .github/workflows/validation.yml
- [X] T030 [US5] Add artifact upload for validation reports in .github/workflows/validation.yml
- [X] T031 [US5] Add failure notification (GitHub issue or Slack) in .github/workflows/validation.yml

**Checkpoint**: Nightly validation running automatically with reports uploaded

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final integration

- [X] T032 Update validation/README.md with usage instructions
- [X] T033 Add validation framework to docs/ARCHITECTURE.md
- [X] T034 Run full validation suite and generate first report
- [ ] T035 Commit all baselines and report to repository

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Baselines (Phase 2)**: Depends on Setup, uses existing fetcher
- **Tests (Phase 3)**: Depends on Baselines (needs data to test against)
- **Visual (Phase 4)**: Depends on Setup, can run parallel with Tests
- **CLI (Phase 5)**: Depends on Visual completion
- **CI/CD (Phase 6)**: Depends on CLI completion
- **Polish (Phase 7)**: Depends on all previous phases

### User Story Dependencies

- **US1 (Baselines)**: No dependencies - first priority
- **US2 (Tests)**: Depends on US1 for test data
- **US3 (Visual)**: Independent of US1/US2
- **US4 (CLI)**: Depends on US3
- **US5 (CI/CD)**: Depends on US4

### Parallel Opportunities

After Phase 1 (Setup) completes:

```bash
# Baselines can be populated in parallel:
Task: "T005 [P] Populate nupl_baseline.json"
Task: "T006 [P] Populate sopr_baseline.json"
Task: "T007 [P] Populate cdd_baseline.json"
Task: "T008 [P] Populate hash_ribbons_baseline.json"
Task: "T009 [P] Populate cost_basis_baseline.json"

# Tests can be written in parallel after baselines:
Task: "T011 [P] Write tests for MetricValidator.compare()"
Task: "T012 [P] Write tests for MetricValidator.validate_mvrv()"
Task: "T013 [P] Write tests for CheckOnChainFetcher._extract_plotly_from_html()"
Task: "T014 [P] Write tests for CheckOnChainFetcher.fetch_metric_data()"
```

---

## Implementation Strategy

### MVP First (US1 + US3 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Baselines (T004-T009)
3. Complete Phase 4: Visual Validator (T016-T021)
4. **STOP and VALIDATE**: Run visual comparison on MVRV chart
5. Use for manual validation of spec-032 dashboard

### Full Implementation

1. Setup → Baselines ready
2. Add Tests → Framework validated
3. Add Visual → Screenshot comparison working
4. Add CLI → Command-line access
5. Add CI/CD → Automated nightly runs

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | T001-T003 | Setup (verify existing, add config) |
| 2 | T004-T009 | Baselines (populate from CheckOnChain) |
| 3 | T010-T015 | Tests (validate framework) |
| 4 | T016-T021 | Visual Validator (screenshots) |
| 5 | T022-T027 | CLI (command-line interface) |
| 6 | T028-T031 | CI/CD (GitHub Action) |
| 7 | T032-T035 | Polish (docs, final run) |

**Total**: 35 tasks across 7 phases
**MVP**: T001-T009 + T016-T021 (15 tasks)
**Full Implementation**: T001-T035 (35 tasks)
