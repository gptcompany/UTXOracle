# Quickstart: Advanced On-Chain Analytics

**Feature**: 009-advanced-onchain-analytics
**Status**: Spec Complete, Implementation Pending
**Estimated Implementation**: ~2 hours

## Overview

This spec adds three advanced statistical modules to enhance UTXOracle's signal fusion:

| Module | Purpose | Accuracy Gain |
|--------|---------|---------------|
| **Symbolic Dynamics** | Temporal pattern complexity | +25% |
| **Power Law Detector** | Critical regime detection | +5% |
| **Fractal Dimension** | Structural analysis | +10% |

Combined with existing signals (whale, utxo, funding, oi), the enhanced fusion targets **+40% accuracy improvement**.

## Prerequisites

Before implementation, ensure:

```bash
# 1. Verify spec-007 is complete (Monte Carlo Fusion)
curl http://localhost:8001/api/metrics/latest | jq '.monte_carlo'

# 2. Verify metrics module exists
ls -la /media/sam/1TB/UTXOracle/scripts/metrics/

# 3. Verify tests pass
uv run pytest tests/test_onchain_metrics.py -v
```

## Quick Implementation

### Option A: Use TDD Workflow (Recommended)

```bash
# 1. Generate tasks
cd /media/sam/1TB/UTXOracle
# Run /speckit.tasks in Claude Code

# 2. Implement with TDD
uv run pytest tests/test_advanced_metrics.py -v  # RED
# Implement module
uv run pytest tests/test_advanced_metrics.py -v  # GREEN
```

### Option B: Direct Implementation

If you want to implement without SpecKit tasks:

```bash
# 1. Create symbolic_dynamics.py
cat > scripts/metrics/symbolic_dynamics.py << 'EOF'
"""Symbolic Dynamics Processor - Permutation Entropy Analysis"""
from dataclasses import dataclass, field
from datetime import datetime
from math import factorial, log

@dataclass
class SymbolicDynamicsResult:
    permutation_entropy: float
    statistical_complexity: float
    order: int
    pattern_counts: dict
    dominant_pattern: str
    complexity_class: str
    pattern_type: str
    symbolic_vote: float
    series_length: int
    is_valid: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

def permutation_entropy(series: list[float], order: int = 5, delay: int = 1) -> float:
    """Compute normalized permutation entropy."""
    n = len(series)
    min_length = order + (order - 1) * delay
    if n < min_length:
        return 0.0

    patterns = {}
    for i in range(n - (order - 1) * delay):
        window = [series[i + j * delay] for j in range(order)]
        pattern = tuple(sorted(range(order), key=lambda k: window[k]))
        patterns[pattern] = patterns.get(pattern, 0) + 1

    total = sum(patterns.values())
    probs = [c / total for c in patterns.values()]
    H = -sum(p * log(p) for p in probs if p > 0)
    H_max = log(factorial(order))
    return H / H_max if H_max > 0 else 0

def analyze(series: list[float], order: int = 5) -> SymbolicDynamicsResult:
    """Full symbolic dynamics analysis."""
    H = permutation_entropy(series, order)
    # Classify based on entropy
    if H < 0.4:
        pattern_type = "ACCUMULATION_TREND"
        vote = 0.8 * (1 - H / 0.4)
        complexity_class = "LOW"
    elif H > 0.7:
        pattern_type = "CHAOTIC_TRANSITION"
        vote = 0.0
        complexity_class = "HIGH"
    else:
        pattern_type = "TRANSITIONAL"
        vote = 0.0
        complexity_class = "MEDIUM"

    return SymbolicDynamicsResult(
        permutation_entropy=H,
        statistical_complexity=0.0,  # Simplified
        order=order,
        pattern_counts={},
        dominant_pattern="",
        complexity_class=complexity_class,
        pattern_type=pattern_type,
        symbolic_vote=vote,
        series_length=len(series)
    )
EOF

# 2. Run basic test
python -c "
from scripts.metrics.symbolic_dynamics import permutation_entropy, analyze
# Monotonic series = low entropy
mono = list(range(100))
H_mono = permutation_entropy(mono)
print(f'Monotonic entropy: {H_mono:.3f} (expect ~0)')

# Random shuffle = high entropy
import random
rand = list(range(100))
random.shuffle(rand)
H_rand = permutation_entropy(rand)
print(f'Random entropy: {H_rand:.3f} (expect ~1)')

# Full analysis
result = analyze(mono)
print(f'Pattern type: {result.pattern_type}')
print(f'Vote: {result.symbolic_vote:.2f}')
"
```

## Files to Create/Modify

| File | Action | LOC |
|------|--------|-----|
| `scripts/metrics/symbolic_dynamics.py` | CREATE | ~100 |
| `scripts/metrics/power_law.py` | CREATE | ~120 |
| `scripts/metrics/fractal_dimension.py` | CREATE | ~80 |
| `scripts/metrics/monte_carlo_fusion.py` | MODIFY | ~60 |
| `scripts/models/metrics_models.py` | MODIFY | ~50 |
| `api/main.py` | MODIFY | ~30 |
| `tests/test_advanced_metrics.py` | CREATE | ~200 |

**Total**: ~640 LOC (including tests)

## API Usage (After Implementation)

```bash
# Get advanced metrics
curl http://localhost:8001/api/metrics/advanced | jq

# Example response:
{
  "timestamp": "2025-12-04T12:00:00Z",
  "power_law": {
    "tau": 1.85,
    "regime": "NEUTRAL",
    "vote": 0.0,
    "is_valid": true
  },
  "symbolic_dynamics": {
    "entropy": 0.35,
    "pattern_type": "ACCUMULATION_TREND",
    "vote": 0.65,
    "complexity_class": "LOW"
  },
  "fractal_dimension": {
    "dimension": 0.72,
    "structure": "WHALE_DOMINATED",
    "vote": 0.35,
    "is_valid": true
  },
  "enhanced_fusion": {
    "signal_mean": 0.58,
    "action": "BUY",
    "action_confidence": 0.82,
    "components_available": 7
  }
}
```

## Validation

After implementation, validate with:

```bash
# 1. Unit tests
uv run pytest tests/test_advanced_metrics.py -v --cov=scripts/metrics

# 2. Performance benchmark
python -c "
import time
from scripts.metrics.symbolic_dynamics import analyze
from scripts.metrics.power_law import fit as power_law_fit
from scripts.metrics.fractal_dimension import analyze as fractal_analyze

# Generate test data
import random
data = [random.random() * 1000 for _ in range(1000)]

start = time.time()
for _ in range(100):
    analyze(data)
    power_law_fit(data)
    fractal_analyze(data)
elapsed = (time.time() - start) / 100 * 1000
print(f'Average time: {elapsed:.1f}ms (target: <100ms)')
"

# 3. Integration test
curl http://localhost:8001/api/metrics/advanced
```

## Troubleshooting

### "Module not found" error
```bash
# Add scripts to PYTHONPATH
export PYTHONPATH=/media/sam/1TB/UTXOracle:$PYTHONPATH
```

### Performance >100ms
```bash
# Check if numpy is available for acceleration
python -c "import numpy; print('numpy available')" 2>/dev/null || echo "Consider: uv pip install numpy"
```

### Power law fit fails
- Check sample size (need ≥100 values)
- Check KS p-value (need >0.05)
- System will gracefully return `is_valid=False`

## References

- [spec.md](./spec.md) - Full specification
- [research.md](./research.md) - Academic foundations
- [data-model.md](./data-model.md) - Data structures
- [contracts/advanced_metrics_api.py](./contracts/advanced_metrics_api.py) - API contracts
