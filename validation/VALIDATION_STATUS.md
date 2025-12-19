# Validation Status Tracker

**Last Updated**: 2025-12-19T22:31:00
**Validation Framework**: spec-031

## Summary

| Category | Count |
|----------|-------|
| Total Metrics | 28 |
| Tier A (Reference Validation) | 15 |
| Tier B (Computational Validation) | 10 |
| Tier C (Derived/Secondary) | 3 |
| Validated PASS | 4 |
| Known Differences | 3 |
| Skipped (no data) | 1 |
| Pending (no endpoint) | 0 |
| Broken Endpoints | 3 |

## Validated Metrics

### PASS (Matching Reference)

| Metric | Our Value | Reference | Deviation | Tolerance | Endpoint |
|--------|-----------|-----------|-----------|-----------|----------|
| MVRV | 1.5000 | 1.5395 | 2.56% | ±5.0% | `/api/metrics/reserve-risk` |
| Hash Ribbons 30d | 1057.21 | 1055.89 | 0.12% | ±3.0% | `/api/metrics/hash-ribbons` |
| Hash Ribbons 60d | 1076.52 | 1075.80 | 0.07% | ±3.0% | `/api/metrics/hash-ribbons` |
| SOPR | 1.0000 | 0.9939 | 0.61% | ±2.0% | `/api/metrics/sopr` |

### KNOWN_DIFF (Expected Definitional Difference)

| Metric | Our Value | Reference | Deviation | Root Cause | Fix Required |
|--------|-----------|-----------|-----------|------------|--------------|
| NUPL | 0.4376 | 0.6869 | 36.29% | UTXO-level vs wallet-level Realized Cap | spec-013 Phase 9 |
| Cost Basis | $56,236 | $18,492 | 204% | Our Realized Price vs CheckOnChain Yearly Cost Basis | Different metrics |
| Puell Multiple | 2.00 | 0.81 | 145.8% | Simplified 365d MA (static $50k) vs actual historical data | Add historical price API |

### SKIP (Insufficient Data)

| Metric | Reason | Endpoint Status |
|--------|--------|-----------------|
| Binary CDD | `insufficient_data: true` (need spent UTXO history) | Working |

## Pending Validation

### Completed Endpoints (Previously Pending)

| Metric | Baseline Available | Endpoint | Status |
|--------|-------------------|----------|--------|
| SOPR | ✅ `sopr_baseline.json` | ✅ `/api/metrics/sopr` | PASS (0.61% deviation) |
| Puell Multiple | ✅ `puell_multiple_baseline.json` | ✅ `/api/metrics/puell-multiple` | KNOWN_DIFF (simplified 365d MA) |

### Broken Endpoints (Need Fix)

| Metric | Endpoint | Error | Priority |
|--------|----------|-------|----------|
| P/L Ratio | `/api/metrics/pl-ratio` | BIGINT vs TIMESTAMP type mismatch | HIGH |
| Net Realized P&L | `/api/metrics/net-realized-pnl` | BIGINT vs TIMESTAMP type mismatch | HIGH |
| CDD/VDD | `/api/metrics/cdd-vdd` | BIGINT vs TIMESTAMP type mismatch | HIGH |

## Baselines Available

Located in `validation/baselines/`:

| Baseline File | Metric | Source | Captured |
|---------------|--------|--------|----------|
| `mvrv_baseline.json` | MVRV | CheckOnChain | 2025-12-19 |
| `nupl_baseline.json` | NUPL | CheckOnChain | 2025-12-19 |
| `hash_ribbons_baseline.json` | Hash Ribbons | CheckOnChain | 2025-12-19 |
| `sopr_baseline.json` | SOPR | CheckOnChain | 2025-12-19 |
| `cdd_baseline.json` | CDD | CheckOnChain | 2025-12-19 |
| `cost_basis_baseline.json` | Cost Basis | CheckOnChain | 2025-12-19 |
| `puell_multiple_baseline.json` | Puell Multiple | CheckOnChain | 2025-12-19 |

## Action Items

1. **Fix BIGINT vs TIMESTAMP bug** in:
   - `scripts/metrics/pl_ratio.py`
   - `scripts/metrics/net_realized_pnl.py`
   - `scripts/metrics/cdd_vdd.py`

2. **Add SOPR endpoint** to `api/main.py`:
   - Expected endpoint: `/api/metrics/sopr`
   - Expected response: `{"aggregate_sopr": float, "sth_sopr": float, "lth_sopr": float}`
   - Implementation exists in `scripts/metrics/sopr.py`
   - Validator added: `validate_sopr()` (returns ERROR until endpoint exists)

3. **Add Puell Multiple endpoint** to `api/main.py`:
   - Expected endpoint: `/api/metrics/puell-multiple`
   - Expected response: `{"puell_multiple": float, "daily_issuance_usd": float, "ma_365d": float}`
   - Need to create implementation (see CheckOnChain for reference)
   - Validator added: `validate_puell_multiple()` (returns ERROR until endpoint exists)

4. **Long-term**: Implement spec-013 Phase 9 for wallet-level cost basis

## Comprehensive Validation Matrix

### Tier A - Reference Validation Required

These metrics have external baselines (CheckOnChain, LookingIntoBitcoin, Glassnode) for validation.

| Metric | File | Free Reference Source | Validation Status | Baseline File |
|--------|------|----------------------|-------------------|---------------|
| MVRV | realized_metrics.py | CheckOnChain API (free) | PASS (2.56% deviation) | mvrv_baseline.json |
| NUPL | nupl.py | CheckOnChain API (free) | KNOWN_DIFF (36.29%, spec-013 Phase 9 needed) | nupl_baseline.json |
| SOPR | sopr.py | CheckOnChain API (free) | Pending endpoint | sopr_baseline.json |
| Reserve Risk | reserve_risk.py | CheckOnChain API (free) | Validated via MVRV | mvrv_baseline.json |
| HODL Waves | hodl_waves.py | CheckOnChain/Glassnode | Not started | - |
| URPD | urpd.py | CheckOnChain/Glassnode | Not started | - |
| Supply P/L | supply_profit_loss.py | Glassnode (limited free) | Not started | - |
| Realized Cap | realized_metrics.py | CheckOnChain API (free) | Embedded in MVRV | mvrv_baseline.json |
| Cost Basis | cost_basis.py | CheckOnChain API (free) | KNOWN_DIFF (204%, different metric) | cost_basis_baseline.json |
| Hash Ribbons | mining_economics.py | CheckOnChain API (free) | PASS (0.12% deviation) | hash_ribbons_baseline.json |
| CDD/VDD | cdd_vdd.py | CheckOnChain API (free) | ERROR (BIGINT bug) | cdd_baseline.json |
| Binary CDD | binary_cdd.py | CheckOnChain API (free) | SKIP (insufficient data) | - |
| P/L Ratio | pl_ratio.py | CheckOnChain API (free) | ERROR (BIGINT bug) | - |
| Net Realized P&L | net_realized_pnl.py | CheckOnChain API (free) | ERROR (BIGINT bug) | - |
| Puell Multiple | mining_economics.py | CheckOnChain API (free) | Pending endpoint | puell_multiple_baseline.json |

**Free Reference Sources:**
- **CheckOnChain API**: https://api.checkonchain.com (free tier, comprehensive coverage)
- **LookingIntoBitcoin**: https://www.lookintobitcoin.com (limited free data, visual charts)
- **CryptoQuant Free**: https://cryptoquant.com/asset/btc/chart (some metrics free, rate limited)
- **Bitcoin Magazine Pro**: https://charts.bitcoinmagazinepro.com (limited free charts)
- **Glassnode Studio**: https://studio.glassnode.com (free tier, 10 API calls/day)

### Tier B - Computational Validation

These are UTXOracle-specific implementations with no external reference. Validation is via computational correctness.

| Metric | File | Validation Method | Status | Notes |
|--------|------|-------------------|--------|-------|
| Power Law | power_law.py | Mathematical proof + unit tests | Complete | MLE + KS test validated |
| Symbolic Dynamics | symbolic_dynamics.py | Reference implementation (Bandt & Pompe 2002) | Complete | Permutation entropy validated |
| Fractal Dimension | fractal_dimension.py | Box-counting algorithm verification | Complete | Standard algorithm |
| Wasserstein Distance | wasserstein.py | Quantile-based algorithm (Peyré & Cuturi 2019) | Complete | O(n log n) validated |
| Monte Carlo Fusion | monte_carlo_fusion.py | Statistical convergence tests | Complete | 10,000 iteration bootstrap |
| Active Addresses | active_addresses.py | Count verification vs Bitcoin Core | Pending | Need RPC cross-check |
| TX Volume | tx_volume.py | Volume verification vs Bitcoin Core | Pending | Need RPC cross-check |
| Wallet Waves | wallet_waves.py | Balance aggregation logic verification | Pending | Need balance cross-check |
| Absorption Rates | absorption_rates.py | Depends on Wallet Waves | Pending | Computational correctness only |
| Exchange Netflow | exchange_netflow.py | Depends on exchange address list | Pending | B-C grade (limited coverage) |

**Validation Approach:**
- Unit tests with known inputs/outputs
- Cross-validation with Bitcoin Core RPC data
- Statistical convergence tests (Monte Carlo)
- Mathematical proofs (Power Law MLE)

### Tier C - Derived/Secondary Metrics

These metrics depend on other metrics and are validated transitively.

| Metric | File | Depends On | Validation Approach | Status |
|--------|------|-----------|---------------------|--------|
| Revived Supply | revived_supply.py | CDD/VDD | Validates when CDD fixed | Blocked (CDD bug) |
| Sell Side Risk | sell_side_risk.py | MVRV, SOPR, Realized Cap | Validates when SOPR endpoint added | Pending |
| UTXO Lifecycle | utxo_lifecycle.py | All UTXO-based metrics | Foundation metric, validates via dependents | Complete |

**Cointime Metrics** (spec-018):
- cointime.py: Standalone implementation (Tier B)
- Requires historical UTXO destruction data
- Validation: Computational correctness via unit tests

## Validation Commands

```bash
# Run full validation
python -m validation

# Update baselines from CheckOnChain
python -m validation.framework.checkonchain_fetcher --update-all

# Run specific metric
python -c "from validation.framework.validator import MetricValidator; v=MetricValidator(); print(v.validate_mvrv())"

# Validate Tier B metric computationally
pytest tests/test_power_law.py -v
pytest tests/test_wasserstein.py -v
```
