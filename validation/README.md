# UTXOracle Validation Framework

Professional validation of metric implementations against CheckOnChain.com reference.

## Quick Start

### 1. Numerical Validation (No Frontend Required)

```python
from validation.framework.validator import MetricValidator
from validation.framework.checkonchain_fetcher import CheckOnChainFetcher

# Update baselines from CheckOnChain
fetcher = CheckOnChainFetcher()
fetcher.update_all_baselines()

# Run validation
validator = MetricValidator()
results = validator.run_all()

# Generate report
report = validator.generate_report()
print(report)
```

### 2. Visual Validation (Requires Frontend)

After frontend is built:

```python
from validation.framework.comparison_engine import ComparisonEngine

engine = ComparisonEngine()

# Get URLs for screenshot comparison
mvrv_comparison = engine.prepare_visual_comparison("mvrv")
print(f"Our chart: {mvrv_comparison['ours']}")
print(f"Reference: {mvrv_comparison['reference']}")
```

## Directory Structure

```
validation/
├── README.md              # This file
├── framework/
│   ├── __init__.py
│   ├── validator.py       # Core validation logic
│   ├── checkonchain_fetcher.py  # Reference data fetcher
│   └── comparison_engine.py     # Compare and report
├── baselines/             # Reference data snapshots
│   ├── mvrv_baseline.json
│   ├── nupl_baseline.json
│   └── ...
├── reports/               # Validation reports
│   └── YYYY-MM-DD_validation.md
├── screenshots/           # Visual comparison
│   ├── ours/
│   └── reference/
└── cache/                 # Fetcher cache
```

## Metrics Covered

| Metric | API Endpoint | CheckOnChain Page |
|--------|--------------|-------------------|
| MVRV-Z Score | `/api/metrics/mvrv` | btconchain/mvrv |
| NUPL | `/api/metrics/nupl` | btconchain/unrealised_pnl |
| SOPR | `/api/metrics/sopr` | btconchain/sopr |
| CDD | `/api/metrics/binary-cdd` | btconchain/cdd |
| Hash Ribbons | `/api/metrics/hash-ribbons` | btconchain/mining_hashribbons |
| Realized Price | `/api/metrics/cost-basis` | btconchain/realised_price |

## Tolerance Levels

| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| MVRV-Z | ±2% | High precision expected |
| NUPL | ±2% | High precision expected |
| SOPR | ±1% | Very sensitive metric |
| CDD | ±5% | Aggregation timing differences |
| Hash Ribbons | ±3% | API timing differences |

## Validation Status Meanings

- ✅ **PASS**: Deviation within tolerance
- ⚠️ **WARN**: Deviation within 2x tolerance (review recommended)
- ❌ **FAIL**: Deviation exceeds 2x tolerance (investigation required)
- 🔴 **ERROR**: Validation could not complete

## Running Validation

### CLI

```bash
# Update baselines
python -c "from validation.framework.checkonchain_fetcher import CheckOnChainFetcher; CheckOnChainFetcher().update_all_baselines()"

# Run validation
python -c "from validation.framework.validator import MetricValidator; v = MetricValidator(); v.run_all(); print(v.generate_report())"
```

### As Test

```bash
uv run pytest validation/tests/test_validation.py -v
```

## Extending

To add a new metric:

1. Add endpoint to `checkonchain_fetcher.py` ENDPOINTS
2. Add tolerance to `validator.py` TOLERANCES
3. Implement `validate_<metric>()` method in validator
4. Add comparison URL to `comparison_engine.py`

## Reference

- **Primary Source**: https://checkonchain.com
- **Technology**: Plotly.js (same as our frontend)
- **Rate Limit**: 1 request per 2 seconds (respectful)
