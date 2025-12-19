# spec-029: Profit/Loss Ratio (Dominance)

## Overview
Ratio of profit-taking to loss-taking activity - shows which side dominates market activity.
Simple but powerful indicator of market regime and sentiment.

**Evidence Grade**: A (derivative of spec-028 Net Realized P/L)
**Priority**: Quick Win (very low complexity once spec-028 exists)

## Formula
```
P/L Ratio = Realized Profit / Realized Loss
P/L Dominance = (Profit - Loss) / (Profit + Loss)  # Normalized -1 to +1
```

## Metrics
| Metric | Description |
|--------|-------------|
| `pl_ratio` | Raw ratio (Profit / Loss) |
| `pl_dominance` | Normalized dominance (-1 to +1) |
| `profit_dominant` | Boolean flag (ratio > 1) |
| `dominance_zone` | Categorical zone classification |

## Signal Zones
| Zone | P/L Ratio | Dominance | Interpretation |
|------|-----------|-----------|----------------|
| EXTREME_PROFIT | > 5.0 | > 0.67 | Euphoria, potential top |
| PROFIT | 1.5 - 5.0 | 0.2 - 0.67 | Healthy bull market |
| NEUTRAL | 0.67 - 1.5 | -0.2 - 0.2 | Equilibrium |
| LOSS | 0.2 - 0.67 | -0.67 - -0.2 | Bear market |
| EXTREME_LOSS | < 0.2 | < -0.67 | Capitulation, potential bottom |

## Implementation

### Data Source
Reuses spec-028 `calculate_net_realized_pnl()` result to derive ratio metrics.
Avoids duplicate queries to `utxo_lifecycle_full` VIEW.

### Files
- `scripts/metrics/pl_ratio.py` - Calculator
- `tests/test_pl_ratio.py` - TDD tests
- `scripts/models/metrics_models.py` - Add PLRatioResult dataclass, PLDominanceZone enum

### API
- `GET /api/metrics/pl-ratio?window_hours=24`
- `GET /api/metrics/pl-ratio/history?days=30`

### Query
```sql
-- Can reuse spec-028 results or calculate directly
WITH pnl AS (
    SELECT
        SUM(CASE WHEN spent_price_usd > creation_price_usd
            THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END) AS profit,
        SUM(CASE WHEN spent_price_usd < creation_price_usd
            THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END) AS loss
    FROM utxo_lifecycle_full
    WHERE is_spent = TRUE AND spent_timestamp >= NOW() - INTERVAL ? HOUR
)
SELECT
    profit / NULLIF(loss, 0) AS pl_ratio,
    (profit - loss) / NULLIF(profit + loss, 0) AS pl_dominance
FROM pnl
```

## Dependencies
- spec-028 (Net Realized P/L) - OR direct UTXO lifecycle data

## Effort: 1-2 hours (very low complexity)
## ROI: High - simple yet effective market regime indicator
