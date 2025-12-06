# Tasks: Evidence-Based Fusion Weights

**Spec**: spec-014
**Total Tasks**: 13
**TDD**: Required per Constitution Principle II

---

## Task Overview

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup | 2 | Pending |
| Tests (RED) | 1 | Pending |
| Implementation (GREEN) | 6 | Pending |
| Validation | 2 | Pending |
| Documentation | 2 | Pending |

---

## Phase 1: Setup

### Task 014-001: Create feature branch
**Priority**: P0
**Dependencies**: None

```bash
git checkout -b 014-evidence-based-weights
```

**Acceptance Criteria**:
- [ ] Branch created from main
- [ ] Branch name follows convention

---

### Task 014-002: Review current weight implementation
**Priority**: P0
**Dependencies**: None

**Actions**:
1. Read `scripts/metrics/monte_carlo_fusion.py`
2. Identify where weights are defined
3. Note any hardcoded values
4. Check for existing environment variable usage

**Acceptance Criteria**:
- [ ] Current implementation understood
- [ ] All weight references identified

---

## Phase 2: Tests (RED Phase)

**NOTE**: Write tests FIRST. They MUST FAIL before implementation.

### Task 014-003: [P] Add unit tests for weights
**Priority**: P1
**Dependencies**: 014-002

**File**: `tests/test_monte_carlo_fusion.py`

**Tests to add**:
```python
def test_evidence_based_weights_sum_to_one()
def test_legacy_weights_sum_to_one()
def test_weight_validation_rejects_invalid_sum()
def test_weight_validation_rejects_negative()
def test_load_weights_from_env_default()
def test_load_weights_from_env_legacy()
```

**Run**: `uv run pytest tests/test_monte_carlo_fusion.py -v -k "weight"` → **Must FAIL**

**Acceptance Criteria**:
- [ ] Tests written
- [ ] Tests fail (constants/functions don't exist yet)

---

## Phase 3: Implementation (GREEN Phase)

### Task 014-004: Define weight constants
**Priority**: P1
**Dependencies**: 014-003

**File**: `scripts/metrics/monte_carlo_fusion.py`

**Actions**:
1. Add `LEGACY_WEIGHTS` constant (preserves spec-009)
2. Add `EVIDENCE_BASED_WEIGHTS` constant
3. Add docstrings with evidence sources
4. Ensure both sum to 1.0

**Code**:
```python
# Evidence-based weights (spec-014)
# Source: Contadino Galattico analysis (42 sources)
EVIDENCE_BASED_WEIGHTS = {
    "whale": 0.15,      # Reduced: Grade D evidence
    "utxo": 0.20,       # Increased: Grade A evidence
    "funding": 0.05,    # Reduced: LAGGING (Coinbase)
    "oi": 0.10,         # Maintained: Grade B
    "power_law": 0.15,  # Increased: Regime detection
    "symbolic": 0.15,   # Maintained: Needs validation
    "fractal": 0.10,    # Maintained: Needs validation
    "wasserstein": 0.10,# NEW: Grade A (Horvath 2021)
}
```

**Acceptance Criteria**:
- [ ] Both constants defined
- [ ] Both sum to exactly 1.0
- [ ] Evidence documented in comments

---

### Task 014-005: Add weight validation function
**Priority**: P1
**Dependencies**: 014-004

**File**: `scripts/metrics/monte_carlo_fusion.py`

**Actions**:
1. Create `validate_weights()` function
2. Check sum equals 1.0 (within tolerance)
3. Check all values non-negative
4. Raise descriptive errors

**Acceptance Criteria**:
- [ ] Function validates sum = 1.0
- [ ] Function validates non-negative values
- [ ] Clear error messages

---

### Task 014-006: Add environment configuration
**Priority**: P1
**Dependencies**: 014-004

**Files**: `.env.example`, `scripts/metrics/monte_carlo_fusion.py`

**Actions**:
1. Add weight variables to `.env.example`
2. Create `load_weights_from_env()` function
3. Support `FUSION_USE_LEGACY_WEIGHTS` toggle
4. Default to evidence-based weights

**Acceptance Criteria**:
- [ ] `.env.example` updated
- [ ] Environment loading works
- [ ] Legacy toggle works

---

### Task 014-007: Update fusion function
**Priority**: P1
**Dependencies**: 014-005, 014-006

**File**: `scripts/metrics/monte_carlo_fusion.py`

**Actions**:
1. Modify `enhanced_monte_carlo_fusion()` signature
2. Add optional `weights` parameter
3. Use `load_weights_from_env()` as default
4. Call `validate_weights()` at start

**Run**: `uv run pytest tests/test_monte_carlo_fusion.py -v -k "weight"` → **Must PASS**

**Acceptance Criteria**:
- [ ] Function accepts custom weights
- [ ] Defaults to evidence-based
- [ ] Validation runs on every call
- [ ] All weight tests now pass (GREEN)

---

### Task 014-008: Update daily_analysis.py
**Priority**: P2
**Dependencies**: 014-007

**File**: `scripts/daily_analysis.py`

**Actions**:
1. Remove any hardcoded weights
2. Rely on defaults from monte_carlo_fusion.py
3. Add logging for which weights are used

**Acceptance Criteria**:
- [ ] No hardcoded weights
- [ ] Logs weight configuration

---

### Task 014-009: Add fusion breakdown API endpoint
**Priority**: P2
**Dependencies**: 014-007

**File**: `api/main.py`

**Actions**:
1. Add `/api/metrics/fusion/breakdown` endpoint
2. Return all 8 component weights and current votes
3. Include evidence grade in response

**Response Schema**:
```python
@app.get("/api/metrics/fusion/breakdown")
def get_fusion_breakdown():
    return {
        "components": {
            "whale": {"weight": 0.15, "vote": None, "grade": "D"},
            "utxo": {"weight": 0.20, "vote": None, "grade": "A"},
            "funding": {"weight": 0.05, "vote": None, "grade": "B-LAGGING"},
            "oi": {"weight": 0.10, "vote": None, "grade": "B"},
            "power_law": {"weight": 0.15, "vote": None, "grade": "C"},
            "symbolic": {"weight": 0.15, "vote": None, "grade": "C"},
            "fractal": {"weight": 0.10, "vote": None, "grade": "C"},
            "wasserstein": {"weight": 0.10, "vote": None, "grade": "A"},
        },
        "total_weight": 1.0,
        "weight_source": "evidence-based"  # or "legacy"
    }
```

**Acceptance Criteria**:
- [ ] Endpoint returns all component weights
- [ ] Endpoint returns evidence grade per component
- [ ] Returns weight source (evidence-based or legacy)

---

## Phase 4: Validation

### Task 014-010: Run full test suite
**Priority**: P1
**Dependencies**: 014-007

**Command**:
```bash
uv run pytest tests/test_monte_carlo_fusion.py -v
uv run pytest tests/ -v --tb=short
```

**Acceptance Criteria**:
- [ ] All existing tests pass
- [ ] No regressions

---

### Task 014-011: Backtest comparison
**Priority**: P2
**Dependencies**: 014-007

**Actions**:
1. Run backtest with legacy weights
2. Run backtest with evidence-based weights
3. Compare Sharpe ratios
4. Document results

**Acceptance Criteria**:
- [ ] Both backtests complete
- [ ] Sharpe comparison documented
- [ ] No significant degradation

---

## Phase 5: Documentation

### Task 014-012: Update CLAUDE.md
**Priority**: P2
**Dependencies**: 014-007

**Actions**:
1. Add note about evidence-based weights
2. Reference Contadino Galattico analysis
3. Document how to switch to legacy

**Acceptance Criteria**:
- [ ] CLAUDE.md updated
- [ ] Clear instructions for configuration

---

### Task 014-013: Create PR and merge
**Priority**: P0
**Dependencies**: All previous tasks

**Actions**:
1. Run final tests
2. Format code: `ruff check . && ruff format .`
3. Create PR with summary
4. Merge after review

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Code formatted
- [ ] PR merged

---

## Task Summary

| Priority | Count |
|----------|-------|
| P0 (Critical) | 3 |
| P1 (High) | 6 |
| P2 (Medium) | 4 |
| **Total** | **13** |

## TDD Flow

```
Phase 2 (RED)    → Tests written, FAIL
Phase 3 (GREEN)  → Implementation, tests PASS
Phase 4          → Validation & backtest
```
