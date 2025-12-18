# Quickstart: Exchange Netflow (spec-026)

**Date**: 2025-12-18
**Status**: Ready for Implementation

## Overview

Exchange Netflow tracks BTC movement to/from known exchange addresses, providing a primary indicator of selling pressure vs accumulation.

| Metric | Description |
|--------|-------------|
| `exchange_inflow` | BTC flowing into exchanges (sell pressure) |
| `exchange_outflow` | BTC flowing out of exchanges (accumulation) |
| `netflow` | Inflow - Outflow (positive = selling, negative = accumulation) |

## Prerequisites

- Python 3.11+
- DuckDB database with `utxo_lifecycle_full` VIEW populated
- Existing `data/exchange_addresses.csv` file

## Installation

No new dependencies required. Uses existing project infrastructure.

## Quick Test

```bash
# Run TDD tests (RED phase first)
uv run pytest tests/test_exchange_netflow.py -v

# After implementation (GREEN phase)
uv run pytest tests/test_exchange_netflow.py -v --cov=scripts/metrics/exchange_netflow
```

## API Usage

### Get Current Netflow

```bash
curl http://localhost:8000/api/metrics/exchange-netflow
```

Response:
```json
{
    "exchange_inflow": 5432.50,
    "exchange_outflow": 4234.75,
    "netflow": 1197.75,
    "netflow_7d_ma": 856.25,
    "netflow_30d_ma": 523.10,
    "zone": "weak_inflow",
    "confidence": 0.75
}
```

### Get Historical Data

```bash
curl http://localhost:8000/api/metrics/exchange-netflow/history?days=30
```

### Custom Window

```bash
# 48-hour window
curl "http://localhost:8000/api/metrics/exchange-netflow?window=48"
```

## Signal Interpretation

| Zone | Netflow | Market Signal |
|------|---------|---------------|
| `strong_outflow` | < -1000 BTC/day | Bullish (heavy accumulation) |
| `weak_outflow` | -1000 to 0 | Neutral-bullish |
| `weak_inflow` | 0 to 1000 | Neutral-bearish |
| `strong_inflow` | > 1000 BTC/day | Bearish (heavy selling) |

## Code Example

```python
from scripts.metrics.exchange_netflow import (
    calculate_exchange_netflow,
    classify_netflow_zone,
    load_exchange_addresses,
)
import duckdb

# Connect to database
conn = duckdb.connect("data/utxo_lifecycle.duckdb")

# Load exchange addresses
addresses = load_exchange_addresses("data/exchange_addresses.csv")

# Calculate netflow (24h window)
result = calculate_exchange_netflow(
    conn=conn,
    exchange_addresses=addresses,
    window_hours=24,
    current_price_usd=105000.0,
    block_height=875000,
)

print(f"Netflow: {result.netflow:.2f} BTC")
print(f"Zone: {result.zone.value}")
print(f"7-day MA: {result.netflow_7d_ma:.2f} BTC")
```

## File Structure

```
scripts/
├── metrics/
│   └── exchange_netflow.py      # Calculator module
├── models/
│   └── metrics_models.py        # NetflowZone enum, ExchangeNetflowResult
├── data/
│   └── exchange_addresses.csv   # Exchange address list

api/
└── main.py                      # API endpoints

tests/
└── test_exchange_netflow.py     # TDD tests
```

## Exchange Address Management

The exchange address list is stored in `data/exchange_addresses.csv`:

```csv
exchange_name,address,type
Binance,1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX,hot_wallet
Kraken,3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE,cold_wallet
...
```

To add new exchanges:
1. Edit `data/exchange_addresses.csv`
2. Restart the API service
3. New addresses will be included in netflow calculations

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Empty results | Check `utxo_lifecycle_full` VIEW has data |
| Zero confidence | Verify `exchange_addresses.csv` exists and is valid |
| Slow queries | Ensure DuckDB indexes are created |

## Related Specs

- [spec-013](../013-address-clustering/spec.md): Address Clustering (future exchange detection)
- [spec-017](../017-utxo-lifecycle-engine/spec.md): UTXO Lifecycle Engine (data source)
- [spec-024](../024-revived-supply/spec.md): Revived Supply (similar pattern)
