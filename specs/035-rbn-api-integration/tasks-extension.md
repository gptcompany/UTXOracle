# Tasks: RBN Validation System Extension (spec-035)

**Extension to**: spec-035 (RBN API Integration)
**Date**: 2025-12-27
**Purpose**: Double-verification system for UTXOracle metrics

## Summary

Implements Option D (Hybrid) validation approach:
- Weekly batch validation against RBN reference data
- Golden data tests integrated in pytest
- Alerting on significant deviations

---

## Phase 1: Infrastructure (Completed ✅)

- [X] T001 Implement MetricLoader in scripts/integrations/metric_loader.py
  - Loads data from DuckDB tables
  - Falls back to golden data for tests
  - Supports P1 metrics: MVRV, SOPR, NUPL, Realized Cap

- [X] T002 Update ValidationService.load_utxoracle_metric() to use MetricLoader
  - scripts/integrations/rbn_validator.py updated
  - Now loads actual data instead of returning empty dict

- [X] T003 Create golden data infrastructure
  - tests/validation/golden_data/ directory
  - scripts/integrations/golden_data_manager.py
  - Synthetic data generation for testing
  - RBN download capability (requires API token)

- [X] T004 Create validation test suite
  - tests/validation/__init__.py
  - tests/validation/test_rbn_validation.py
  - 11 tests covering all P1 metrics
  - Uses @pytest.mark.validation marker

---

## Phase 2: Batch Validation (Completed ✅)

- [X] T005 Create weekly batch validation script
  - scripts/integrations/validation_batch.py
  - Validates all P1+P2 metrics
  - Calculates correlation and MAPE
  - Determines pass/warn/fail status

- [X] T006 Add HTML report generator
  - Generates professional HTML reports
  - Color-coded status indicators
  - Saved to reports/validation/

- [X] T007 Add JSON report output
  - Machine-readable format
  - Includes all metrics and statistics

- [X] T008 Add webhook alerting
  - Slack-compatible webhook format
  - Triggered on failures only
  - Configurable via VALIDATION_WEBHOOK_URL

---

## Files Created/Modified

### New Files
- scripts/integrations/metric_loader.py
- scripts/integrations/golden_data_manager.py
- scripts/integrations/validation_batch.py
- tests/validation/__init__.py
- tests/validation/test_rbn_validation.py
- tests/validation/golden_data/*.parquet

### Modified Files
- scripts/integrations/rbn_validator.py
- pyproject.toml (added validation marker)

---

## Usage

```bash
# Generate synthetic golden data (no API token needed)
python scripts/integrations/golden_data_manager.py --generate-synthetic

# Run validation tests
uv run pytest tests/validation/ -v

# Run batch validation with HTML report
PYTHONPATH=. python scripts/integrations/validation_batch.py --html

# Download real RBN data (requires RBN_API_TOKEN)
RBN_API_TOKEN=xxx python scripts/integrations/golden_data_manager.py --download

# Weekly cron job
0 2 * * 0 cd /path/to/UTXOracle && PYTHONPATH=. python scripts/integrations/validation_batch.py --html --alert
```

---

## Thresholds

| Metric | Correlation | MAPE | Status |
|--------|-------------|------|--------|
| All | > 0.90 | < 10% | PASS |
| All | > 0.90 | 10-20% | WARN |
| All | < 0.90 | > 20% | FAIL |

---

## P1 Metrics (Priority 1)

| Metric | RBN Endpoint | UTXOracle Spec |
|--------|--------------|----------------|
| mvrv_z | mvrv_z | spec-007 |
| sopr | sopr | spec-016 |
| nupl | net_unrealized_profit_loss | spec-007 |
| realized_cap | realized_cap | spec-007 |

## P2 Metrics (Priority 2)

| Metric | RBN Endpoint | UTXOracle Spec |
|--------|--------------|----------------|
| liveliness | liveliness | spec-018 |
| power_law | price_power_law_qr | spec-034 |

---

## Next Steps

1. **Get RBN API Token**: Register at researchbitcoin.net for free tier
2. **Download Real Data**: Replace synthetic golden data with actual RBN data
3. **Set Up Cron**: Schedule weekly validation runs
4. **Configure Webhook**: Set VALIDATION_WEBHOOK_URL for alerts
