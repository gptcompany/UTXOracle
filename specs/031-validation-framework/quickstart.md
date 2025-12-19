# Quickstart: Validation Framework

## Prerequisites

1. **FastAPI backend running**:
   ```bash
   uv run uvicorn api.main:app --reload --port 8000
   ```

2. **Frontend served** (for visual validation):
   ```bash
   python -m http.server 8080 -d frontend
   ```

3. **Playwright MCP configured** (already in `.mcp.json`)

## Running Numerical Validation

### Populate Baselines First

```bash
cd /media/sam/1TB/UTXOracle
python -c "
from validation.framework.checkonchain_fetcher import CheckOnChainFetcher
fetcher = CheckOnChainFetcher()
fetcher.update_all_baselines()
"
```

This creates baseline files in `validation/baselines/`.

### Run Validation

```python
from validation.framework.validator import MetricValidator

validator = MetricValidator(api_base_url="http://localhost:8000")
results = validator.run_all()

# Print report
print(validator.generate_report())
```

### Save Report

```python
from validation.framework.comparison_engine import ComparisonEngine

engine = ComparisonEngine(api_base_url="http://localhost:8000")
engine.run_numerical_validation()
report_path = engine.save_report()
print(f"Report saved: {report_path}")
```

## Running Visual Validation

### Using alpha-visual Agent

The `alpha-visual` subagent handles screenshot comparison:

```
# In Claude Code
Use alpha-visual agent to:
1. Navigate to http://localhost:8080/metrics/mvrv.html
2. Take screenshot
3. Navigate to https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html
4. Take screenshot
5. Compare and report deviations
```

### Manual Screenshot Comparison

```python
from validation.framework.visual_validator import VisualValidator

visual = VisualValidator()
result = visual.compare_metric("mvrv")
print(f"Status: {result.status}")
print(f"Trend Match: {result.trend_match}")
print(f"Alignment: {result.value_alignment}%")
```

## Directory Structure After Running

```
validation/
├── baselines/
│   ├── mvrv_baseline.json      ← Populated
│   ├── nupl_baseline.json      ← Populated
│   └── ...
├── cache/
│   ├── mvrv_cache.json         ← Auto-generated
│   └── ...
├── reports/
│   └── 2025-12-19_validation.md ← Generated
└── screenshots/
    ├── ours/
    │   └── mvrv.png            ← Our chart
    └── reference/
        └── mvrv.png            ← CheckOnChain
```

## Interpreting Results

### Status Codes

| Status | Meaning |
|--------|---------|
| ✅ PASS | Deviation within tolerance |
| ⚠️ WARN | Deviation between 1x-2x tolerance |
| ❌ FAIL | Deviation exceeds 2x tolerance |
| 🔴 ERROR | API error or missing data |

### Tolerance Reference

| Metric | Tolerance |
|--------|-----------|
| mvrv_z | ±2% |
| nupl | ±2% |
| sopr | ±1% |
| cdd | ±5% |
| hash_ribbons | ±3% |
| cost_basis | ±2% |

## Troubleshooting

### "Baseline not found"
Run baseline population first:
```python
fetcher.update_all_baselines()
```

### "API unavailable"
Ensure FastAPI is running:
```bash
curl http://localhost:8000/api/metrics/nupl
```

### Visual validation fails
1. Check frontend is served on port 8080
2. Verify Playwright MCP is connected
3. Check network access to charts.checkonchain.com
