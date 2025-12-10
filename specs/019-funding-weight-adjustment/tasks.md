# Tasks: Derivatives Weight Reduction (spec-019)

**Input**: Design documents from `/specs/019-funding-weight-adjustment/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, quickstart.md ✅

**Tests**: Included per NFR-002 requirement in spec.md

**Organization**: Tasks grouped by functional requirement (FR-001, FR-002, FR-003) since this is a configuration change, not a user-story feature.

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[FR]**: Which functional requirement this task belongs to

---

## Phase 1: Setup

**Purpose**: Verify prerequisites and ensure clean starting point

- [x] T001 Verify on correct branch `019-funding-weight-adjustment` via `git branch --show-current`
- [x] T002 Run existing test suite to confirm baseline passes via `uv run pytest tests/test_monte_carlo_fusion.py -v`
- [x] T003 Verify SOPR module exists and is importable via `python -c "from scripts.metrics.sopr import BlockSOPR"`

**Checkpoint**: All prerequisites verified, ready for implementation ✅

---

## Phase 2: FR-001 - Update ENHANCED_WEIGHTS (Priority: P1) 🎯 MVP

**Goal**: Update weight distribution to reduce derivatives signals from 21% to 10%, redistributing to higher-evidence signals

**Independent Test**: Run `python -c "from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS; print(sum(ENHANCED_WEIGHTS.values()))"` - should return `1.0`

### Implementation

- [x] T004 [FR-001] Update `ENHANCED_WEIGHTS` dictionary with new values in `scripts/metrics/monte_carlo_fusion.py`:
  - `whale`: 0.21 → 0.24 (+0.03)
  - `funding`: 0.12 → 0.05 (-0.07)
  - `oi`: 0.09 → 0.05 (-0.04)
  - `wasserstein`: 0.04 → 0.08 (+0.04)
  - `cointime`: 0.12 → 0.14 (+0.02)
  - Add `sopr`: 0.02 (NEW)

- [x] T005 [FR-001] Add weight sum assertion after `ENHANCED_WEIGHTS` definition in `scripts/metrics/monte_carlo_fusion.py`

- [x] T006 [FR-001] Update test assertions for new weights in `tests/test_monte_carlo_fusion.py`

**Checkpoint**: Weights updated, sum verified = 1.0, basic tests pass ✅

---

## Phase 3: FR-002 - SOPR Signal Integration (Priority: P2)

**Goal**: Add SOPR signal to enhanced_fusion() function with full end-to-end integration

**Independent Test**: Call `enhanced_fusion(sopr_vote=0.5, sopr_conf=0.9)` and verify `sopr_weight > 0` in result

### Implementation

- [x] T007 [FR-002] Add `sopr_vote: Optional[float] = None` parameter to `enhanced_fusion()` in `scripts/metrics/monte_carlo_fusion.py`

- [x] T008 [FR-002] Add `sopr_conf: Optional[float] = None` parameter to `enhanced_fusion()` in `scripts/metrics/monte_carlo_fusion.py`

- [x] T009 [FR-002] Add SOPR component handling in `enhanced_fusion()` body in `scripts/metrics/monte_carlo_fusion.py`

- [x] T010 [FR-002] Add `sopr_weight: float = 0.0` field to `EnhancedFusionResult` dataclass in `scripts/metrics/monte_carlo_fusion.py`

- [x] T011 [FR-002] Update result construction to include `sopr_weight=normalized_weights.get("sopr", 0.0)` in `scripts/metrics/monte_carlo_fusion.py`

- [x] T012 [FR-002] Add `sopr_to_vote()` helper function in `scripts/metrics/monte_carlo_fusion.py`:
  ```python
  def sopr_to_vote(sopr_value: float, confidence: float) -> tuple[float, float]:
      """Convert SOPR to fusion vote. SOPR>1=bearish, SOPR<1=bullish."""
      if sopr_value > 1.0:
          vote = -min(0.8, (sopr_value - 1.0) * 2)
      elif sopr_value < 1.0:
          vote = min(0.8, (1.0 - sopr_value) * 2)
      else:
          vote = 0.0
      return (vote, confidence)
  ```

- [x] T013 [FR-002] Wire SOPR into `scripts/daily_analysis.py`:
  - Import: `from scripts.metrics.sopr import calculate_block_sopr`
  - Import: `from scripts.metrics.monte_carlo_fusion import sopr_to_vote`
  - Calculate SOPR in analysis flow
  - Convert to vote/conf via `sopr_to_vote()`
  - Pass `sopr_vote` and `sopr_conf` to `enhanced_fusion()`

- [x] T014 [FR-002] Add SOPR integration test `test_fusion_with_sopr()` in `tests/test_monte_carlo_fusion.py`

- [x] T015 [FR-002] Add test for `sopr_to_vote()` function in `tests/test_monte_carlo_fusion.py`

**Checkpoint**: SOPR signal fully integrated end-to-end, all tests pass ✅

---

## Phase 4: FR-003 - Backward Compatibility Verification (Priority: P3)

**Goal**: Ensure existing callers work without modification

**Independent Test**: Call `enhanced_fusion()` with only original parameters and verify it returns valid result

### Verification

- [x] T016 [FR-003] Add backward compatibility test `test_backward_compatibility_without_sopr()` in `tests/test_monte_carlo_fusion.py`

- [x] T017 [FR-003] Run full test suite to verify no regressions via `uv run pytest tests/test_monte_carlo_fusion.py -v`

**Checkpoint**: Backward compatibility verified, all tests pass ✅

---

## Phase 5: Polish & Validation

**Purpose**: Final validation and documentation

- [x] T018 [P] Verify import works without errors via `python -c "from scripts.metrics.monte_carlo_fusion import enhanced_fusion, EnhancedFusionResult, ENHANCED_WEIGHTS, sopr_to_vote"`

- [x] T019 [P] Run full project test suite via `uv run pytest tests/ -v --tb=short`

- [x] T020 Run quickstart.md validation commands from `specs/019-funding-weight-adjustment/quickstart.md`

**Checkpoint**: All acceptance criteria met, ready for merge ✅

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **FR-001 (Phase 2)**: Depends on Setup - CORE CHANGE
- **FR-002 (Phase 3)**: Depends on FR-001 (needs SOPR weight in dict)
- **FR-003 (Phase 4)**: Depends on FR-002 (verifies full integration)
- **Polish (Phase 5)**: Depends on all FRs complete

### Task Dependencies Within Phases

**Phase 2 (FR-001)**:
- T004 → T005 → T006 (sequential - same file modifications)

**Phase 3 (FR-002)**:
- T007, T008 can run in parallel (separate params)
- T009 depends on T007, T008
- T010 can run parallel to T007-T009
- T011 depends on T010
- T012 (sopr_to_vote) can run parallel to T007-T011
- T013 (daily_analysis wiring) depends on T012
- T014, T015 (tests) depend on T013

**Phase 4 (FR-003)**:
- T016 → T017 (test first, then full suite)

**Phase 5 (Polish)**:
- T018, T019 can run in parallel
- T020 depends on T018, T019

### Parallel Opportunities

```bash
# Phase 2: Sequential (same file)
T004 → T005 → T006

# Phase 3: Some parallelism
T007 + T008 in parallel
T010 in parallel with T009
T012 in parallel with T007-T011
T013 → T014 + T015 sequential

# Phase 5: High parallelism
T018 + T019 in parallel
```

---

## Implementation Strategy

### MVP First (FR-001 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: FR-001 (weight update)
3. **STOP and VALIDATE**: Weights sum to 1.0, existing tests pass
4. This alone delivers the core value (derivatives weight reduction)

### Full Implementation

1. Complete Setup + FR-001 → Weight reduction achieved
2. Add FR-002 → SOPR signal integrated
3. Add FR-003 verification → Backward compat confirmed
4. Polish → Ready for merge

---

## Acceptance Criteria Mapping

| Acceptance Criteria | Task(s) |
|---------------------|---------|
| `ENHANCED_WEIGHTS` updated | T004 |
| Weights sum verified = 1.0 | T005 |
| SOPR signal integrated (end-to-end) | T007-T015 |
| All existing tests pass | T006, T017 |
| Backtest stable (not in scope) | Manual verification |

---

## Notes

- This is a configuration change, not a feature implementation
- Effort estimate: 1 day (from spec.md)
- No new files created, only modifications to existing files
- SOPR module dependency already on main (spec-016)
- Performance target: <10ms per fusion call (existing)
- Commit after each phase checkpoint
