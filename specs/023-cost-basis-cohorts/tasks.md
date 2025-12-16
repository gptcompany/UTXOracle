# Tasks: STH/LTH Cost Basis (spec-023)

## Phase 1: Setup
- [ ] T001 Add CostBasisResult dataclass to scripts/models/metrics_models.py

## Phase 2: Tests (TDD)
- [ ] T002 Create tests/test_cost_basis.py with test_calculate_basic()
- [ ] T003 Add test_sth_lth_breakdown() for cohort split
- [ ] T004 Add test_mvrv_calculation() for price/cost_basis ratio
- [ ] T005 Add test_empty_cohort() edge case

## Phase 3: Implementation
- [ ] T006 Create scripts/metrics/cost_basis.py with calculate_cost_basis()
- [ ] T007 Implement _calculate_cohort_mvrv() helper
- [ ] T008 Add structured logging

## Phase 4: API
- [ ] T009 Add GET /api/metrics/cost-basis endpoint to api/main.py
- [ ] T010 Run all tests: `uv run pytest tests/test_cost_basis.py -v`

**Effort**: 2-3 hours
**Dependencies**: utxo_lifecycle_full VIEW (cohort, creation_price_usd)
