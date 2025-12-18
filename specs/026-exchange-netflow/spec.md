# spec-026: Exchange Netflow

## Overview
Tracks BTC movement to/from known exchange addresses - primary indicator of selling pressure vs accumulation.

**Evidence Grade**: B-C (contadino_galattico.md: 42 sources)
**Priority**: CRITICAL (identified in all 3 contadino docs as missing Tier A metric)

## Formula
```
Exchange Inflow = SUM(btc_value) WHERE destination IN exchange_addresses
Exchange Outflow = SUM(btc_value) WHERE source IN exchange_addresses
Netflow = Inflow - Outflow
```

## Metrics
| Metric | Description |
|--------|-------------|
| `exchange_inflow` | BTC flowing into exchanges (sell pressure) |
| `exchange_outflow` | BTC flowing out of exchanges (accumulation) |
| `netflow` | Net flow (positive = selling, negative = accumulation) |
| `netflow_7d_ma` | 7-day moving average of netflow |
| `netflow_30d_ma` | 30-day moving average of netflow |

## Signal Interpretation
| Netflow | Interpretation |
|---------|----------------|
| Strong Positive (>1000 BTC/day) | Heavy selling pressure, bearish |
| Weak Positive (0-1000 BTC/day) | Mild selling, neutral-bearish |
| Weak Negative (-1000-0 BTC/day) | Mild accumulation, neutral-bullish |
| Strong Negative (<-1000 BTC/day) | Heavy accumulation, bullish |

## Implementation

### Data Source
- `utxo_lifecycle_full` VIEW - contains `address` column (UTXO destination address)
  - **Inflow detection**: UTXOs created at exchange addresses (`creation_timestamp` within window)
  - **Outflow detection**: UTXOs spent from exchange addresses (`spent_timestamp` within window)
- `data/exchange_addresses.csv` - Curated exchange address list (existing file)

### Exchange Address Sources
1. **Primary**: Publicly known exchange cold/hot wallets
2. **Secondary**: Heuristic clustering (spec-013)
3. **Maintained by**: Community lists (e.g., glassnode, chainalysis public data)

### Files
- `scripts/metrics/exchange_netflow.py` - Calculator
- `data/exchange_addresses.csv` - Curated address list (10 addresses from 4 major exchanges)
- `tests/test_exchange_netflow.py` - TDD tests
- `scripts/models/metrics_models.py` - Add ExchangeNetflowResult dataclass

### API
- `GET /api/metrics/exchange-netflow?window=24h`
- `GET /api/metrics/exchange-netflow/history?days=30`

### Query (Pseudo)
```sql
-- Requires exchange_addresses table/list
SELECT
    SUM(CASE WHEN dest_addr IN exchange_list THEN btc_value ELSE 0 END) AS inflow,
    SUM(CASE WHEN src_addr IN exchange_list THEN btc_value ELSE 0 END) AS outflow
FROM utxo_lifecycle_full
WHERE spent_timestamp >= NOW() - INTERVAL ? HOUR
```

## Dependencies
- `data/exchange_addresses.csv` - Existing curated exchange address list (MVP)
- `utxo_lifecycle_full` VIEW - Must exist with `address`, `btc_value`, `creation_timestamp`, `is_spent`, `spent_timestamp` columns

### Future Enhancements
- spec-013 (Address Clustering) - Could provide heuristic-detected exchange addresses (not required for MVP)

## Effort: 3-5 days (medium complexity due to external data requirement)
## ROI: Very High - primary indicator of market sentiment and capital flows
