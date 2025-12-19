# Quickstart: P/L Ratio (Dominance)

**Spec**: spec-029 | **Date**: 2025-12-19

## Prerequisites

- Python 3.11+
- DuckDB with `utxo_lifecycle_full` VIEW (from spec-017)
- spec-028 Net Realized P/L module installed

## Installation

No additional dependencies required. Uses existing project infrastructure.

## Usage

### Python API

```python
from scripts.metrics.pl_ratio import (
    calculate_pl_ratio,
    get_pl_ratio_history,
)
from scripts.models.metrics_models import PLDominanceZone
import duckdb

# Connect to database
conn = duckdb.connect("path/to/utxoracle.duckdb")

# Calculate current P/L ratio (24-hour window)
result = calculate_pl_ratio(conn, window_hours=24)

print(f"P/L Ratio: {result.pl_ratio:.2f}")
print(f"P/L Dominance: {result.pl_dominance:.2%}")
print(f"Zone: {result.dominance_zone.value}")
print(f"Profit Dominant: {result.profit_dominant}")

# Get historical data (30 days)
history = get_pl_ratio_history(conn, days=30)
for point in history:
    print(f"{point.date}: {point.dominance_zone.value} (ratio: {point.pl_ratio:.2f})")

conn.close()
```

### REST API

```bash
# Get current P/L ratio (24-hour window)
curl "http://localhost:8000/api/metrics/pl-ratio?window_hours=24"

# Get 30-day history
curl "http://localhost:8000/api/metrics/pl-ratio/history?days=30"
```

### Example Response

```json
{
  "pl_ratio": 2.5,
  "pl_dominance": 0.43,
  "profit_dominant": true,
  "dominance_zone": "PROFIT",
  "realized_profit_usd": 250000.0,
  "realized_loss_usd": 100000.0,
  "window_hours": 24,
  "timestamp": "2025-12-19T12:00:00Z"
}
```

## Zone Interpretation

| Zone | Meaning | Action |
|------|---------|--------|
| `EXTREME_PROFIT` | Euphoria | Caution: potential top |
| `PROFIT` | Bull market | Normal, profits being taken |
| `NEUTRAL` | Equilibrium | Sideways, no clear trend |
| `LOSS` | Bear market | Normal, losses being realized |
| `EXTREME_LOSS` | Capitulation | Caution: potential bottom |

## Key Metrics

1. **P/L Ratio**: `Profit / Loss`
   - > 1.0: Profit dominant
   - < 1.0: Loss dominant
   - = 1.0: Neutral

2. **P/L Dominance**: `(Profit - Loss) / (Profit + Loss)`
   - Range: -1.0 to +1.0
   - Positive: More profits being realized
   - Negative: More losses being realized

## Troubleshooting

### No data returned

Check that `utxo_lifecycle_full` VIEW has data:

```sql
SELECT COUNT(*) FROM utxo_lifecycle_full WHERE is_spent = TRUE;
```

### Division by zero

When loss = 0, the ratio returns `1e9` (effectively infinite profit).
When profit + loss = 0, dominance returns `0.0` (no activity).

### Connection issues

Ensure DuckDB file path is correct and database is not locked by another process.
