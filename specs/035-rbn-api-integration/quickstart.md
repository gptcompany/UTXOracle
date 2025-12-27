# Quickstart: ResearchBitcoin.net API Integration

**Phase 1 Design Output** | **Date**: 2025-12-26

## Prerequisites

1. **RBN API Token**: Register at https://api.researchbitcoin.net/token (free)
2. **UTXOracle running**: Metrics database populated with historical data
3. **Python 3.10+** with `httpx` installed

## Configuration

Add to your `.env` file:

```bash
# ResearchBitcoin.net API
RBN_API_TOKEN=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RBN_TIER=0  # 0=free (100/week), 1=standard (300/week), 2=premium (10k/week)
RBN_CACHE_TTL_HOURS=24
```

## Quick Usage

### CLI: Validate a Single Metric

```bash
# Validate MVRV Z-Score for last 30 days
python -m scripts.integrations.rbn_validator mvrv_z

# Validate SOPR with custom date range
python -m scripts.integrations.rbn_validator sopr \
    --start-date 2024-06-01 \
    --end-date 2024-12-31

# Generate full validation report
python -m scripts.integrations.rbn_validator --report
```

### API: Validation Endpoints

```bash
# Check quota status
curl http://localhost:8000/api/v1/validation/rbn/quota

# Validate single metric
curl "http://localhost:8000/api/v1/validation/rbn/mvrv_z?start_date=2024-01-01"

# Generate report for multiple metrics
curl "http://localhost:8000/api/v1/validation/rbn/report?metrics=mvrv,sopr,nupl"
```

### Python: Direct Usage

```python
from scripts.integrations.rbn_fetcher import RBNFetcher
from scripts.integrations.rbn_validator import ValidationService
from datetime import date

# Initialize fetcher
fetcher = RBNFetcher()

# Fetch single metric
data = await fetcher.fetch_metric(
    metric_id="mvrv_z",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)

# Run validation
validator = ValidationService(fetcher)
report = await validator.validate_metric(
    metric_id="mvrv_z",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    tolerance_pct=1.0
)

print(f"Match rate: {report.match_rate_pct:.1f}%")
print(f"Avg deviation: {report.avg_deviation_pct:.2f}%")
```

## Available Metrics

### Priority 1: Validation (UTXOracle equivalents)

| Metric ID | Name | UTXOracle Spec |
|-----------|------|----------------|
| `mvrv` | MVRV Ratio | spec-007 |
| `mvrv_z` | MVRV Z-Score | spec-007 |
| `sopr` | SOPR | spec-016 |
| `nupl` | Net Unrealized P/L | spec-007 |
| `realized_cap` | Realized Cap | spec-007 |
| `price_power_law` | Power Law Model | spec-034 |
| `liveliness` | Liveliness | spec-018 |

### Priority 2: Gap-Filling

| Metric ID | Name | Tier |
|-----------|------|------|
| `thermo_cap` | Thermocap | 0 (free) |
| `stocktoflow_nominal` | Stock-to-Flow | 0 (free) |
| `active_mvrv` | Active MVRV | 0 (free) |

## Rate Limits

| Tier | Weekly Queries | History |
|------|----------------|---------|
| 0 (Free) | 100 | 1 year |
| 1 (Standard) | 300 | Full |
| 2 (Premium) | 10,000 | Full |

Quota resets weekly. Check status anytime:

```bash
curl http://localhost:8000/api/v1/validation/rbn/quota
```

## Caching

- Responses cached for 24 hours in `cache/rbn/`
- Cache uses Parquet format for efficient storage
- Clear cache with:
  ```bash
  curl -X DELETE "http://localhost:8000/api/v1/validation/rbn/cache?metric_id=mvrv_z"
  ```

## Interpretation Guide

| Status | Deviation | Meaning |
|--------|-----------|---------|
| `match` | <1% | Calculations agree |
| `minor_diff` | 1-5% | Small methodology difference |
| `major_diff` | >5% | Investigate discrepancy |
| `missing` | N/A | Data unavailable on one side |

**Target**: >95% match rate for Priority 1 metrics.

## Troubleshooting

### Error: "RBN API quota exceeded"
Wait for weekly reset or upgrade tier.

### Error: "Invalid token"
Verify token at https://api.researchbitcoin.net/info_user

### Large deviations on specific dates
May indicate:
- Different block height cutoffs
- Exchange price source differences
- Calculation methodology variations

Document deviations in `reports/validation/` for reference.

## Next Steps

1. Run initial validation for all Priority 1 metrics
2. Document any systematic deviations
3. Consider methodology adjustments if match rate <95%
4. Set up weekly cron job for automated validation
