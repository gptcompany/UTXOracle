# Quickstart: PRO Risk Metric (spec-033)

## Overview

PRO Risk Metric is a composite 0-1 scale indicator that aggregates 6 on-chain signals to provide a single-glance market cycle position.

## Prerequisites

- Python 3.11+
- UTXOracle with specs 007, 016, 017, 018 complete
- DuckDB database with historical metrics (4+ years recommended)

## Installation

```bash
# Already part of UTXOracle - no additional installation needed
# Dependencies are in existing pyproject.toml
```

## Quick Usage

### CLI

```bash
# Get today's PRO Risk
python -m scripts.metrics.pro_risk

# Get for specific date
python -m scripts.metrics.pro_risk -d 2025/12/25

# Output JSON format
python -m scripts.metrics.pro_risk --json
```

### Python API

```python
from scripts.metrics.pro_risk import calculate_pro_risk, ProRiskResult

# Calculate for today
result: ProRiskResult = calculate_pro_risk()
print(f"PRO Risk: {result.value:.2f} ({result.zone})")
print(f"Confidence: {result.confidence:.0%}")

# Individual components
for name, score in result.components.items():
    print(f"  {name}: {score:.2f}")
```

### REST API

```bash
# Get current PRO Risk
curl http://localhost:8000/api/risk/pro

# Get for specific date
curl "http://localhost:8000/api/risk/pro?date=2025-12-25"

# Get historical range
curl "http://localhost:8000/api/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25"

# Get zone definitions
curl http://localhost:8000/api/risk/pro/zones
```

## Zone Interpretation

| Zone | Value Range | Action |
|------|-------------|--------|
| extreme_fear | 0.00 - 0.20 | Strong buy signal |
| fear | 0.20 - 0.40 | Accumulation zone |
| neutral | 0.40 - 0.60 | Hold / DCA |
| greed | 0.60 - 0.80 | Caution zone |
| extreme_greed | 0.80 - 1.00 | Distribution zone |

## Example Output

```json
{
  "date": "2025-12-25",
  "value": 0.62,
  "zone": "greed",
  "components": [
    {"metric": "mvrv_z", "raw_value": 2.1, "normalized": 0.71, "weight": 0.30, "weighted": 0.213},
    {"metric": "sopr", "raw_value": 1.02, "normalized": 0.55, "weight": 0.20, "weighted": 0.110},
    {"metric": "nupl", "raw_value": 0.45, "normalized": 0.60, "weight": 0.20, "weighted": 0.120},
    {"metric": "reserve_risk", "raw_value": 0.008, "normalized": 0.68, "weight": 0.15, "weighted": 0.102},
    {"metric": "puell", "raw_value": 1.3, "normalized": 0.58, "weight": 0.10, "weighted": 0.058},
    {"metric": "hodl_waves", "raw_value": 0.42, "normalized": 0.45, "weight": 0.05, "weighted": 0.023}
  ],
  "confidence": 0.95,
  "historical_context": {
    "percentile_30d": 0.78,
    "percentile_1y": 0.65
  }
}
```

## Configuration

Environment variables:

```bash
# Minimum history for stable percentiles (default: 1460 days = 4 years)
PRO_RISK_MIN_HISTORY_DAYS=1460

# Winsorization percentile (default: 0.02 = 2%)
PRO_RISK_WINSORIZE_PCT=0.02

# DuckDB database path
UTXORACLE_DB_PATH=./data/utxoracle.duckdb
```

## Testing

```bash
# Run unit tests
uv run pytest tests/test_pro_risk.py -v

# Run with coverage
uv run pytest tests/test_pro_risk.py --cov=scripts.metrics.pro_risk
```

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics/pro_risk.py` | Core calculation module |
| `api/routes/risk.py` | API endpoint |
| `tests/test_pro_risk.py` | Unit tests |
| `historical_data/risk_percentiles.json` | Pre-computed percentile cache |
