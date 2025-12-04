# Tasks: Derivatives Historical Integration

**Feature**: 008-derivatives-historical
**Branch**: `008-derivatives-historical`
**Generated**: 2025-12-03
**Total Tasks**: 42
**Estimated LOC**: ~500

## User Story Summary

| Story | Priority | Description | Tasks | LOC |
|-------|----------|-------------|-------|-----|
| US1 | P1 | Funding Rate Signal Integration | 9 | ~100 |
| US2 | P1 | Open Interest Signal Integration | 9 | ~120 |
| US3 | P2 | Combined Derivatives-Enhanced Signal | 8 | ~80 |
| US4 | P2 | Historical Backtesting | 8 | ~150 |
| - | - | Setup & Integration | 8 | ~50 |

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Goal**: Create project structure and shared infrastructure for derivatives integration.

- [x] T001 Create derivatives module directory at `scripts/derivatives/__init__.py`
- [x] T002 Create derivatives data models at `scripts/models/derivatives_models.py` (copy from data-model.md)
- [x] T003 [P] Add .env configuration for `LIQUIDATION_HEATMAP_DB_PATH` and `DERIVATIVES_ENABLED`
- [x] T004 Create test file at `tests/test_derivatives_integration.py` with fixtures

**Checkpoint**: Module structure ready for user story implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Goal**: DuckDB cross-database query infrastructure that ALL stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Implement `get_liq_connection()` helper in `scripts/derivatives/__init__.py` (DuckDB ATTACH with READ_ONLY, exponential backoff retry max 3 attempts)
- [x] T006 Implement `check_data_freshness()` helper in `scripts/derivatives/__init__.py` (log last update timestamp)
- [x] T007 [P] Write test `test_crossdb_connection()` in `tests/test_derivatives_integration.py`
- [x] T008 [P] Write test `test_graceful_degradation_db_unavailable()` in `tests/test_derivatives_integration.py`

**Checkpoint**: Cross-DB connection working, degradation tested

---

## Phase 3: User Story 1 - Funding Rate Signal Integration (Priority: P1) 🎯 MVP

**Goal**: Read Binance Funding Rate from LiquidationHeatmap and convert to contrarian signal.

**Independent Test**:
1. Query LiquidationHeatmap for funding rate at specific timestamp
2. Verify contrarian conversion: +0.15% → -0.8, -0.08% → +0.6, +0.01% → 0.0

### Tests for User Story 1

- [x] T009 [P] [US1] Write test `test_funding_positive_extreme()` in `tests/test_derivatives_integration.py`
  - Given funding_rate=+0.15%, expect funding_vote=-0.8, is_extreme=True
- [x] T010 [P] [US1] Write test `test_funding_negative_extreme()` in `tests/test_derivatives_integration.py`
  - Given funding_rate=-0.08%, expect funding_vote=+0.6, is_extreme=True
- [x] T011 [P] [US1] Write test `test_funding_neutral()` in `tests/test_derivatives_integration.py`
  - Given funding_rate=+0.01%, expect funding_vote=0.0, is_extreme=False
- [x] T012 [P] [US1] Write test `test_funding_unavailable_graceful()` in `tests/test_derivatives_integration.py`
  - Given LiquidationHeatmap offline, expect None returned (not exception)

### Implementation for User Story 1

- [x] T013 [US1] Implement `funding_to_vote(funding_rate)` in `scripts/derivatives/funding_rate_reader.py`
- [x] T014 [US1] Implement `read_funding_rate(timestamp)` in `scripts/derivatives/funding_rate_reader.py`
- [x] T015 [US1] Implement `get_latest_funding_signal()` in `scripts/derivatives/funding_rate_reader.py`
- [x] T016 [US1] Add logging for funding rate operations
- [x] T017 [US1] Verify all US1 tests pass with `uv run pytest tests/test_derivatives_integration.py -k funding -v`

**Checkpoint**: Funding rate reader complete and independently testable

---

## Phase 4: User Story 2 - Open Interest Signal Integration (Priority: P1)

**Goal**: Read Open Interest from LiquidationHeatmap, calculate % change, and convert to context-aware signal.

**Independent Test**:
1. Query OI at t and t-1h from LiquidationHeatmap
2. Verify context-aware conversion based on whale signal direction

### Tests for User Story 2

- [x] T018 [P] [US2] Write test `test_oi_rising_accumulation()` in `tests/test_derivatives_integration.py`
  - Given OI +5%, whale=ACCUMULATION, expect oi_vote=+0.5, context="confirming"
- [x] T019 [P] [US2] Write test `test_oi_rising_distribution()` in `tests/test_derivatives_integration.py`
  - Given OI +5%, whale=DISTRIBUTION, expect oi_vote=-0.3, context="diverging"
- [x] T020 [P] [US2] Write test `test_oi_falling_deleveraging()` in `tests/test_derivatives_integration.py`
  - Given OI -3%, expect oi_vote=0.0, context="deleveraging"
- [x] T021 [P] [US2] Write test `test_oi_data_gap()` in `tests/test_derivatives_integration.py`
  - Given missing timestamps, expect None or last known with warning

### Implementation for User Story 2

- [x] T022 [US2] Implement `calculate_oi_change(current_oi, previous_oi)` in `scripts/derivatives/oi_reader.py`
- [x] T023 [US2] Implement `oi_to_vote(oi_change, whale_direction)` in `scripts/derivatives/oi_reader.py`
- [x] T024 [US2] Implement `read_oi_at_timestamp(timestamp, window_hours=1)` in `scripts/derivatives/oi_reader.py`
- [x] T025 [US2] Implement `get_latest_oi_signal(whale_direction)` in `scripts/derivatives/oi_reader.py`
- [x] T026 [US2] Verify all US2 tests pass with `uv run pytest tests/test_derivatives_integration.py -k oi -v`

**Checkpoint**: OI reader complete and independently testable

---

## Phase 5: User Story 3 - Combined Derivatives-Enhanced Signal (Priority: P2)

**Goal**: Extend Monte Carlo fusion from 2 to 4 components (whale + utxo + funding + oi).

**Independent Test**:
1. Provide all four signals (whale, utxo, funding, oi)
2. Run Monte Carlo fusion with configurable weights
3. Verify output includes all components and derivatives_available flag

### Tests for User Story 3

- [x] T027 [P] [US3] Write test `test_enhanced_fusion_all_signals()` in `tests/test_derivatives_integration.py`
  - Given all 4 signals, expect combined signal with derivatives_available=True
- [x] T028 [P] [US3] Write test `test_enhanced_fusion_conflicting()` in `tests/test_derivatives_integration.py`
  - Given conflicting signals, expect high signal_std (>0.3)
- [x] T029 [P] [US3] Write test `test_enhanced_fusion_fallback()` in `tests/test_derivatives_integration.py`
  - Given derivatives unavailable, expect 2-component fusion (spec-007 behavior)

### Implementation for User Story 3

- [x] T030 [US3] Implement `enhanced_monte_carlo_fusion()` in `scripts/derivatives/enhanced_fusion.py`
- [x] T031 [US3] Implement `redistribute_weights(missing_components)` in `scripts/derivatives/enhanced_fusion.py`
- [x] T032 [US3] Implement `create_enhanced_result()` in `scripts/derivatives/enhanced_fusion.py`
- [x] T033 [US3] Integrate enhanced fusion into `scripts/daily_analysis.py` main flow
- [x] T034 [US3] Verify all US3 tests pass with `uv run pytest tests/test_derivatives_integration.py -k enhanced -v`

**Checkpoint**: Enhanced 4-component fusion complete

---

## Phase 6: User Story 4 - Historical Backtesting (Priority: P2)

**Goal**: Backtest derivatives-enhanced signal against historical price data.

**Independent Test**:
1. Run enhanced fusion on 30+ days of historical data
2. Compare signals with actual BTC price changes (24h forward)
3. Calculate and report performance metrics

### Tests for User Story 4

- [x] T035 [P] [US4] Write test `test_backtest_output_format()` in `tests/test_derivatives_integration.py`
  - Verify report includes: total_signals, win_rate, sharpe_ratio, max_drawdown
- [x] T036 [P] [US4] Write test `test_backtest_weight_optimization()` in `tests/test_derivatives_integration.py`
  - Given optimize=True, expect optimal_weights in result

### Implementation for User Story 4

- [x] T037 [US4] Implement `load_historical_data(start_date, end_date)` in `scripts/backtest_derivatives.py`
- [x] T038 [US4] Implement `run_backtest(data, weights)` in `scripts/backtest_derivatives.py`
- [x] T039 [US4] Implement `calculate_performance_metrics(signals, prices)` in `scripts/backtest_derivatives.py`
- [x] T040 [US4] Implement `grid_search_weights(data, holdout_ratio)` in `scripts/backtest_derivatives.py`
- [x] T041 [US4] Add CLI interface with argparse (--start, --end, --optimize)
- [x] T042 [US4] Verify backtest runs with `uv run python scripts/backtest_derivatives.py --start 2025-10-01 --end 2025-10-31`

**Checkpoint**: Backtest script complete and produces performance report

---

## Phase 7: Integration & Polish

**Goal**: API integration, documentation, and validation.

- [x] T043 Extend `/api/metrics/latest` in `api/main.py` to include derivatives signals
- [x] T044 [P] Create integration test at `tests/integration/test_derivatives_e2e.py` with real LiquidationHeatmap
- [x] T045 [P] Update CLAUDE.md with derivatives module documentation
- [x] T046 Validate cross-DB latency <500ms with benchmark
- [x] T047 Verify code coverage ≥80% for `scripts/derivatives/` with `uv run pytest --cov=scripts/derivatives`
- [x] T048 Run quickstart.md validation steps

**Checkpoint**: Feature complete and documented

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational) ◄── BLOCKS all user stories
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  │
Phase 3 (US1)     Phase 4 (US2)          │
Funding Rate      Open Interest          │
[Independent]     [Independent]          │
    │                  │                  │
    └────────┬─────────┘                  │
             ▼                            │
        Phase 5 (US3) ◄───────────────────┘
        Enhanced Fusion
        [Depends on US1 + US2]
             │
             ▼
        Phase 6 (US4)
        Backtesting
        [Depends on US3]
             │
             ▼
        Phase 7 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Run After |
|-------|------------|---------------|
| US1 (Funding) | Phase 2 only | Phase 2 complete |
| US2 (OI) | Phase 2 only | Phase 2 complete |
| US3 (Enhanced) | US1 + US2 | Both US1 and US2 complete |
| US4 (Backtest) | US3 | US3 complete |

**Note**: US1 and US2 are INDEPENDENT and can run in parallel after Phase 2.

---

## Parallel Execution Opportunities

### Within Phase 2 (Foundational)
```
T007, T008 [P] - Tests can run in parallel
```

### Within Phase 3 (US1)
```
T009, T010, T011, T012 [P] - All funding tests in parallel
```

### Within Phase 4 (US2)
```
T018, T019, T020, T021 [P] - All OI tests in parallel
```

### Within Phase 5 (US3)
```
T027, T028, T029 [P] - All fusion tests in parallel
```

### Cross-Story Parallelism
```
After Phase 2 complete:
  ├── Phase 3 (US1 Funding) ─┐
  │                          ├── Phase 5 (US3 Enhanced)
  └── Phase 4 (US2 OI) ──────┘
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: US1 Funding Rate
4. **STOP and VALIDATE**: Test funding rate signal independently
5. Can integrate with daily_analysis.py for partial benefit

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Funding) → Test independently → Partial value (funding signal only)
3. Add US2 (OI) → Test independently → More complete (both derivatives)
4. Add US3 (Enhanced) → Test independently → Full 4-component fusion
5. Add US4 (Backtest) → Validate and optimize → Production ready

### Parallel Team Strategy

With 2 developers after Phase 2:
- Developer A: US1 (Funding Rate)
- Developer B: US2 (Open Interest)

Both complete → US3 can begin → US4 follows

---

## Validation Commands

```bash
# Run all derivatives tests
uv run pytest tests/test_derivatives_integration.py -v

# Check coverage
uv run pytest tests/test_derivatives_integration.py --cov=scripts/derivatives --cov-report=term-missing

# Test cross-DB performance
uv run python -c "
import time
import duckdb
start = time.time()
conn = duckdb.connect()
conn.execute(\"ATTACH '/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb' AS liq (READ_ONLY)\")
conn.execute('SELECT * FROM liq.funding_rate_history WHERE symbol = \\'BTCUSDT\\' ORDER BY timestamp DESC LIMIT 100').fetchall()
print(f'Cross-DB query: {(time.time()-start)*1000:.1f}ms (target: <500ms)')
conn.close()
"

# Run backtest
uv run python scripts/backtest_derivatives.py --start 2025-10-01 --end 2025-10-31

# API test
curl http://localhost:8000/api/metrics/latest | jq '.monte_carlo.derivatives_available'
```

---

## File Checklist

After all tasks complete, verify:

```
✅ scripts/derivatives/__init__.py (T001, T005, T006)
✅ scripts/derivatives/funding_rate_reader.py (T013-T016)
✅ scripts/derivatives/oi_reader.py (T022-T025)
✅ scripts/derivatives/enhanced_fusion.py (T030-T032)
✅ scripts/backtest_derivatives.py (T037-T041)
✅ scripts/models/derivatives_models.py (T002)
✅ scripts/daily_analysis.py (modified - T033)
✅ api/main.py (modified - T043)
✅ tests/test_derivatives_integration.py (T004, T007-T012, T018-T021, T027-T029, T035-T036)
✅ tests/integration/test_derivatives_e2e.py (T044)
✅ .env (modified - T003)
✅ CLAUDE.md (updated - T045)
```

---

## Notes

- Constitution compliance verified in plan.md (all principles pass)
- TDD approach: Tests written before implementation for each user story
- Graceful degradation: System works with whale+utxo only if derivatives fail
- Zero data duplication: All data read from LiquidationHeatmap via ATTACH
- Performance target: <500ms cross-DB, <100ms fusion (inherited from spec-007)
