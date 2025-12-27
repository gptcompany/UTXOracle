# Tasks: Custom Price Models Framework

**Input**: Design documents from `/specs/036-custom-price-models/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: TDD is mandatory per constitution (Principle II). Tests written BEFORE implementation.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

### When to use [P] marker (CRITICAL)
- **USE [P]** only when tasks edit **different files** with no dependencies
- **NEVER use [P]** when multiple tasks edit the **same file** (they conflict)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [X] T001 Create test directory structure at tests/test_models/\_\_init\_\_.py
- [X] T002 Create backtest subdirectory at scripts/models/backtest/\_\_init\_\_.py
- [X] T003 Create API routes directory at api/routes/\_\_init\_\_.py
- [X] T004 Create model configuration file at config/models.yaml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create Pydantic API models in api/models/model_framework.py (ModelPredictionResponse, ModelInfoResponse, BacktestResultResponse, ModelComparisonResponse, EnsembleCreateRequest)
- [X] T006 Update scripts/models/\_\_init\_\_.py with new module exports

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Model Framework (Priority: P1) 🎯 MVP

**Goal**: Create PriceModel ABC and ModelPrediction dataclass as the foundation for all models

**Independent Test**: `uv run pytest tests/test_models/test_base.py -v` passes

### Tests for User Story 1

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [US1] Write contract tests for PriceModel ABC in tests/test_models/test_base.py (test abstract methods, test concrete implementation required, test ModelPrediction dataclass validation)

### Implementation for User Story 1

- [X] T008 [US1] Implement ModelPrediction dataclass in scripts/models/base.py (model_name, date, predicted_price, confidence_interval, confidence_level, metadata, to_dict method)
- [X] T009 [US1] Implement PriceModel ABC in scripts/models/base.py (name, description, required_data properties; fit, predict abstract methods; is_fitted helper)

**Checkpoint**: PriceModel ABC and ModelPrediction dataclass functional

---

## Phase 4: User Story 2 - Model Registry (Priority: P2)

**Goal**: Create registry pattern for model discovery and instantiation

**Independent Test**: `uv run pytest tests/test_models/test_registry.py -v` passes

### Tests for User Story 2

- [X] T010 [US2] Write tests for ModelRegistry in tests/test_models/test_registry.py (test register decorator, test get by name, test list_models, test create with config, test KeyError for unknown model)

### Implementation for User Story 2

- [X] T011 [US2] Implement ModelRegistry class in scripts/models/registry.py (register decorator, get, list_models, create factory method)

**Checkpoint**: ModelRegistry functional with register/get/list/create

---

## Phase 5: User Story 3 - Built-in Models (Priority: P3)

**Goal**: Implement 4 built-in models: Power Law adapter, Stock-to-Flow, Thermocap, UTXOracle wrapper

**Independent Test**: `uv run pytest tests/test_models/test_stock_to_flow.py tests/test_models/test_thermocap.py tests/test_models/test_utxoracle_model.py -v` passes

### Tests for User Story 3

- [X] T012 [P] [US3] Write tests for PowerLawAdapter in tests/test_models/test_power_law_adapter.py (test wraps existing spec-034, test fit, test predict, test is_fitted)
- [X] T013 [P] [US3] Write tests for StockToFlowModel in tests/test_models/test_stock_to_flow.py (test S2F calculation, test halving schedule, test predict output)
- [X] T014 [P] [US3] Write tests for ThermocapModel in tests/test_models/test_thermocap.py (test thermocap multiple, test fair value range, test predict)
- [X] T015 [P] [US3] Write tests for UTXOracleModel in tests/test_models/test_utxoracle_model.py (test wrapper around UTXOracle_library, test predict)

### Implementation for User Story 3

- [X] T016 [P] [US3] Implement PowerLawAdapter in scripts/models/power_law_adapter.py (wraps existing price_power_law.py, implements PriceModel interface)
- [X] T017 [P] [US3] [E] Implement StockToFlowModel in scripts/models/stock_to_flow.py (halving-aware S2F calculation, fit from block heights, predict with confidence interval)
- [X] T018 [P] [US3] Implement ThermocapModel in scripts/models/thermocap.py (thermocap multiple calculation, fair value range 3-8x)
- [X] T019 [P] [US3] Implement UTXOracleModel in scripts/models/utxoracle_model.py (wrapper around UTXOracle_library functions)
- [X] T020 [US3] Register all built-in models in scripts/models/\_\_init\_\_.py (import and auto-register on module load)

**Checkpoint**: All 4 built-in models registered and functional

---

## Phase 6: User Story 4 - Ensemble Model (Priority: P4)

**Goal**: Combine multiple models for ensemble predictions with configurable aggregation

**Independent Test**: `uv run pytest tests/test_models/test_ensemble.py -v` passes

### Tests for User Story 4

- [X] T021 [US4] Write tests for EnsembleConfig and EnsembleModel in tests/test_models/test_ensemble.py (test weight validation, test weighted_avg aggregation, test median aggregation, test confidence interval calculation)

### Implementation for User Story 4

- [X] T022 [US4] Implement EnsembleConfig dataclass in scripts/models/ensemble.py (models list, weights list, aggregation method, validation in \_\_post\_init\_\_)
- [X] T023 [US4] Implement EnsembleModel in scripts/models/ensemble.py (creates sub-models from registry, aggregates predictions, calculates combined confidence interval)

**Checkpoint**: EnsembleModel functional with weighted_avg, median, min, max aggregation

---

## Phase 7: User Story 5 - Backtesting Framework (Priority: P5)

**Goal**: Walk-forward backtesting with MAE, MAPE, RMSE, direction accuracy metrics

**Independent Test**: `uv run pytest tests/test_models/test_model_backtester.py -v` passes

### Tests for User Story 5

- [X] T024 [US5] Write tests for ModelBacktester in tests/test_models/test_model_backtester.py (test walk-forward split, test metric calculations, test compare_models ranking)

### Implementation for User Story 5

- [X] T025 [US5] Implement ModelBacktestResult dataclass in scripts/models/backtest/model_backtester.py (model_name, dates, predictions count, MAE, MAPE, RMSE, direction_accuracy, sharpe_ratio, max_drawdown, daily_results DataFrame)
- [X] T026 [US5] [E] Implement ModelBacktester class in scripts/models/backtest/model_backtester.py (run method with train/test split, metric calculation helpers, compare_models method)

**Checkpoint**: ModelBacktester functional with all metrics

---

## Phase 8: User Story 6 - API Endpoints (Priority: P6)

**Goal**: REST API for model listing, prediction, ensemble, backtest, comparison

**Independent Test**: `uv run pytest tests/test_models/test_api_models.py -v` passes

### Tests for User Story 6

- [X] T027 [US6] Write API integration tests in tests/test_models/test_api_models.py (test GET /models, test GET /models/{name}/predict, test POST /models/ensemble, test GET /models/backtest/{name}, test GET /models/compare)

### Implementation for User Story 6

- [X] T028 [US6] Implement API router in api/routes/models.py (listModels, getModelPrediction, createEnsemble, runBacktest, compareModels endpoints per OpenAPI contract)
- [X] T029 [US6] Register router in api/main.py (add models router with /api/v1/models prefix)

**Checkpoint**: All 5 API endpoints functional per OpenAPI contract

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T030 [P] Add docstrings to all public functions and classes
- [X] T031 Run full test suite with coverage: `uv run pytest tests/test_models/ --cov=scripts/models --cov=api/routes/models --cov-report=term-missing`
- [X] T032 Validate quickstart.md examples work end-to-end
- [X] T033 Run linting and formatting: `ruff check scripts/models api/routes/models.py && ruff format scripts/models api/routes/models.py`
- [X] T034 Add performance benchmark tests in tests/test_models/test_performance.py (verify prediction <100ms, backtest <500ms per 1000 days per spec validation criteria #5)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Model Framework) MUST complete before US2-US6
  - US2 (Registry) MUST complete before US3-US6
  - US3 (Built-in Models), US4 (Ensemble), US5 (Backtest) can proceed in parallel after US2
  - US6 (API) depends on US3, US4, US5 being complete
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
    v
Phase 2 (Foundational)
    │
    v
Phase 3 (US1: Model Framework)
    │
    v
Phase 4 (US2: Registry)
    │
    ├──────────────┬──────────────┐
    v              v              v
Phase 5 (US3)  Phase 6 (US4)  Phase 7 (US5)
Built-in       Ensemble       Backtest
    │              │              │
    └──────────────┴──────────────┘
                   │
                   v
            Phase 8 (US6: API)
                   │
                   v
            Phase 9 (Polish)
```

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Dataclasses before classes that use them
- Core implementation before integration
- Story complete before moving to dependent stories

### Parallel Opportunities

**Phase 1 (Setup)**:
```
T001, T002, T003, T004 can run in parallel (different directories)
```

**Phase 5 (US3: Built-in Models)**:
```
T012, T013, T014, T015 can run in parallel (different test files)
T016, T017, T018, T019 can run in parallel (different model files)
```

---

## Parallel Example: User Story 3 (Built-in Models)

```bash
# Launch all tests for US3 together:
Task: "Write tests for PowerLawAdapter in tests/test_models/test_power_law_adapter.py"
Task: "Write tests for StockToFlowModel in tests/test_models/test_stock_to_flow.py"
Task: "Write tests for ThermocapModel in tests/test_models/test_thermocap.py"
Task: "Write tests for UTXOracleModel in tests/test_models/test_utxoracle_model.py"

# After tests written, launch all model implementations together:
Task: "Implement PowerLawAdapter in scripts/models/power_law_adapter.py"
Task: "Implement StockToFlowModel in scripts/models/stock_to_flow.py"
Task: "Implement ThermocapModel in scripts/models/thermocap.py"
Task: "Implement UTXOracleModel in scripts/models/utxoracle_model.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: US1 (Model Framework)
4. Complete Phase 4: US2 (Registry)
5. **STOP and VALIDATE**: Test base framework works
6. Proceed with remaining stories

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 + US2 → Framework MVP (can define/register models)
3. US3 → Built-in models available
4. US4 + US5 → Ensemble + Backtest (model comparison enabled)
5. US6 → API exposure (full feature complete)

### Suggested MVP Scope

For fastest validation, implement only:
- Phase 1: Setup
- Phase 2: Foundational
- Phase 3: US1 (Model Framework)
- Phase 4: US2 (Registry)
- Phase 5: US3 (Built-in Models) - at least PowerLawAdapter

This delivers: working model framework with at least one model that can predict.

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 34 |
| Setup Tasks | 4 |
| Foundational Tasks | 2 |
| US1 Tasks | 3 |
| US2 Tasks | 2 |
| US3 Tasks | 9 |
| US4 Tasks | 3 |
| US5 Tasks | 3 |
| US6 Tasks | 3 |
| Polish Tasks | 5 |
| Parallel Opportunities | Phase 1 (4), Phase 5 (8) |
| Alpha-Evolve Tasks [E] | 2 (T017, T026) |

---

## Notes

- [P] tasks = different files, no dependencies (processed by /speckit.implement)
- [E] tasks = complex algorithms triggering alpha-evolve
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (TDD per constitution)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
