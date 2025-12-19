# Tasks: Mining Economics (Hash Ribbons + Mining Pulse)

**Input**: Design documents from `/specs/030-hash-ribbons/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD enforced per Constitution Principle II. Tests FIRST (RED), then implementation (GREEN).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic tasks
- **[Story]**: Which user story (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure and shared dependencies

- [x] T001 Add MiningPulseZone enum to scripts/models/metrics_models.py
- [x] T002 [P] Create scripts/data/ directory if not exists

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared models that ALL user stories depend on

**⚠️ CRITICAL**: User stories cannot begin until these models exist

- [x] T003 Add HashRibbonsResult dataclass to scripts/models/metrics_models.py (after T001)
- [x] T004 Add MiningPulseResult dataclass to scripts/models/metrics_models.py (after T003)
- [x] T005 Add MiningEconomicsResult dataclass to scripts/models/metrics_models.py (after T004)

**Checkpoint**: All models ready - user story implementation can begin

---

## Phase 3: User Story 1 - Mining Pulse (Priority: P1) 🎯 MVP

**Goal**: Real-time block interval analysis for hashrate change detection (RPC-only, no external deps)

**Independent Test**: `curl http://localhost:8000/api/metrics/mining-pulse` returns pulse_zone

### Tests for User Story 1 (TDD - RED phase)

- [x] T006 [US1] Create tests/test_mining_economics.py with test_calculate_mining_pulse_returns_valid_result
- [x] T007 [US1] Add test_mining_pulse_zone_classification tests to tests/test_mining_economics.py
- [x] T008 [US1] Add test_mining_pulse_rpc_integration test to tests/test_mining_economics.py

### Implementation for User Story 1 (GREEN phase)

- [x] T009 [US1] Create scripts/metrics/mining_economics.py with calculate_mining_pulse function
- [x] T010 [US1] Add MiningPulseResponse Pydantic model to api/main.py
- [x] T011 [US1] Add GET /api/metrics/mining-pulse endpoint to api/main.py

**Checkpoint**: Mining Pulse fully functional and testable independently

---

## Phase 4: User Story 2 - Hash Ribbons (Priority: P2)

**Goal**: Miner capitulation/recovery signals from 30d/60d MA crossover (external API)

**Independent Test**: `curl http://localhost:8000/api/metrics/hash-ribbons` returns ribbon_signal

### Tests for User Story 2 (TDD - RED phase)

- [x] T012 [US2] Add test_fetch_hashrate_from_mempool_api test to tests/test_mining_economics.py
- [x] T013 [US2] Add test_calculate_hash_ribbons_ma_crossover test to tests/test_mining_economics.py
- [x] T014 [US2] Add test_hash_ribbons_capitulation_days_counting test to tests/test_mining_economics.py

### Implementation for User Story 2 (GREEN phase)

- [x] T015 [P] [US2] Create scripts/data/hashrate_fetcher.py with fetch_hashrate_data function and input validation for API responses
- [x] T016 [US2] Add TTL cache wrapper to scripts/data/hashrate_fetcher.py
- [x] T017 [US2] Add calculate_hash_ribbons function to scripts/metrics/mining_economics.py
- [x] T018 [US2] Add HashRibbonsResponse Pydantic model to api/main.py
- [x] T019 [US2] Add GET /api/metrics/hash-ribbons endpoint to api/main.py

**Checkpoint**: Hash Ribbons fully functional and testable independently

---

## Phase 5: User Story 3 - Combined Mining Economics (Priority: P3)

**Goal**: Combined view with aggregated signal interpretation

**Independent Test**: `curl http://localhost:8000/api/metrics/mining-economics` returns combined_signal

### Tests for User Story 3 (TDD - RED phase)

- [x] T020 [US3] Add test_derive_combined_signal_logic test to tests/test_mining_economics.py
- [x] T021 [US3] Add test_mining_economics_with_api_unavailable test to tests/test_mining_economics.py

### Implementation for User Story 3 (GREEN phase)

- [x] T022 [US3] Add derive_combined_signal function to scripts/metrics/mining_economics.py
- [x] T023 [US3] Add calculate_mining_economics function to scripts/metrics/mining_economics.py
- [x] T024 [US3] Add MiningEconomicsResponse Pydantic model to api/main.py
- [x] T025 [US3] Add GET /api/metrics/mining-economics endpoint to api/main.py
- [x] T026 [US3] Add GET /api/metrics/mining-economics/history endpoint to api/main.py

**Checkpoint**: All three user stories complete and integrated

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, documentation, cleanup

- [x] T027 Run quickstart.md validation (curl all endpoints, verify responses)
- [x] T028 Verify test coverage >= 80% for mining_economics.py (93% achieved)
- [x] T029 Add docstrings to all public functions in scripts/metrics/mining_economics.py
- [x] T030 Update docs/ARCHITECTURE.md with spec-030 module documentation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on T001 (MiningPulseZone enum first)
- **User Story 1 (Phase 3)**: Depends on Foundational (T003-T005 complete)
- **User Story 2 (Phase 4)**: Depends on Foundational (T003-T005 complete)
- **User Story 3 (Phase 5)**: Depends on US1 + US2 completion
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Independent - only needs models from Foundational
- **User Story 2 (P2)**: Independent - only needs models from Foundational
- **User Story 3 (P3)**: Depends on US1 + US2 (uses both calculate functions)

### Within Each User Story (TDD Flow)

1. Tests MUST be written and FAIL first (RED)
2. Implementation makes tests pass (GREEN)
3. Verify all tests pass before checkpoint

### Parallel Opportunities

Phase 1:
- T001 + T002 can run in parallel (different files)

Phase 3-4 (after Foundational):
- US1 and US2 can be implemented in parallel by different developers
- T015 (hashrate_fetcher.py) is independent file, marked [P]

---

## Parallel Example: User Story 2

```bash
# T015 can run in parallel with T012-T014 (different files):
Task: "Create scripts/data/hashrate_fetcher.py with fetch_hashrate_data function"

# Tests in same file must be sequential:
Task: "Add test_fetch_hashrate_from_mempool_api test to tests/test_mining_economics.py"
# Then:
Task: "Add test_calculate_hash_ribbons_ma_crossover test to tests/test_mining_economics.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T005)
3. Complete Phase 3: User Story 1 (T006-T011)
4. **STOP and VALIDATE**: Test Mining Pulse independently
5. Deploy if ready (Mining Pulse works RPC-only, no external deps)

### Incremental Delivery

1. Setup + Foundational → Models ready
2. Add User Story 1 → Test → Deploy (MVP - RPC-only mining pulse)
3. Add User Story 2 → Test → Deploy (adds external API hash ribbons)
4. Add User Story 3 → Test → Deploy (combined view)
5. Polish → Final release

---

## Notes

- [P] tasks = different files, no dependencies
- [E] tasks = not used (no complex algorithms requiring exploration)
- [Story] label maps task to user story for traceability
- All models in same file (metrics_models.py) so T003-T005 are sequential
- Tests in same file (test_mining_economics.py) so test tasks are sequential within story
- TDD enforced: write failing test → implement → verify pass
- Commit after each task or logical group
