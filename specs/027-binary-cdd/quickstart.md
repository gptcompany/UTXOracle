# Quickstart: Binary CDD Indicator

**Spec**: 027-binary-cdd | **Effort**: ~2 hours

## Overview

Binary CDD is a statistical significance flag that transforms noisy Coin Days Destroyed (CDD) data into actionable signals. It calculates a z-score against a rolling baseline and outputs:
- `binary_cdd=0`: Normal activity (noise)
- `binary_cdd=1`: Significant long-term holder movement event

## Prerequisites

- UTXOracle API running (`api/main.py`)
- DuckDB database with `utxo_lifecycle_full` table populated (spec-017/021)
- At least 30 days of historical UTXO data (365 days recommended)

## API Usage

### Basic Request

```bash
curl http://localhost:8000/api/metrics/binary-cdd
```

### With Custom Threshold

```bash
# More sensitive (1.5 sigma)
curl "http://localhost:8000/api/metrics/binary-cdd?threshold=1.5"

# More conservative (3 sigma - extreme events only)
curl "http://localhost:8000/api/metrics/binary-cdd?threshold=3.0"
```

### With Custom Window

```bash
# 90-day baseline (more reactive)
curl "http://localhost:8000/api/metrics/binary-cdd?window=90"

# 730-day baseline (more stable)
curl "http://localhost:8000/api/metrics/binary-cdd?window=730"
```

## Response Interpretation

```json
{
  "cdd_today": 12543.75,      // Today's CDD value
  "cdd_mean": 8234.21,        // 365-day average
  "cdd_std": 2156.73,         // Standard deviation
  "cdd_zscore": 1.998,        // How many std devs above mean
  "cdd_percentile": 97.28,    // Percentile rank
  "binary_cdd": 0,            // THE SIGNAL (0 or 1)
  "threshold_used": 2.0,      // Your threshold
  "window_days": 365,
  "data_points": 365,
  "insufficient_data": false,
  "block_height": 875000,
  "timestamp": "2025-12-18T10:30:00Z"
}
```

### Signal Logic

| Z-Score | Percentile | Binary CDD | Meaning |
|---------|------------|------------|---------|
| < 2σ | < 97.5% | 0 | Normal LTH activity |
| >= 2σ | >= 97.5% | 1 | Significant event |
| >= 3σ | >= 99.9% | 1 | Extreme event (rare) |

## Integration Examples

### Python

```python
import requests

response = requests.get(
    "http://localhost:8000/api/metrics/binary-cdd",
    params={"threshold": 2.0, "window": 365}
)
data = response.json()

if data["binary_cdd"] == 1:
    print(f"ALERT: Significant LTH movement! Z-score: {data['cdd_zscore']:.2f}")
else:
    print(f"Normal activity. Z-score: {data['cdd_zscore']:.2f}")
```

### Trading Signal

```python
# Combine with other metrics for confluence
binary_cdd = data["binary_cdd"]
zscore = data["cdd_zscore"]

if binary_cdd == 1 and zscore >= 3.0:
    signal = "STRONG_DISTRIBUTION"  # LTH selling hard
elif binary_cdd == 1:
    signal = "DISTRIBUTION"  # LTH distribution event
elif zscore < -2.0:
    signal = "ACCUMULATION"  # Unusually low CDD
else:
    signal = "NEUTRAL"
```

## Common Issues

### insufficient_data: true

**Cause**: Less than 30 days of UTXO lifecycle data available.

**Solution**: Run UTXO lifecycle sync to populate historical data.

### cdd_zscore: null

**Cause**: Zero standard deviation (all daily CDD values identical, unlikely).

**Solution**: Check database integrity; ensure varied transaction activity.

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics/binary_cdd.py` | Calculator module |
| `scripts/models/metrics_models.py` | BinaryCDDResult dataclass |
| `api/main.py` | API endpoint |
| `tests/test_binary_cdd.py` | TDD tests |
