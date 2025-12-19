# UTXOracle Validation Framework

Professional validation of metric implementations against CheckOnChain.com reference.

## Quick Start

### CLI (Recommended)

```bash
# Update baselines from CheckOnChain
python -m validation --update-baselines

# Run full validation suite
python -m validation

# Numerical validation only
python -m validation --numerical

# Visual validation workflow
python -m validation --visual

# Single metric
python -m validation --metric mvrv
```

### Python API

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

### Visual Validation (Requires Playwright MCP)

```python
from validation.framework.visual_validator import VisualValidator

validator = VisualValidator()

# Get workflow instructions for screenshot comparison
workflow = validator.compare_metric("mvrv")
print(workflow)

# After capturing screenshots and comparing visually:
result = validator.compare_screenshots(
    "mvrv",
    trend_match=True,
    zone_match=True,
    value_alignment=95.0,
    notes="Charts aligned well"
)
```

## Directory Structure

```
validation/
├── __init__.py            # Package init
├── __main__.py            # CLI entry point
├── README.md              # This file
├── framework/
│   ├── __init__.py
│   ├── config.py          # URL mappings, tolerances
│   ├── validator.py       # Core validation logic
│   ├── checkonchain_fetcher.py  # Reference data fetcher
│   ├── comparison_engine.py     # Compare and report
│   └── visual_validator.py      # Screenshot comparison
├── baselines/             # Reference data snapshots
│   ├── mvrv_baseline.json
│   ├── nupl_baseline.json
│   ├── sopr_baseline.json
│   ├── cdd_baseline.json
│   ├── hash_ribbons_baseline.json
│   └── cost_basis_baseline.json
├── reports/               # Validation reports
│   └── YYYY-MM-DD_validation.md
├── screenshots/           # Visual comparison
│   ├── ours/
│   └── reference/
├── cache/                 # Fetcher cache (1-hour TTL)
└── tests/                 # Test suite
    ├── conftest.py
    ├── test_validator.py
    ├── test_fetcher.py
    └── test_comparison.py
```

## Metrics Covered

| Metric | API Endpoint | CheckOnChain Page |
|--------|--------------|-------------------|
| MVRV-Z Score | `/api/metrics/mvrv` | btconchain/unrealised/mvrv_all |
| NUPL | `/api/metrics/nupl` | btconchain/unrealised/nupl |
| SOPR | `/api/metrics/pl-ratio` | btconchain/realised/sopr |
| CDD | `/api/metrics/binary-cdd` | btconchain/lifespan/cdd |
| Hash Ribbons | `/api/metrics/hash-ribbons` | btconchain/mining/hashribbons |
| Cost Basis | `/api/metrics/cost-basis` | btconchain/pricing/yearlycostbasis |

## Tolerance Levels

| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| MVRV-Z | ±2% | High precision expected |
| NUPL | ±2% | High precision expected |
| SOPR | ±1% | Very sensitive metric |
| STH/LTH SOPR | ±2% | Cohort-specific variance |
| CDD | ±5% | Aggregation timing differences |
| Binary CDD | 0% | Boolean - exact match |
| Cost Basis | ±2% | Price-based, stable |
| Hash Ribbons | ±3% | Mining metrics natural variance |

## Validation Status Meanings

- ✅ **PASS**: Deviation within tolerance
- ⚠️ **WARN**: Deviation within 2x tolerance (review recommended)
- ❌ **FAIL**: Deviation exceeds 2x tolerance (investigation required)
- 🔴 **ERROR**: Validation could not complete

## Running Tests

```bash
# Run all validation tests
uv run pytest validation/tests/ -v

# Run with coverage
uv run pytest validation/tests/ --cov=validation --cov-report=term-missing
```

## CI/CD

GitHub Action runs nightly at 2 AM UTC:

- `.github/workflows/validation.yml`
- Manual trigger available with metric selection
- Creates issues on validation failures
- Uploads reports as artifacts

## Extending

To add a new metric:

1. Add URL mapping to `framework/config.py` URL_MAPPING
2. Add tolerance to `framework/config.py` TOLERANCES
3. Add endpoint to `checkonchain_fetcher.py` ENDPOINTS
4. Implement `validate_<metric>()` method in validator
5. Add tests in `tests/test_validator.py`

## Reference

- **Primary Source**: https://charts.checkonchain.com
- **Technology**: Plotly.js (same as our frontend)
- **Rate Limit**: 1 request per 2 seconds (respectful)
- **Cache TTL**: 1 hour
