# spec-024: Revived Supply

## Overview
Tracks dormant coins being spent - signals long-term holder behavior changes.

## Formula
```
Revived Supply = SUM(btc_value)
                 WHERE is_spent = TRUE
                 AND age_days >= threshold (default: 365)
                 AND spent_timestamp IN window (default: 30 days)
```

## Metrics
| Metric | Description |
|--------|-------------|
| `revived_1y` | BTC revived after 1+ year dormancy |
| `revived_2y` | BTC revived after 2+ year dormancy |
| `revived_5y` | BTC revived after 5+ year dormancy |
| `revived_total_usd` | USD value of revived supply |
| `revived_avg_age` | Average age of revived UTXOs |

## Signal Zones
| Zone | Revived/Day | Interpretation |
|------|-------------|----------------|
| DORMANT | < 1000 BTC | Low LTH activity |
| NORMAL | 1000-5000 BTC | Baseline movement |
| ELEVATED | 5000-10000 BTC | Increased LTH selling |
| SPIKE | > 10000 BTC | Major distribution event |

## Implementation

### Data Source
- `utxo_lifecycle_full` VIEW (btc_value, age_days, spent_timestamp, is_spent)

### Query
```sql
SELECT
    SUM(btc_value) AS revived_btc,
    AVG(age_days) AS avg_age,
    COUNT(*) AS utxo_count
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND age_days >= ?  -- threshold
  AND spent_timestamp >= NOW() - INTERVAL ? DAY  -- window
```

### Files
- `scripts/metrics/revived_supply.py` - Calculator
- `tests/test_revived_supply.py` - TDD tests
- `scripts/models/metrics_models.py` - Add RevivedZone enum + RevivedSupplyResult dataclass

### API
- `GET /api/metrics/revived-supply?threshold=365&window=30`

## Effort: 2-3 hours
## Evidence Grade: A (CheckOnChain holder behavior metric)
## ROI: High - tracks long-term holder conviction changes
