# Quickstart: Wasserstein Distance Calculator

**Feature**: spec-010 | **Date**: 2025-12-04

## Overview

The Wasserstein Distance Calculator detects distribution shifts in UTXO value patterns using Earth Mover's Distance (EMD). It integrates as the 8th component in the Enhanced Monte Carlo Fusion.

## Installation

No additional dependencies required (pure Python).

## Basic Usage

### Single Distance Calculation

```python
from scripts.metrics.wasserstein import wasserstein_1d, WassersteinResult

# Compare two distributions
values_window_1 = [1000, 2000, 3000, 4000, 5000]  # Earlier window
values_window_2 = [1500, 2500, 3500, 4500, 5500]  # Later window

# Calculate Wasserstein distance
result = wasserstein_1d(values_window_1, values_window_2)
print(f"Distance: {result.distance:.4f}")
print(f"Normalized: {result.distance_normalized:.4f}")
print(f"Shift Direction: {result.shift_direction}")
```

### Rolling Window Analysis

```python
from scripts.metrics.wasserstein import rolling_wasserstein

# Full UTXO value series from daily_analysis
utxo_values = [...]  # List of UTXO values with timestamps

# Compute rolling Wasserstein
rolling_result = rolling_wasserstein(
    values=utxo_values,
    window_size=144,   # ~24 hours of blocks
    step_size=6,       # ~1 hour steps
    threshold=0.10     # Shift detection threshold
)

print(f"Regime Status: {rolling_result.regime_status}")
print(f"Wasserstein Vote: {rolling_result.wasserstein_vote:+.3f}")
print(f"Mean Distance: {rolling_result.mean_distance:.4f}")
print(f"Sustained Shift: {rolling_result.sustained_shift_detected}")
```

### Integration with Enhanced Fusion

```python
from scripts.metrics.monte_carlo_fusion import enhanced_fusion

# Run fusion with all 8 components including Wasserstein
result = enhanced_fusion(
    whale_vote=0.6,
    whale_conf=0.9,
    utxo_vote=0.4,
    utxo_conf=0.85,
    funding_vote=0.2,
    oi_vote=-0.1,
    power_law_vote=0.5,
    symbolic_vote=0.3,
    fractal_vote=0.1,
    wasserstein_vote=0.35,  # NEW: from rolling_wasserstein
    n_samples=1000
)

print(f"Action: {result.action}")
print(f"Confidence: {result.action_confidence:.2%}")
print(f"Signal Mean: {result.signal_mean:+.3f}")
print(f"Components Used: {result.components_used}")
```

## API Usage

### Get Latest Wasserstein Metrics

```bash
curl http://localhost:8000/api/metrics/wasserstein
```

Response:
```json
{
  "distance": 0.125,
  "distance_normalized": 0.087,
  "shift_direction": "CONCENTRATION",
  "regime_status": "TRANSITIONING",
  "wasserstein_vote": 0.35,
  "is_valid": true,
  "timestamp": "2025-12-04T15:30:00Z"
}
```

### Get Historical Data

```bash
curl "http://localhost:8000/api/metrics/wasserstein/history?hours=24&limit=50"
```

### Get Regime Status

```bash
curl http://localhost:8000/api/metrics/wasserstein/regime
```

## Interpretation Guide

### Wasserstein Distance

| Distance | Meaning |
|----------|---------|
| W < 0.05 | Stable distribution, no significant change |
| 0.05 ≤ W < 0.10 | Minor shift, monitor closely |
| 0.10 ≤ W < 0.20 | Significant shift, regime change likely |
| W ≥ 0.20 | Major shift, regime transition confirmed |

### Shift Direction

| Direction | Meaning | Trading Implication |
|-----------|---------|---------------------|
| CONCENTRATION | More large values, fewer small | Whale accumulation (bullish) |
| DISPERSION | More small values, fewer large | Retail entry (neutral/bearish) |
| NONE | No clear direction | Market stable |

### Regime Status

| Status | Definition | Action |
|--------|------------|--------|
| STABLE | W < threshold for extended period | Current strategy valid |
| TRANSITIONING | 1-2 consecutive high-W windows | Monitor for confirmation |
| SHIFTED | 3+ consecutive high-W windows | Adjust strategy |

### Vote Interpretation

| Vote | Meaning |
|------|---------|
| +0.6 to +1.0 | Strong concentration signal (bullish) |
| +0.2 to +0.5 | Moderate concentration (slightly bullish) |
| -0.2 to +0.2 | Neutral/no significant shift |
| -0.5 to -0.2 | Moderate dispersion (slightly bearish) |
| -1.0 to -0.6 | Strong dispersion signal (bearish) |

## Configuration

Environment variables (`.env`):

```bash
# Enable/disable Wasserstein calculation
WASSERSTEIN_ENABLED=true

# Window configuration
WASSERSTEIN_WINDOW_SIZE=144    # blocks (~24h)
WASSERSTEIN_STEP_SIZE=6        # blocks (~1h)

# Detection thresholds
WASSERSTEIN_SHIFT_THRESHOLD=0.10
WASSERSTEIN_MIN_SAMPLES=50
WASSERSTEIN_SUSTAINED_COUNT=3

# Fusion weight
WASSERSTEIN_WEIGHT=0.08
```

## Performance

| Operation | Time | Memory |
|-----------|------|--------|
| Single W calculation (1000 samples) | <1ms | O(n) |
| Rolling analysis (24h, 1h steps) | <50ms | O(n) |
| Full daily_analysis with Wasserstein | +10ms | +1MB |

## Troubleshooting

### "is_valid: false"

Insufficient samples in one or both windows. Ensure:
- At least 50 UTXO values per window
- Data source (electrs/mempool) is returning transactions

### High variance in rolling distances

Normal during volatile periods. Check:
- Recent whale movements
- Market events (listings, news)
- CoinJoin activity (may cause false positives)

### Zero distance when expecting shift

Possible causes:
- Identical distributions (unlikely in practice)
- Data source returning cached values
- Window size too large for the timeframe

## Next Steps

1. Run `daily_analysis.py` to generate initial metrics
2. Check `/api/metrics/wasserstein` endpoint
3. Monitor regime changes over 24-48 hours
4. Adjust thresholds based on backtesting results (spec-012)
