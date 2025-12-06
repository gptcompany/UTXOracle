# Tasks: Address Clustering & CoinJoin Detection

**Input**: Design documents from `/specs/013-address-clustering/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Create scripts/clustering/ directory structure
- [x] T002 [P] Create scripts/clustering/__init__.py
- [x] T003 [P] Create empty tests/test_clustering.py

---

## Phase 2: Foundational - Union-Find

- [x] T004 [P] Write test_union_find_basic() in tests/test_clustering.py
- [x] T005 [P] Write test_union_find_transitivity() in tests/test_clustering.py
- [x] T006 Implement UnionFind class in scripts/clustering/union_find.py
- [x] T007 Run tests - verify T004-T005 pass

---

## Phase 3: User Story 1 - Multi-Input Clustering (P1) 🎯 MVP

**Goal**: Cluster addresses that appear together in transaction inputs

### Tests (TDD RED)
- [x] T008 [P] [US1] Write test_cluster_single_tx() in tests/test_clustering.py
- [x] T009 [P] [US1] Write test_cluster_multiple_tx() in tests/test_clustering.py
- [x] T010 [P] [US1] Write test_cluster_transitivity() in tests/test_clustering.py

### Implementation (TDD GREEN)
- [x] T011 [US1] Add AddressCluster dataclass to scripts/clustering/address_clustering.py
- [x] T012 [US1] Implement cluster_addresses() in scripts/clustering/address_clustering.py
- [x] T013 [US1] Implement get_cluster_stats() in scripts/clustering/address_clustering.py
- [x] T014 [US1] Run tests - verify T008-T010 pass

**Checkpoint**: Address clustering working ✅

---

## Phase 4: User Story 2 - CoinJoin Detection (P1)

**Goal**: Identify CoinJoin transactions with confidence scoring

### Tests (TDD RED)
- [x] T015 [P] [US2] Write test_detect_generic_coinjoin() in tests/test_clustering.py
- [x] T016 [P] [US2] Write test_detect_wasabi() in tests/test_clustering.py
- [x] T017 [P] [US2] Write test_detect_whirlpool() in tests/test_clustering.py
- [x] T018 [P] [US2] Write test_normal_tx_not_coinjoin() in tests/test_clustering.py

### Implementation (TDD GREEN)
- [x] T019 [US2] Add CoinJoinResult dataclass to scripts/clustering/coinjoin_detector.py
- [x] T020 [US2] Implement _check_equal_outputs() in scripts/clustering/coinjoin_detector.py
- [x] T021 [US2] Implement _check_known_patterns() in scripts/clustering/coinjoin_detector.py
- [x] T022 [US2] Implement detect_coinjoin() in scripts/clustering/coinjoin_detector.py
- [x] T023 [US2] Run tests - verify T015-T018 pass

**Checkpoint**: CoinJoin detection working ✅

---

## Phase 5: User Story 3 - Change Detection (P2)

**Goal**: Identify change outputs in transactions

### Tests (TDD RED)
- [x] T024 [P] [US3] Write test_detect_odd_amount_change() in tests/test_clustering.py
- [x] T025 [P] [US3] Write test_detect_small_output_change() in tests/test_clustering.py

### Implementation (TDD GREEN)
- [x] T026 [US3] Add ChangeDetectionResult dataclass to scripts/clustering/change_detector.py
- [x] T027 [US3] Implement detect_change_outputs() in scripts/clustering/change_detector.py
- [x] T028 [US3] Run tests - verify T024-T025 pass

**Checkpoint**: Change detection working ✅

---

## Phase 6: User Story 4 - Integration with Whale Tracking (P1)

**Goal**: Improve whale detection using clustering and CoinJoin filter

### Tests (TDD RED)
- [x] T029 [P] [US4] Write test_whale_detection_with_clustering() in tests/test_clustering.py
- [x] T030 [P] [US4] Write test_whale_detection_filters_coinjoin() in tests/test_clustering.py

### Implementation (TDD GREEN)
- [x] T031 [US4] Add clustering parameter to whale_flow_detector.py
- [x] T032 [US4] Add coinjoin_filter parameter to whale_flow_detector.py
- [x] T033 [US4] Implement filter_coinjoins() in scripts/clustering/__init__.py
- [x] T034 [US4] Run tests - verify T029-T030 pass

**Checkpoint**: Integration with whale tracking complete ✅

---

## Phase 7: Database Integration

- [x] T035 Add address_clusters table to scripts/init_metrics_db.py
- [x] T036 Add coinjoin_cache table to scripts/init_metrics_db.py
- [x] T037 Implement save_cluster() in scripts/clustering/address_clustering.py
- [x] T038 Implement save_coinjoin_result() in scripts/clustering/coinjoin_detector.py

---

## Phase 8: Polish

- [x] T039 [P] Add module docstrings to all clustering modules
- [x] T040 [P] Export public API from scripts/clustering/__init__.py
- [x] T041 Run full test suite - verify ≥85% coverage ✅ (achieved: 87%)
- [x] T042 Create integration test in tests/integration/test_clustering_whale.py

---

## Dependencies

```
Phase 1 (Setup)        → No dependencies
Phase 2 (Union-Find)   → Phase 1
Phase 3 (US1)         → Phase 2 🎯 MVP
Phase 4 (US2)         → Phase 1
Phase 5 (US3)         → Phase 1
Phase 6 (US4)         → Phase 3, Phase 4
Phase 7 (DB)          → Phase 3, Phase 4
Phase 8 (Polish)      → All previous
```

## Summary

| Phase | Tasks | Completed |
|-------|-------|-----------|
| Setup | 3 | 3 ✅ |
| Foundation | 4 | 4 ✅ |
| US1 | 7 | 7 ✅ |
| US2 | 9 | 9 ✅ |
| US3 | 5 | 5 ✅ |
| US4 | 6 | 6 ✅ |
| DB | 4 | 4 ✅ |
| Polish | 4 | 4 ✅ |
| **Total** | **42** | **42/42** ✅ |

## Status: COMPLETE ✅

All 42 tasks completed. Bug hunting passed (6 rounds, 0 bugs found).
- **Test coverage**: 87% (target: 85%)
- **Total tests**: 65 passing
- **Modules**: 5 files, 260 lines of code
