# Tasks: Revived Supply (spec-024)

## Phase 1: Setup
- [ ] T001 Add RevivedSupplyResult dataclass to scripts/models/metrics_models.py
- [ ] T002 Add RevivedZone enum (DORMANT, NORMAL, ELEVATED, SPIKE)

## Phase 2: Tests (TDD)
- [ ] T003 Create tests/test_revived_supply.py with test_calculate_basic()
- [ ] T004 Add test_age_threshold_filter() for 1y/2y/5y thresholds
- [ ] T005 Add test_window_filter() for 7d/30d/90d windows
- [ ] T006 Add test_signal_zones() for zone classification

## Phase 3: Implementation
- [ ] T007 Create scripts/metrics/revived_supply.py with calculate_revived_supply()
- [ ] T008 Implement _filter_by_age() helper
- [ ] T009 Implement _classify_zone() helper
- [ ] T010 Add structured logging

## Phase 4: API
- [ ] T011 Add GET /api/metrics/revived-supply endpoint to api/main.py
- [ ] T012 Run all tests: `uv run pytest tests/test_revived_supply.py -v`

**Effort**: 2-3 hours
**Dependencies**: utxo_lifecycle_full VIEW (age_days, spent_timestamp, is_spent)
