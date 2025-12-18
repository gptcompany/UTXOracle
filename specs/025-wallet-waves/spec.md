# spec-025: Wallet Waves & Absorption Rates

## Overview
Supply distribution across wallet size bands (shrimp to whale) and rate at which each cohort absorbs new supply.
Reveals retail vs institutional accumulation patterns and conviction by holder class.

**Evidence Grade**: B-C (CheckOnChain.com, contadino docs)
**Priority**: Tier 1 - High Value

## Part 1: Wallet Waves

### Formula
```
Wallet Band Supply = SUM(balance) WHERE balance IN band_range
Wallet Wave = Wallet Band Supply / Total Supply
```

### Wallet Size Bands
| Band | Name | Balance Range | Typical Entity |
|------|------|---------------|----------------|
| 1 | Shrimp | < 1 BTC | Retail small |
| 2 | Crab | 1-10 BTC | Retail medium |
| 3 | Fish | 10-100 BTC | High net worth |
| 4 | Shark | 100-1,000 BTC | Institutions small |
| 5 | Whale | 1,000-10,000 BTC | Institutions |
| 6 | Humpback | > 10,000 BTC | Exchanges, funds |

### Metrics
| Metric | Description |
|--------|-------------|
| `band_supply_btc[1-6]` | BTC held by each band |
| `band_supply_pct[1-6]` | Percentage of supply per band |
| `band_address_count[1-6]` | Number of addresses per band |
| `band_avg_balance[1-6]` | Average balance per band |

---

## Part 2: Absorption Rates

### Formula
```
Absorption Rate = (Band_Supply_t - Band_Supply_t-n) / New_Supply_Mined
```
Where `n` = lookback period (7d, 30d, 90d)

### Metrics
| Metric | Description |
|--------|-------------|
| `absorption_rate_7d[1-6]` | 7-day absorption rate per band |
| `absorption_rate_30d[1-6]` | 30-day absorption rate per band |
| `dominant_absorber` | Band with highest absorption rate |
| `retail_absorption` | Combined bands 1-3 absorption |
| `institutional_absorption` | Combined bands 4-6 absorption |

### Signal Interpretation
| Pattern | Interpretation |
|---------|----------------|
| Whale absorption high | Smart money accumulating, bullish |
| Shrimp absorption high | Retail FOMO, potential top |
| Institutional > Retail | Healthy accumulation |
| Retail > Institutional | Distribution phase |

---

## Implementation

### Data Source
- `utxo_lifecycle_full` VIEW (address, btc_value)
- Address balance aggregation (sum UTXOs per address)

### Address Balance Calculation
```sql
-- Step 1: Calculate current balance per address
CREATE VIEW address_balances AS
SELECT
    address,
    SUM(CASE WHEN is_spent = FALSE THEN btc_value ELSE 0 END) AS balance
FROM utxo_lifecycle_full
WHERE address IS NOT NULL
GROUP BY address
HAVING balance > 0;

-- Step 2: Aggregate by wallet band
SELECT
    CASE
        WHEN balance < 1 THEN 'shrimp'
        WHEN balance < 10 THEN 'crab'
        WHEN balance < 100 THEN 'fish'
        WHEN balance < 1000 THEN 'shark'
        WHEN balance < 10000 THEN 'whale'
        ELSE 'humpback'
    END AS band,
    COUNT(*) AS address_count,
    SUM(balance) AS total_btc
FROM address_balances
GROUP BY band;
```

### Files
- `scripts/metrics/wallet_waves.py` - Wallet distribution calculator
- `scripts/metrics/absorption_rates.py` - Absorption rate calculator
- `tests/test_wallet_waves.py` - TDD tests
- `tests/test_absorption_rates.py` - TDD tests
- `scripts/models/metrics_models.py` - Add WalletBand enum, WalletWavesResult, AbsorptionRatesResult

### API
- `GET /api/metrics/wallet-waves` - Current distribution
- `GET /api/metrics/wallet-waves/history?days=30` - Historical waves
- `GET /api/metrics/absorption-rates?window=30d` - Absorption rates

## Dependencies
- spec-017 (UTXO Lifecycle) - provides address-level UTXO data
- spec-013 (Address Clustering) - optional, improves accuracy

## Caveats
- Exchange addresses inflate whale bands (use spec-026 to filter)
- Lost coins appear as long-term holders
- Address reuse affects accuracy

## Effort: 4-6 hours (medium complexity)
## ROI: High - reveals retail vs institutional sentiment shifts
