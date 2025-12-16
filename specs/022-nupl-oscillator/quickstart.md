# Quickstart: NUPL Oscillator (spec-022)

## Prerequisites

- DuckDB database with `utxo_lifecycle_full` VIEW populated
- UTXOracle API running (`uv run uvicorn api.main:app`)

## Usage

### API Endpoint

```bash
curl http://localhost:8000/api/metrics/nupl
```

Response:
```json
{
  "nupl": 0.42,
  "zone": "OPTIMISM",
  "market_cap_usd": 2100000000000,
  "realized_cap_usd": 1218000000000,
  "unrealized_profit_usd": 882000000000,
  "pct_supply_in_profit": 75.3,
  "block_height": 872500,
  "timestamp": "2025-12-16T10:30:00Z",
  "confidence": 0.85
}
```

### Python Library

```python
from scripts.metrics.nupl import calculate_nupl_signal, NUPLZone
import duckdb

conn = duckdb.connect("data/utxo.duckdb")
current_price = 105000.0  # BTC price in USD
block_height = 872500

result = calculate_nupl_signal(conn, block_height, current_price)

print(f"NUPL: {result.nupl:.2f}")
print(f"Zone: {result.zone.value}")
print(f"Market Cap: ${result.market_cap_usd:,.0f}")
print(f"Realized Cap: ${result.realized_cap_usd:,.0f}")
```

## Zone Interpretation

| Zone | NUPL Range | Market Phase | Action Signal |
|------|------------|--------------|---------------|
| **CAPITULATION** | < 0 | Bottom | Strong accumulation |
| **HOPE_FEAR** | 0 - 0.25 | Early recovery | Accumulate |
| **OPTIMISM** | 0.25 - 0.5 | Bull building | Hold |
| **BELIEF** | 0.5 - 0.75 | Strong bull | Hold / Take partial profits |
| **EUPHORIA** | > 0.75 | Cycle top | Distribute |

## Testing

```bash
# Run NUPL tests
uv run pytest tests/test_nupl.py -v

# Run with coverage
uv run pytest tests/test_nupl.py -v --cov=scripts/metrics/nupl
```

## Troubleshooting

### Error: "UTXO lifecycle data not available"

Run the UTXO sync to populate the database:

```bash
python scripts/metrics/utxo_lifecycle.py sync --start 800000
```

### NUPL returns 0.0

Check that:
1. `utxo_lifecycle_full` VIEW exists
2. UTXOs have been synced for recent blocks
3. Price data is available (non-zero)
