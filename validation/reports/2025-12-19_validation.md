# Validation Report

**Generated**: 2025-12-19T23:26:45.939193

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 4 |
| ⚠️ WARN | 0 |
| ❌ FAIL | 1 |
| 🔴 ERROR | 0 |
| 🔷 KNOWN_DIFF | 2 |
| ⏭️ SKIP | 1 |

## Details

| Metric | Our Value | Reference | Deviation | Tolerance | Status | Notes |
|--------|-----------|-----------|-----------|-----------|--------|-------|
| mvrv | 1.5000 | 1.5189 | 1.24% | ±5.0% | ✅ |  |
| nupl | 0.6869 | 0.6869 | 0.00% | ±1.0% | ✅ |  |
| hash_ribbons_30d | 1057.2086 | 1058.1557 | 0.09% | ±3.0% | ✅ |  |
| hash_ribbons_60d | 1076.5245 | 1076.1038 | 0.04% | ±3.0% | ✅ |  |
| cost_basis | 56236.0366 | 18498.7228 | 204.00% | ±5.0% | 🔷 | Our Realized Price vs CheckOnChain Yearly Cost Basis (different metrics) |
| binary_cdd | 0.0000 | 0.0000 | 0.00% | ±0.0% | ⏭️ | Insufficient data for CDD calculation |
| sopr | 1.0000 | 0.9517 | 5.08% | ±2.0% | ❌ |  |
| puell_multiple | 2.0000 | 0.8413 | 137.73% | ±10.0% | 🔷 | Simplified 365d MA (static $50k avg) vs CheckOnChain actual historical data |
