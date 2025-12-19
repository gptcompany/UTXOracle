# Quickstart: Net Realized Profit/Loss (spec-028)

Get up and running with the Net Realized P/L metric in under 5 minutes.

## Prerequisites

- Python 3.11+
- DuckDB database with `utxo_lifecycle_full` VIEW populated
- UTXOracle API server running

## Installation

No additional dependencies required - uses existing infrastructure.

```bash
# Verify existing setup
uv run python -c "import duckdb; print('DuckDB:', duckdb.__version__)"
```

## Quick Test

### 1. Verify Data Source

```python
import duckdb

conn = duckdb.connect("data/utxo_metrics.duckdb")

# Check VIEW exists and has data
result = conn.execute("""
    SELECT COUNT(*) as spent_count
    FROM utxo_lifecycle_full
    WHERE is_spent = TRUE
      AND creation_price_usd > 0
      AND spent_price_usd > 0
""").fetchone()

print(f"Spent UTXOs with price data: {result[0]:,}")
```

### 2. Test Query

```python
# Calculate Net Realized P/L for last 24 hours
from datetime import datetime, timedelta

window_start = datetime.now() - timedelta(hours=24)

result = conn.execute("""
    SELECT
        COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
            THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS profit,
        COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
            THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS loss,
        COUNT(CASE WHEN spent_price_usd > creation_price_usd THEN 1 END) AS profit_count,
        COUNT(CASE WHEN spent_price_usd < creation_price_usd THEN 1 END) AS loss_count
    FROM utxo_lifecycle_full
    WHERE is_spent = TRUE
      AND spent_timestamp >= ?
      AND creation_price_usd > 0
      AND spent_price_usd > 0
""", [window_start]).fetchone()

profit, loss, profit_count, loss_count = result
net_pnl = profit - loss

print(f"Realized Profit: ${profit:,.2f}")
print(f"Realized Loss: ${loss:,.2f}")
print(f"Net P/L: ${net_pnl:,.2f}")
print(f"Profit UTXOs: {profit_count:,}")
print(f"Loss UTXOs: {loss_count:,}")
```

### 3. API Usage

```bash
# Start API server (if not running)
uv run uvicorn api.main:app --reload

# Get current Net Realized P/L
curl "http://localhost:8000/api/metrics/net-realized-pnl?window=24"

# Get 30-day history
curl "http://localhost:8000/api/metrics/net-realized-pnl/history?days=30"
```

## Expected Output

### Current Metrics Response

```json
{
  "realized_profit_usd": 1234567.89,
  "realized_loss_usd": 987654.32,
  "net_realized_pnl_usd": 246913.57,
  "realized_profit_btc": 12.34,
  "realized_loss_btc": 9.87,
  "net_realized_pnl_btc": 2.47,
  "profit_utxo_count": 15234,
  "loss_utxo_count": 12456,
  "profit_loss_ratio": 1.25,
  "signal": "PROFIT_DOMINANT",
  "window_hours": 24,
  "timestamp": "2025-12-18T12:00:00Z"
}
```

### History Response

```json
{
  "history": [
    {
      "date": "2025-12-17",
      "realized_profit_usd": 1100000.00,
      "realized_loss_usd": 900000.00,
      "net_realized_pnl_usd": 200000.00,
      "profit_utxo_count": 14500,
      "loss_utxo_count": 12000
    }
  ],
  "days": 30,
  "start_date": "2025-11-18",
  "end_date": "2025-12-17"
}
```

## Signal Interpretation

| Signal | Net P/L | Interpretation |
|--------|---------|----------------|
| `PROFIT_DOMINANT` | > 0 | More value realized as profit |
| `LOSS_DOMINANT` | < 0 | More value realized as loss |
| `NEUTRAL` | = 0 | Balanced profit/loss |

## Common Use Cases

### 1. Market Sentiment Check

```python
from scripts.metrics.net_realized_pnl import calculate_net_realized_pnl

result = calculate_net_realized_pnl(conn, window_hours=24)

if result.signal == "PROFIT_DOMINANT":
    print("Bulls taking profits - healthy market")
elif result.signal == "LOSS_DOMINANT":
    print("Capitulation in progress - watch for bottom")
```

### 2. Historical Analysis

```python
from scripts.metrics.net_realized_pnl import get_net_realized_pnl_history

history = get_net_realized_pnl_history(conn, days=30)

# Find days with largest losses (capitulation events)
capitulation_days = [
    day for day in history
    if day.net_realized_pnl_usd < -1_000_000
]
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Empty results | Verify `utxo_lifecycle_full` VIEW has spent UTXOs with price data |
| All zeros | Check `spent_timestamp` is within time window |
| Missing price data | Run `import_chainstate.py --create-view` to refresh VIEW |
| Slow queries | Ensure indexes exist on `is_spent`, `spent_timestamp` columns |

## Next Steps

1. Run tests: `uv run pytest tests/test_net_realized_pnl.py -v`
2. Check API docs: `http://localhost:8000/docs#/metrics`
3. Integrate with dashboard: Add chart to `frontend/`
