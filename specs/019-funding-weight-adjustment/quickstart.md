# Quickstart: spec-019 Derivatives Weight Reduction

## Prerequisites

- Python 3.11+
- `uv` package manager
- Bitcoin Core node (for integration testing)
- Existing test suite passing

## Quick Verification

```bash
# 1. Ensure on feature branch
git checkout 019-funding-weight-adjustment

# 2. Install dependencies
uv sync

# 3. Verify current tests pass
uv run pytest tests/test_monte_carlo_fusion.py -v
```

## Implementation Steps

### Step 1: Update ENHANCED_WEIGHTS

Edit `scripts/metrics/monte_carlo_fusion.py`:

```python
# Line ~203: Replace ENHANCED_WEIGHTS dict
ENHANCED_WEIGHTS = {
    "whale": 0.24,      # +0.03 Primary signal
    "utxo": 0.12,       # unchanged
    "funding": 0.05,    # -0.07 LAGGING
    "oi": 0.05,         # -0.04 LAGGING
    "power_law": 0.09,  # unchanged
    "symbolic": 0.12,   # unchanged
    "fractal": 0.09,    # unchanged
    "wasserstein": 0.08,# +0.04 Grade A
    "cointime": 0.14,   # +0.02 AVIV
    "sopr": 0.02,       # NEW signal
}

# Add assertion after dict definition
_weight_sum = sum(ENHANCED_WEIGHTS.values())
assert abs(_weight_sum - 1.0) < 0.001, f"Weights sum to {_weight_sum}, expected 1.0"
```

### Step 2: Add SOPR Parameters to enhanced_fusion()

```python
def enhanced_fusion(
    whale_vote: Optional[float] = None,
    whale_conf: Optional[float] = None,
    # ... existing params ...
    sopr_vote: Optional[float] = None,  # NEW
    sopr_conf: Optional[float] = None,  # NEW
    # ... rest of params ...
) -> EnhancedFusionResult:
```

### Step 3: Handle SOPR Component

In the components collection section:

```python
if sopr_vote is not None and sopr_conf is not None:
    components["sopr"] = (sopr_vote, sopr_conf)
```

### Step 4: Update EnhancedFusionResult

Add field to dataclass:

```python
@dataclass
class EnhancedFusionResult:
    # ... existing fields ...
    sopr_weight: float = 0.0  # NEW
```

And in result construction:

```python
sopr_weight=normalized_weights.get("sopr", 0.0),
```

### Step 5: Update Tests

Edit `tests/test_monte_carlo_fusion.py`:

```python
def test_weights_sum_to_one():
    from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS
    assert abs(sum(ENHANCED_WEIGHTS.values()) - 1.0) < 0.001

def test_fusion_with_sopr():
    result = enhanced_fusion(
        whale_vote=0.8, whale_conf=0.9,
        sopr_vote=0.6, sopr_conf=0.85,
    )
    assert result.sopr_weight > 0
    assert 0 <= result.sopr_weight <= 1
```

## Verification Commands

```bash
# Run all fusion tests
uv run pytest tests/test_monte_carlo_fusion.py -v

# Verify weights sum
python -c "from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS; print(f'Sum: {sum(ENHANCED_WEIGHTS.values())}')"

# Check for import errors
python -c "from scripts.metrics.monte_carlo_fusion import enhanced_fusion, EnhancedFusionResult"

# Full test suite
uv run pytest tests/ -v --tb=short
```

## Troubleshooting

### Import Error: sopr module not found

Ensure you're on `main` or a branch that includes spec-016:
```bash
git log --oneline | grep -i sopr
```

### Weights don't sum to 1.0

Check for typos in weight values. Use:
```python
from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS
for k, v in ENHANCED_WEIGHTS.items():
    print(f"{k}: {v}")
print(f"Sum: {sum(ENHANCED_WEIGHTS.values())}")
```

### Test failures after weight change

Expected - update test assertions to match new weights:
```python
# OLD
assert result.whale_weight == pytest.approx(0.21 / total, rel=0.01)
# NEW
assert result.whale_weight == pytest.approx(0.24 / total, rel=0.01)
```
