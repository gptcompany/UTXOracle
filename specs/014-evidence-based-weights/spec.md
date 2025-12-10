# Feature Specification: Evidence-Based Fusion Weights

**Feature Branch**: `014-evidence-based-weights`
**Created**: 2025-12-06
**Status**: Draft
**Prerequisites**: spec-009 (Advanced On-Chain Analytics) complete
**Priority**: IMMEDIATE (1-2 days)
**Evidence Source**: Contadino Galattico Analysis (42 sources, 7 peer-reviewed)

## Context & Motivation

### Background: Empirical Weight Calibration

Current fusion weights in `enhanced_fusion.py` were assigned based on intuition rather than empirical evidence. Research analysis from 42 sources (7 peer-reviewed, 15 industry research) reveals critical misalignments:

| Component | Current Weight | Evidence Grade | Issue |
|-----------|---------------|----------------|-------|
| **Funding Rate** | 15% | B-LAGGING | Coinbase: "trailing byproduct of momentum" |
| **Whale Signal** | 25% | D | Zero empirical validation found |
| **UTXO/Clustering** | 15% | A | Underweighted vs ML importance |
| **Power Law** | 10% | C | Needs validation, regime detection value |

### Critical Finding: Funding Rate is LAGGING

**Source**: Coinbase Institutional Research
> "Funding rates are linked to long-term price movements, but the magnitude of positive (or negative) rate changes may actually be **trailing byproducts of market momentum rather than leading indicators**."

**Impact**: Funding rate should NOT have 15% weight as a "leading indicator" - it confirms trends, doesn't predict them.

### Critical Finding: Whale Signal Lacks Validation

**Research**: 42 sources analyzed
**Result**: Zero rigorous backtests found for:
- Win rate of whale alerts
- Sharpe ratio of whale-based strategies
- Statistical significance tests

**Verdict**: Grade D evidence - "Observational only, no predictive backtest"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Improved Signal Quality (Priority: P1)

As a Bitcoin trader using UTXOracle fusion signals, I want the **component weights calibrated to empirical evidence**, so my trading signals are based on validated predictive power rather than intuition.

**Why this priority**: Incorrect weights actively degrade signal quality. Lagging indicators weighted as leading cause delayed or wrong signals.

**Acceptance Scenarios**:

1. **Given** enhanced fusion with current weights
   **When** funding rate spikes AFTER price move
   **Then** signal incorrectly suggests "leading" information

2. **Given** enhanced fusion with evidence-based weights
   **When** funding rate spikes AFTER price move
   **Then** its 5% weight minimizes false signal contribution

3. **Given** backtest on 30 days historical data
   **When** comparing current vs evidence-based weights
   **Then** evidence-based shows higher Sharpe ratio (target: +5%)

---

### User Story 2 - Transparent Signal Attribution (Priority: P2)

As a Bitcoin analyst, I want to understand **which components drive fusion signals**, so I can explain and validate trading decisions.

**Acceptance Scenarios**:

1. **Given** enhanced fusion returns component breakdown
   **When** funding_rate contributes high vote
   **Then** I understand it's confirmation, not prediction

2. **Given** API endpoint `/api/metrics/fusion/breakdown`
   **When** queried
   **Then** returns all 8 component weights and votes

---

### Edge Cases

- **What if removing funding weight causes signal degradation?**
  → Run A/B backtest before committing. Keep 5% minimum for confirmation value.

- **What if whale signal removal causes missed moves?**
  → Not removing, reducing. Grade D means "unvalidated", not "useless".

- **What if weights don't sum to 1.0?**
  → Validation MUST enforce sum = 1.0 ± 0.001.

---

## Requirements *(mandatory)*

### Functional Requirements

**Weight Updates**:
- **FR-001**: Funding rate weight MUST be reduced from 15% to 5%
- **FR-002**: Whale signal weight MUST be reduced from 25% to 15%
- **FR-003**: UTXO/Clustering weight MUST be increased from 15% to 20%
- **FR-004**: Power Law weight MUST be increased from 10% to 15%
- **FR-005**: All weights MUST sum to exactly 1.0

**Validation**:
- **FR-006**: Weight configuration MUST be externalized to `.env`
- **FR-007**: System MUST validate weight sum on startup
- **FR-008**: Invalid weight sum MUST prevent system startup with clear error

**Backward Compatibility**:
- **FR-009**: Legacy weight configuration MUST be preserved as `LEGACY_WEIGHTS`
- **FR-010**: Environment variable `USE_LEGACY_WEIGHTS=true` MUST enable old weights

### Non-Functional Requirements

- **NFR-001**: Weight changes MUST NOT affect fusion calculation performance
- **NFR-002**: All tests MUST pass with new default weights
- **NFR-003**: Documentation MUST explain evidence basis for each weight

### Weight Configuration *(mandatory)*

```python
# BEFORE: Intuition-Based (spec-009)
ENHANCED_WEIGHTS = {
    "whale": 0.25,       # Grade D evidence
    "utxo": 0.15,        # Underweighted
    "funding": 0.15,     # LAGGING indicator!
    "oi": 0.10,
    "power_law": 0.10,   # Underweighted
    "symbolic": 0.15,
    "fractal": 0.10,
}

# AFTER: Evidence-Based (spec-014)
EVIDENCE_BASED_WEIGHTS = {
    "whale": 0.15,       # Reduced (Grade D validation)
    "utxo": 0.20,        # Increased (entity-adjusted, Grade A)
    "funding": 0.05,     # REDUCED (LAGGING - Coinbase research)
    "oi": 0.10,          # Keep (Grade B)
    "power_law": 0.15,   # Increased (regime detection)
    "symbolic": 0.15,    # Keep (needs validation)
    "fractal": 0.10,     # Keep (needs validation)
    "wasserstein": 0.10, # NEW (Grade A - Horvath 2021)
}
# Sum = 1.0 ✓
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All weights sum to exactly 1.0
- **SC-002**: Funding rate weight = 0.05 (reduced from 0.15)
- **SC-003**: Whale weight = 0.15 (reduced from 0.25)
- **SC-004**: UTXO weight = 0.20 (increased from 0.15)
- **SC-005**: Backtest on 30 days shows no Sharpe degradation vs legacy
- **SC-006**: All spec-009 tests pass with new weights

### Definition of Done

- [ ] `EVIDENCE_BASED_WEIGHTS` constant defined in `monte_carlo_fusion.py`
- [ ] `LEGACY_WEIGHTS` preserved for backward compatibility
- [ ] `.env` variables for weight configuration added
- [ ] Startup validation for weight sum = 1.0
- [ ] Unit tests for weight validation
- [ ] Integration test: daily_analysis.py with new weights
- [ ] Backtest comparison: legacy vs evidence-based (30 days)
- [ ] Documentation: evidence basis for each weight in docstring

---

## Technical Notes

### Implementation Order (KISS)

1. **Define Constants** (~20 LOC) - New weights with documentation
2. **Environment Config** (~15 LOC) - .env loading with validation
3. **Startup Validation** (~10 LOC) - Sum check with error handling
4. **Tests** (~30 LOC) - Weight validation and integration

### Files to Modify

- `scripts/metrics/monte_carlo_fusion.py` - Weight constants and validation
- `scripts/daily_analysis.py` - Use evidence-based weights by default
- `.env.example` - Add weight configuration variables
- `tests/test_monte_carlo_fusion.py` - Add weight validation tests

### Configuration

```bash
# .env additions
FUSION_USE_LEGACY_WEIGHTS=false
FUSION_WHALE_WEIGHT=0.15
FUSION_UTXO_WEIGHT=0.20
FUSION_FUNDING_WEIGHT=0.05
FUSION_OI_WEIGHT=0.10
FUSION_POWER_LAW_WEIGHT=0.15
FUSION_SYMBOLIC_WEIGHT=0.15
FUSION_FRACTAL_WEIGHT=0.10
FUSION_WASSERSTEIN_WEIGHT=0.10
```

---

## Evidence Summary

### Sources Supporting Changes

| Change | Source | Grade | Quote/Finding |
|--------|--------|-------|---------------|
| Funding 15%→5% | Coinbase Institutional | B | "trailing byproduct of momentum" |
| Whale 25%→15% | Research (42 sources) | D | Zero empirical validation |
| UTXO 15%→20% | Glassnode ML Study | A-B | Top feature importance |
| Power Law 10%→15% | Academic Literature | B | Regime detection value |

### Full Reference

See: `archive/contadino_galattico.md` and `research/on-chain-metrics-empirical-analysis.md`

---

## Out of Scope

- Machine learning weight optimization (future spec)
- Dynamic weight adjustment based on market regime
- Per-component backtest reports (covered in spec-015)
- STH/LTH SOPR integration (covered in spec-016)

---

## References

1. **Coinbase Institutional**: "A Primer on Perpetual Futures" - Funding rate analysis
2. **Glassnode**: "The Predictive Power of Glassnode Data" - ML feature importance
3. **Contadino Galattico**: Internal evidence-based analysis (42 sources)
