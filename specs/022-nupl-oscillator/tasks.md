# Tasks: NUPL Oscillator (spec-022)

## Phase 1: Setup
- [ ] T001 Add NUPLResult dataclass to scripts/models/metrics_models.py
- [ ] T002 Add NUPLZone enum (CAPITULATION, HOPE_FEAR, OPTIMISM, BELIEF, EUPHORIA)

## Phase 2: Tests (TDD)
- [ ] T003 Create tests/test_nupl.py with test_calculate_nupl_basic()
- [ ] T004 Add test_nupl_zones() for zone classification
- [ ] T005 Add test_nupl_edge_cases() for zero/negative values

## Phase 3: Implementation
- [ ] T006 Create scripts/metrics/nupl.py with calculate_nupl()
- [ ] T007 Implement _classify_zone() helper
- [ ] T008 Add structured logging

## Phase 4: API
- [ ] T009 Add GET /api/metrics/nupl endpoint to api/main.py
- [ ] T010 Run all tests: `uv run pytest tests/test_nupl.py -v`

**Effort**: 1-2 hours
**Dependencies**: realized_metrics.py (realized_cap calculation)
