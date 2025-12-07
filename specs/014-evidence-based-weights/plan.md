# Implementation Plan: Evidence-Based Fusion Weights

**Spec**: spec-014
**Created**: 2025-12-06
**Estimated Effort**: 1-2 days
**Priority**: IMMEDIATE

---

## Overview

This plan implements evidence-based weight adjustments for the Monte Carlo fusion engine, reducing weights for metrics with weak evidence (funding rate, whale signal) and increasing weights for validated metrics.

---

## Architecture Changes

### Current State (spec-009)
```python
ENHANCED_WEIGHTS = {
    "whale": 0.25,      # Grade D evidence
    "utxo": 0.15,
    "funding": 0.15,    # LAGGING indicator
    "oi": 0.10,
    "power_law": 0.10,
    "symbolic": 0.15,
    "fractal": 0.10,
}
```

### Target State (spec-014)
```python
EVIDENCE_BASED_WEIGHTS = {
    "whale": 0.15,      # Reduced (Grade D)
    "utxo": 0.20,       # Increased (Grade A)
    "funding": 0.05,    # Reduced (LAGGING)
    "oi": 0.10,         # Keep
    "power_law": 0.15,  # Increased
    "symbolic": 0.15,   # Keep
    "fractal": 0.10,    # Keep
    "wasserstein": 0.10,# NEW from spec-010
}
```

---

## Implementation Steps

### Step 1: Define New Weight Constants
**File**: `scripts/metrics/monte_carlo_fusion.py`

Add new constants with evidence documentation:
```python
# Legacy weights (spec-009) - preserved for backward compatibility
LEGACY_WEIGHTS = {
    "whale": 0.25,
    "utxo": 0.15,
    "funding": 0.15,
    "oi": 0.10,
    "power_law": 0.10,
    "symbolic": 0.15,
    "fractal": 0.10,
}

# Evidence-based weights (spec-014)
# Sources: Contadino Galattico analysis (42 sources, 7 peer-reviewed)
EVIDENCE_BASED_WEIGHTS = {
    "whale": 0.15,      # Reduced: Grade D evidence (zero empirical validation)
    "utxo": 0.20,       # Increased: Entity-adjusted, Grade A evidence
    "funding": 0.05,    # Reduced: LAGGING indicator (Coinbase research)
    "oi": 0.10,         # Maintained: Grade B evidence
    "power_law": 0.15,  # Increased: Regime detection value
    "symbolic": 0.15,   # Maintained: Needs validation (spec-015)
    "fractal": 0.10,    # Maintained: Needs validation (spec-015)
    "wasserstein": 0.10,# NEW: Grade A evidence (Horvath 2021)
}
```

### Step 2: Add Environment Configuration
**File**: `.env.example`

```bash
# Fusion Weight Configuration (spec-014)
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

### Step 3: Add Weight Validation
**File**: `scripts/metrics/monte_carlo_fusion.py`

```python
def validate_weights(weights: dict[str, float]) -> bool:
    """Validate that weights sum to 1.0 and are all positive."""
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Weights must sum to 1.0, got {total}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("All weights must be non-negative")
    return True

def load_weights_from_env() -> dict[str, float]:
    """Load weights from environment, falling back to defaults."""
    if os.getenv("FUSION_USE_LEGACY_WEIGHTS", "false").lower() == "true":
        return LEGACY_WEIGHTS.copy()

    weights = {
        "whale": float(os.getenv("FUSION_WHALE_WEIGHT", "0.15")),
        "utxo": float(os.getenv("FUSION_UTXO_WEIGHT", "0.20")),
        "funding": float(os.getenv("FUSION_FUNDING_WEIGHT", "0.05")),
        "oi": float(os.getenv("FUSION_OI_WEIGHT", "0.10")),
        "power_law": float(os.getenv("FUSION_POWER_LAW_WEIGHT", "0.15")),
        "symbolic": float(os.getenv("FUSION_SYMBOLIC_WEIGHT", "0.15")),
        "fractal": float(os.getenv("FUSION_FRACTAL_WEIGHT", "0.10")),
        "wasserstein": float(os.getenv("FUSION_WASSERSTEIN_WEIGHT", "0.10")),
    }
    validate_weights(weights)
    return weights
```

### Step 4: Update Fusion Function
**File**: `scripts/metrics/monte_carlo_fusion.py`

Modify `enhanced_monte_carlo_fusion()` to use new weights:
```python
def enhanced_monte_carlo_fusion(
    components: dict[str, float | None],
    weights: dict[str, float] | None = None,
    n_simulations: int = 10000
) -> EnhancedFusionResult:
    """
    Monte Carlo fusion with evidence-based weights.

    Args:
        components: Dict of component votes (-1 to +1, None if unavailable)
        weights: Optional custom weights, defaults to evidence-based
        n_simulations: Number of Monte Carlo iterations
    """
    if weights is None:
        weights = load_weights_from_env()

    validate_weights(weights)
    # ... rest of implementation
```

### Step 5: Add Tests
**File**: `tests/test_monte_carlo_fusion.py`

```python
def test_evidence_based_weights_sum_to_one():
    """Evidence-based weights must sum to exactly 1.0."""
    total = sum(EVIDENCE_BASED_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001

def test_legacy_weights_sum_to_one():
    """Legacy weights must sum to exactly 1.0."""
    total = sum(LEGACY_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001

def test_weight_validation_rejects_invalid_sum():
    """Validation should reject weights that don't sum to 1.0."""
    invalid_weights = {"a": 0.5, "b": 0.3}  # Sum = 0.8
    with pytest.raises(ValueError):
        validate_weights(invalid_weights)

def test_fusion_uses_evidence_based_by_default():
    """Fusion should use evidence-based weights by default."""
    # ... test implementation
```

### Step 6: Update Documentation
**File**: `CLAUDE.md`

Add note about evidence-based weights in the appropriate section.

---

## Testing Strategy

### Unit Tests
- Weight sum validation
- Environment loading
- Backward compatibility with legacy weights

### Integration Tests
- daily_analysis.py with new weights
- API endpoints return correct weight info

### Backtest Validation
- Compare 30-day Sharpe: legacy vs evidence-based
- Document any differences in signal quality

---

## Rollback Plan

If issues arise:
1. Set `FUSION_USE_LEGACY_WEIGHTS=true` in `.env`
2. System reverts to spec-009 weights
3. No code changes required

---

## Files Modified

| File | Changes |
|------|---------|
| `scripts/metrics/monte_carlo_fusion.py` | Add constants, validation, env loading |
| `.env.example` | Add weight configuration |
| `tests/test_monte_carlo_fusion.py` | Add weight validation tests |
| `CLAUDE.md` | Update documentation |

---

## Success Criteria

- [ ] `EVIDENCE_BASED_WEIGHTS` constant defined
- [ ] `LEGACY_WEIGHTS` preserved for backward compatibility
- [ ] Weight sum validation passes
- [ ] All existing tests pass
- [ ] New weight validation tests pass
- [ ] Backtest shows no Sharpe degradation
