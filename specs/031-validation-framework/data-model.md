# Data Model: Validation Framework

## Overview

JSON schemas for baselines, validation results, and reports.

## Baseline Schema

Each metric has a baseline file in `validation/baselines/{metric}_baseline.json`:

```json
{
  "metric": "mvrv",
  "source": "charts.checkonchain.com",
  "captured_at": "2025-12-19T10:30:00Z",
  "current": {
    "mvrv_value": 2.34,
    "mvrv_z_score": 1.45
  },
  "source_url": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
  "visual_url": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html"
}
```

### Metric-Specific Fields

| Metric | Current Fields |
|--------|----------------|
| mvrv | `mvrv_value`, `mvrv_z_score` |
| nupl | `nupl`, `zone` |
| sopr | `sopr`, `sth_sopr`, `lth_sopr` |
| cdd | `cdd_raw`, `cdd_30d_ma` |
| hash_ribbons | `ma_30d`, `ma_60d`, `ribbon_signal` |
| cost_basis | `realized_price`, `sth_cost`, `lth_cost` |

## Validation Result Schema

```python
@dataclass
class ValidationResult:
    metric: str           # "mvrv", "nupl", etc.
    timestamp: datetime   # When validation ran
    our_value: float      # Value from UTXOracle API
    reference_value: float # Value from CheckOnChain
    deviation_pct: float  # Percentage difference
    tolerance_pct: float  # Allowed tolerance
    status: str           # "PASS", "WARN", "FAIL", "ERROR"
    notes: Optional[str]  # Error message or context
```

## Visual Comparison Result Schema

```python
@dataclass
class VisualComparisonResult:
    metric: str                 # "mvrv", "nupl", etc.
    our_screenshot: Path        # Path to our screenshot
    reference_screenshot: Path  # Path to CheckOnChain screenshot
    trend_match: bool           # Do trends align?
    zone_match: bool            # Do zone colors match?
    value_alignment: float      # 0-100% alignment score
    notes: str                  # Observations
    status: str                 # "PASS", "FAIL", "REVIEW"
```

## Report Schema

Generated as Markdown in `validation/reports/YYYY-MM-DD_validation.md`:

```markdown
# Validation Report

**Generated**: 2025-12-19T10:30:00Z

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 5 |
| ⚠️ WARN | 1 |
| ❌ FAIL | 0 |
| 🔴 ERROR | 0 |

## Details

| Metric | Our Value | Reference | Deviation | Tolerance | Status |
|--------|-----------|-----------|-----------|-----------|--------|
| mvrv_z | 1.4500 | 1.4600 | 0.68% | ±2% | ✅ |
| nupl | 0.5200 | 0.5180 | 0.39% | ±2% | ✅ |

## Visual Comparisons

### mvrv ✅
- Trend Match: ✓
- Zone Match: ✓
- Value Alignment: 95.2%
- Notes: Charts visually aligned
```

## Cache Schema

Cached data in `validation/cache/{metric}_cache.json`:

```json
{
  "metric": "mvrv",
  "latest_value": 2.34,
  "timestamp": "2025-12-19T10:30:00Z",
  "raw_data": {
    "data": [
      {
        "x": ["2024-01-01", "2024-01-02", ...],
        "y": [1.2, 1.3, ...],
        "type": "scatter",
        "name": "MVRV Z-Score"
      }
    ]
  }
}
```

## URL Mapping

```python
URL_MAPPING = {
    "mvrv": {
        "ours": "http://localhost:8080/metrics/mvrv.html",
        "reference": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
        "api": "/api/metrics/reserve-risk"
    },
    "nupl": {
        "ours": "http://localhost:8080/metrics/nupl.html",
        "reference": "https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html",
        "api": "/api/metrics/nupl"
    },
    "sopr": {
        "ours": "http://localhost:8080/metrics/sopr.html",
        "reference": "https://charts.checkonchain.com/btconchain/realised/sopr/sopr_light.html",
        "api": "/api/metrics/pl-ratio"
    },
    "cost_basis": {
        "ours": "http://localhost:8080/metrics/cost_basis.html",
        "reference": "https://charts.checkonchain.com/btconchain/realised/realised_price/realised_price_light.html",
        "api": "/api/metrics/cost-basis"
    },
    "hash_ribbons": {
        "ours": "http://localhost:8080/metrics/hash_ribbons.html",
        "reference": "https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html",
        "api": "/api/metrics/hash-ribbons"
    },
    "binary_cdd": {
        "ours": "http://localhost:8080/metrics/binary_cdd.html",
        "reference": "https://charts.checkonchain.com/btconchain/lifespan/cdd_all/cdd_all_light.html",
        "api": "/api/metrics/binary-cdd"
    }
}
```

## Tolerance Configuration

```python
TOLERANCES = {
    "mvrv_z": 2.0,      # ±2%
    "nupl": 2.0,        # ±2%
    "sopr": 1.0,        # ±1%
    "sth_sopr": 2.0,    # ±2%
    "lth_sopr": 2.0,    # ±2%
    "cdd": 5.0,         # ±5%
    "binary_cdd": 0.0,  # Boolean - exact match
    "cost_basis": 2.0,  # ±2%
    "hash_ribbons_30d": 3.0,  # ±3%
    "hash_ribbons_60d": 3.0,  # ±3%
}
```
