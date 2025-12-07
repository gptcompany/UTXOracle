# Tasks: Backtest Validation for spec-009 Metrics

**Spec**: spec-015
**Total Tasks**: 18
**Estimated Effort**: 2-3 days

---

## Task Overview

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup | 2 | Pending |
| Framework | 6 | Pending |
| Validation | 4 | Pending |
| Reports | 3 | Pending |
| Finalization | 3 | Pending |

---

## Phase 1: Setup

### Task 015-001: Create feature branch
**Priority**: P0
**Effort**: 5 min
**Dependencies**: None

```bash
git checkout -b 015-backtest-validation
```

**Acceptance Criteria**:
- [ ] Branch created from main

---

### Task 015-002: Create directory structure
**Priority**: P0
**Effort**: 5 min
**Dependencies**: 015-001

```bash
mkdir -p scripts/backtest
mkdir -p reports/validation
touch scripts/backtest/__init__.py
```

**Acceptance Criteria**:
- [ ] Directories created
- [ ] `__init__.py` created

---

## Phase 2: Framework Implementation

### Task 015-003: Implement MetricValidationResult dataclass
**Priority**: P1
**Effort**: 20 min
**Dependencies**: 015-002

**File**: `scripts/backtest/metric_validator.py`

**Actions**:
1. Create `MetricValidationResult` dataclass
2. Include all performance metrics
3. Include statistical significance fields
4. Include cross-validation fields

**Acceptance Criteria**:
- [ ] Dataclass fully defined
- [ ] All fields documented

---

### Task 015-004: Implement baseline generators
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-002

**File**: `scripts/backtest/baselines.py`

**Functions**:
- `random_baseline()` - Shuffle signals 1000x
- `buyhold_baseline()` - Buy-and-hold Sharpe

**Acceptance Criteria**:
- [ ] Random baseline deterministic (seeded)
- [ ] Buy-and-hold calculation correct

---

### Task 015-005: [E] Implement statistical tests
**Priority**: P1
**Effort**: 45 min
**Dependencies**: 015-002

**File**: `scripts/backtest/statistics.py`

**Functions**:
- `t_test_vs_baseline()` - One-sample t-test
- `cohens_d()` - Effect size
- `bootstrap_ci()` - Confidence intervals
- `t_cdf()` - t-distribution CDF (pure Python)

**Acceptance Criteria**:
- [ ] t-test matches scipy output (within tolerance)
- [ ] Cohen's d interpretation correct
- [ ] Bootstrap CI reasonable

---

### Task 015-006: [E] Implement cross-validation
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-002

**File**: `scripts/backtest/cross_validation.py`

**Functions**:
- `kfold_split()` - Split data into k folds
- `cross_validate()` - Run CV and return mean/std

**Acceptance Criteria**:
- [ ] Folds non-overlapping
- [ ] All data used exactly once
- [ ] Results reproducible

---

### Task 015-007: Implement MetricValidator class
**Priority**: P1
**Effort**: 1 hour
**Dependencies**: 015-003, 015-004, 015-005, 015-006

**File**: `scripts/backtest/metric_validator.py`

**Methods**:
- `__init__()` - Configure validation parameters
- `validate()` - Full validation pipeline
- `_calculate_performance()` - Sharpe, win rate, etc.

**Acceptance Criteria**:
- [ ] Full pipeline working
- [ ] Returns MetricValidationResult

---

### Task 015-008: Implement report generator
**Priority**: P1
**Effort**: 45 min
**Dependencies**: 015-003

**File**: `scripts/backtest/report_generator.py`

**Functions**:
- `generate_validation_report()` - JSON + Markdown
- `generate_comparative_report()` - Ranking
- `interpret_cohens_d()` - Effect size interpretation

**Acceptance Criteria**:
- [ ] JSON valid and complete
- [ ] Markdown well-formatted
- [ ] Ranking correct

---

## Phase 3: Run Validations

### Task 015-009: Load historical data
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-007

**File**: `scripts/backtest/run_validations.py`

**Actions**:
1. Query DuckDB for historical metric signals
2. Load price data from UTXOracle historical
3. Ensure 180+ days of data

**Acceptance Criteria**:
- [ ] Data loaded successfully
- [ ] Minimum 180 days

---

### Task 015-010: Validate Symbolic Dynamics
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-009

**Actions**:
1. Extract symbolic dynamics signals
2. Run full validation
3. Generate report

**Acceptance Criteria**:
- [ ] Validation complete
- [ ] Report generated

---

### Task 015-011: Validate Power Law
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-009

**Actions**:
1. Extract power law signals
2. Run full validation
3. Generate report

**Acceptance Criteria**:
- [ ] Validation complete
- [ ] Report generated

---

### Task 015-012: Validate Fractal Dimension
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-009

**Actions**:
1. Extract fractal dimension signals
2. Run full validation
3. Generate report

**Acceptance Criteria**:
- [ ] Validation complete
- [ ] Report generated

---

## Phase 4: Reports and Analysis

### Task 015-013: Generate comparative ranking
**Priority**: P1
**Effort**: 30 min
**Dependencies**: 015-010, 015-011, 015-012

**File**: `reports/validation/comparative_ranking.md`

**Content**:
1. Ranking by Sharpe ratio
2. Ranking by win rate
3. Significance summary
4. Recommendations (increase/maintain/decrease weight)

**Acceptance Criteria**:
- [ ] All metrics ranked
- [ ] Clear recommendations

---

### Task 015-014: Update fusion weights based on results
**Priority**: P2
**Effort**: 30 min
**Dependencies**: 015-013

**Actions**:
1. Review validation results
2. If metric not significant, recommend weight reduction
3. Update spec-014 if needed

**Acceptance Criteria**:
- [ ] Weights reviewed
- [ ] spec-014 updated if needed

---

### Task 015-015: Create research notes
**Priority**: P2
**Effort**: 30 min
**Dependencies**: 015-013

**File**: `research/spec-009-validation-results.md`

**Content**:
1. Summary of findings
2. Potential publication opportunities
3. Methodology details

**Acceptance Criteria**:
- [ ] Research notes complete
- [ ] Publication potential assessed

---

## Phase 5: Finalization

### Task 015-016: Add unit tests
**Priority**: P1
**Effort**: 1 hour
**Dependencies**: 015-007

**File**: `tests/test_metric_validator.py`

**Tests**:
```python
def test_random_baseline_deterministic()
def test_buyhold_baseline_correct()
def test_t_test_known_values()
def test_cohens_d_interpretation()
def test_kfold_split_coverage()
def test_full_validation_pipeline()
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Coverage > 80%

---

### Task 015-017: Update documentation
**Priority**: P2
**Effort**: 15 min
**Dependencies**: 015-013

**Files**: `CLAUDE.md`, `docs/ARCHITECTURE.md`

**Acceptance Criteria**:
- [ ] Documentation updated
- [ ] Validation process documented

---

### Task 015-018: Create PR and merge
**Priority**: P0
**Effort**: 15 min
**Dependencies**: All previous tasks

**Actions**:
1. Run final tests
2. Format code
3. Create PR with validation summary
4. Merge after review

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] PR merged
- [ ] Reports committed

---

## Task Summary

```
Total Tasks: 18
P0 (Critical): 3
P1 (High): 12
P2 (Medium): 3

Estimated Time:
- Setup: 10 min
- Framework: ~4 hours
- Validation: ~2 hours
- Reports: ~1.5 hours
- Finalization: ~2 hours
- Total: ~10 hours (2 days)
```

---

## Output Artifacts

After completion:
```
reports/validation/
├── symbolic_dynamics_validation.json
├── symbolic_dynamics_validation.md
├── power_law_validation.json
├── power_law_validation.md
├── fractal_dimension_validation.json
├── fractal_dimension_validation.md
└── comparative_ranking.md

research/
└── spec-009-validation-results.md
```
