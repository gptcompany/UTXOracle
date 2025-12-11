# Quickstart: Advanced On-Chain Metrics (spec-021)

## Prerequisites

- Python 3.11+
- DuckDB database with `utxo_lifecycle` table populated
- UTXOracle FastAPI server running (for API access)

## Installation

```bash
# No additional dependencies needed - uses existing project dependencies
cd /media/sam/1TB/UTXOracle
```

## Module Usage

### URPD (UTXO Realized Price Distribution)

```python
import duckdb
from scripts.metrics.urpd import calculate_urpd

# Connect to DuckDB
conn = duckdb.connect("utxo_lifecycle.duckdb")

# Calculate URPD with $5,000 buckets
result = calculate_urpd(
    conn=conn,
    current_price_usd=100000.0,
    bucket_size_usd=5000.0,
    block_height=870000,
)

# Access results
print(f"Total supply: {result.total_supply_btc:.2f} BTC")
print(f"Supply in profit: {result.supply_below_price_pct:.1f}%")
print(f"Dominant bucket: ${result.dominant_bucket.price_low:,.0f} - ${result.dominant_bucket.price_high:,.0f}")

# Get bucket distribution
for bucket in result.buckets[:5]:  # Top 5 buckets
    print(f"  ${bucket.price_low:,.0f}: {bucket.btc_amount:,.0f} BTC ({bucket.percentage:.1f}%)")
```

### Supply in Profit/Loss

```python
from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

result = calculate_supply_profit_loss(
    conn=conn,
    current_price_usd=100000.0,
    block_height=870000,
)

print(f"Market phase: {result.market_phase}")
print(f"% in profit: {result.pct_in_profit:.1f}%")
print(f"STH in profit: {result.sth_pct_in_profit:.1f}%")
print(f"LTH in profit: {result.lth_pct_in_profit:.1f}%")
print(f"Signal strength: {result.signal_strength:.2f}")
```

### Reserve Risk

```python
from scripts.metrics.reserve_risk import calculate_reserve_risk

result = calculate_reserve_risk(
    conn=conn,
    current_price_usd=100000.0,
    block_height=870000,
)

print(f"Reserve Risk: {result.reserve_risk:.6f}")
print(f"Signal zone: {result.signal_zone}")
print(f"HODL Bank: {result.hodl_bank:,.0f}")
print(f"Liveliness: {result.liveliness:.3f}")
print(f"Confidence: {result.confidence:.2f}")

# Interpretation
if result.signal_zone == "STRONG_BUY":
    print("Historically strong buy zone!")
elif result.signal_zone == "DISTRIBUTION":
    print("Warning: Distribution pressure detected")
```

### Sell-side Risk Ratio

```python
from scripts.metrics.sell_side_risk import calculate_sell_side_risk

result = calculate_sell_side_risk(
    conn=conn,
    current_price_usd=100000.0,
    window_days=30,
    block_height=870000,
)

print(f"Sell-side Risk: {result.sell_side_risk_pct:.3f}%")
print(f"Signal zone: {result.signal_zone}")
print(f"Realized profit (30d): ${result.realized_profit_usd:,.0f}")
print(f"Net realized P&L: ${result.net_realized_pnl_usd:,.0f}")
print(f"UTXOs spent: {result.spent_utxos_in_window:,}")
```

### Coindays Destroyed (CDD/VDD)

```python
from scripts.metrics.coindays import calculate_coindays_destroyed

result = calculate_coindays_destroyed(
    conn=conn,
    current_price_usd=100000.0,
    window_days=30,
    block_height=870000,
)

print(f"CDD (30d): {result.cdd_total:,.0f}")
print(f"CDD daily avg: {result.cdd_daily_avg:,.0f}")
print(f"VDD Multiple: {result.vdd_multiple:.2f}x" if result.vdd_multiple else "N/A")
print(f"Avg UTXO age: {result.avg_utxo_age_days:.1f} days")
print(f"Signal zone: {result.signal_zone}")

if result.max_single_day_cdd > result.cdd_daily_avg * 3:
    print(f"Peak CDD spike on {result.max_single_day_date}: {result.max_single_day_cdd:,.0f}")
```

## API Usage

### Start the API server

```bash
cd /media/sam/1TB/UTXOracle
uv run uvicorn api.main:app --reload --port 8000
```

### API Endpoints

```bash
# URPD
curl "http://localhost:8000/api/metrics/urpd?bucket_size=5000&current_price=100000"

# Supply Profit/Loss
curl "http://localhost:8000/api/metrics/supply-profit-loss?current_price=100000"

# Reserve Risk
curl "http://localhost:8000/api/metrics/reserve-risk?current_price=100000"

# Sell-side Risk (30-day window)
curl "http://localhost:8000/api/metrics/sell-side-risk?window_days=30&current_price=100000"

# Coindays Destroyed
curl "http://localhost:8000/api/metrics/coindays?window_days=30&current_price=100000"
```

### Python API Client

```python
import httpx

BASE_URL = "http://localhost:8000"

async def get_all_metrics(current_price: float):
    async with httpx.AsyncClient() as client:
        # Fetch all metrics in parallel
        urpd = await client.get(f"{BASE_URL}/api/metrics/urpd", params={
            "bucket_size": 5000,
            "current_price": current_price
        })
        supply_pl = await client.get(f"{BASE_URL}/api/metrics/supply-profit-loss", params={
            "current_price": current_price
        })
        reserve = await client.get(f"{BASE_URL}/api/metrics/reserve-risk", params={
            "current_price": current_price
        })
        sell_side = await client.get(f"{BASE_URL}/api/metrics/sell-side-risk", params={
            "window_days": 30,
            "current_price": current_price
        })
        coindays = await client.get(f"{BASE_URL}/api/metrics/coindays", params={
            "window_days": 30,
            "current_price": current_price
        })

        return {
            "urpd": urpd.json(),
            "supply_profit_loss": supply_pl.json(),
            "reserve_risk": reserve.json(),
            "sell_side_risk": sell_side.json(),
            "coindays": coindays.json(),
        }
```

## Signal Interpretation

### Market Cycle Phases (Supply in Profit)

| % in Profit | Phase | Interpretation |
|-------------|-------|----------------|
| > 95% | EUPHORIA | Cycle top warning - consider de-risking |
| 80-95% | BULL | Bull market - maintain position |
| 50-80% | TRANSITION | Uncertainty - watch for direction |
| < 50% | CAPITULATION | Accumulation zone - DCA opportunity |

### Reserve Risk Zones

| Reserve Risk | Zone | Interpretation |
|--------------|------|----------------|
| < 0.002 | STRONG_BUY | Historically cycle bottoms |
| 0.002 - 0.008 | ACCUMULATION | Good entry opportunities |
| 0.008 - 0.02 | FAIR_VALUE | Fair market pricing |
| > 0.02 | DISTRIBUTION | Top warning - consider profit-taking |

### Sell-side Risk Zones

| Sell-side Risk | Zone | Interpretation |
|----------------|------|----------------|
| < 0.1% | LOW | Minimal selling - bullish |
| 0.1% - 0.3% | NORMAL | Normal profit-taking |
| 0.3% - 1.0% | ELEVATED | Increased distribution |
| > 1.0% | AGGRESSIVE | Heavy selling - top warning |

### VDD Multiple

| VDD Multiple | Zone | Interpretation |
|--------------|------|----------------|
| < 0.5 | LOW_ACTIVITY | Dormant network - accumulation |
| 0.5 - 1.5 | NORMAL | Normal activity levels |
| 1.5 - 2.0 | ELEVATED | Increased old money movement |
| > 2.0 | SPIKE | Significant LTH distribution |

## Integration with Monte Carlo Fusion

After implementation, add new metrics to fusion (in `monte_carlo_fusion.py`):

```python
ENHANCED_WEIGHTS = {
    # ... existing weights ...
    "urpd_signal": 0.02,       # Support/resistance proximity
    "supply_profit_vote": 0.02, # % in profit extremes
    "reserve_risk_vote": 0.02,  # LTH conviction
    "sell_side_vote": 0.02,     # Distribution pressure
}
```

## Testing

```bash
# Run tests for specific module
uv run pytest tests/test_urpd.py -v

# Run all spec-021 tests
uv run pytest tests/test_urpd.py tests/test_supply_profit_loss.py tests/test_reserve_risk.py tests/test_sell_side_risk.py tests/test_coindays.py -v

# With coverage
uv run pytest tests/test_urpd.py --cov=scripts/metrics/urpd --cov-report=term-missing
```

## Troubleshooting

### "No UTXOs found"

Ensure `utxo_lifecycle` table is populated:

```sql
SELECT COUNT(*) FROM utxo_lifecycle WHERE is_spent = FALSE;
-- Should return > 0
```

### Slow URPD calculation

Check index exists:

```sql
SELECT * FROM pg_indexes WHERE tablename = 'utxo_lifecycle';
-- Should see idx_utxo_is_spent
```

### Reserve Risk returns 0

Ensure cointime data is populated:

```python
from scripts.metrics.cointime import calculate_liveliness
# Should return value between 0 and 1
```
