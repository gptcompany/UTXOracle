# spec-028: Net Realized Profit/Loss

## Overview
Aggregate realized gains/losses from spent UTXOs - shows actual capital flows, not just paper P/L.
When coins move at a profit/loss, this metric captures the aggregate flow direction.

**Evidence Grade**: A (derivative of spec-017 UTXO lifecycle)
**Priority**: Quick Win (low complexity, leverages existing data)

## Formula
```
Realized Profit = SUM(spent_price - creation_price) WHERE spent_price > creation_price
Realized Loss = SUM(creation_price - spent_price) WHERE spent_price < creation_price
Net Realized P/L = Realized Profit - Realized Loss
```

## Metrics
| Metric | Description |
|--------|-------------|
| `realized_profit_btc` | Total profit realized (BTC terms) |
| `realized_profit_usd` | Total profit realized (USD terms) |
| `realized_loss_btc` | Total loss realized (BTC terms) |
| `realized_loss_usd` | Total loss realized (USD terms) |
| `net_realized_pnl_btc` | Net P/L (positive = profit dominant) |
| `net_realized_pnl_usd` | Net P/L in USD |
| `profit_utxo_count` | Count of UTXOs spent at profit |
| `loss_utxo_count` | Count of UTXOs spent at loss |

## Signal Interpretation

### Threshold Definitions
| Signal | Net P/L (USD) | Profit/Loss Ratio |
|--------|---------------|-------------------|
| Strong Positive | > $1,000,000 | > 1.5 |
| Moderate Positive | $100,000 - $1,000,000 | 1.1 - 1.5 |
| Neutral | -$100,000 - $100,000 | 0.9 - 1.1 |
| Moderate Negative | -$1,000,000 - -$100,000 | 0.5 - 0.9 |
| Strong Negative | < -$1,000,000 | < 0.5 |

### Market Context Matrix
| Signal | Bull Market | Bear Market |
|--------|-------------|-------------|
| Strong Positive | Healthy profit-taking, sustainable | Capitulation complete, potential bottom |
| Moderate Positive | Normal distribution | Recovery phase |
| Neutral | Consolidation | Indecision |
| Moderate Negative | Profit-taking exhaustion | Ongoing capitulation |
| Strong Negative | Panic selling, watch for reversal | Continued capitulation, not bottomed |

## Implementation

### Data Source
- `utxo_lifecycle_full` VIEW (btc_value, creation_price, spent_price, is_spent)
- Price data from UTXOracle or mempool.space

### Files
- `scripts/metrics/net_realized_pnl.py` - Calculator
- `tests/test_net_realized_pnl.py` - TDD tests
- `scripts/models/metrics_models.py` - Add NetRealizedPnLResult dataclass

### API
- `GET /api/metrics/net-realized-pnl?window=24h`
- `GET /api/metrics/net-realized-pnl/history?days=30`

### Query
```sql
SELECT
    SUM(CASE WHEN spent_price_usd > creation_price_usd
        THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END) AS realized_profit,
    SUM(CASE WHEN spent_price_usd < creation_price_usd
        THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END) AS realized_loss,
    COUNT(CASE WHEN spent_price_usd > creation_price_usd THEN 1 END) AS profit_count,
    COUNT(CASE WHEN spent_price_usd < creation_price_usd THEN 1 END) AS loss_count
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND spent_timestamp >= NOW() - INTERVAL ? HOUR
```

## Dependencies
- spec-017 (UTXO Lifecycle Engine) - provides UTXO creation/spent prices

## Effort: 2-3 hours (low complexity)
## ROI: High - shows actual capital flows vs paper gains/losses
