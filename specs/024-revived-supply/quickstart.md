# Quickstart: Revived Supply (spec-024)

**Date**: 2025-12-17

## Overview

Revived Supply tracks dormant coins being spent, signaling long-term holder behavior changes. When old coins suddenly move, it often indicates a shift in market sentiment.

## Prerequisites

- Python 3.11+
- DuckDB database with `utxo_lifecycle_full` VIEW populated
- UTXOracle environment configured

## Usage

### Python API

```python
from scripts.metrics.revived_supply import calculate_revived_supply_signal
import duckdb
from datetime import datetime

# Connect to database
conn = duckdb.connect("/path/to/utxo_lifecycle.duckdb")

# Calculate revived supply (default: 1-year dormancy, 30-day window)
result = calculate_revived_supply_signal(
    conn=conn,
    current_block=875000,
    current_price_usd=95000.0,
    timestamp=datetime.utcnow(),
    threshold_days=365,
    window_days=30
)

# Access results
print(f"Revived 1Y: {result.revived_1y:,.2f} BTC")
print(f"Revived 2Y: {result.revived_2y:,.2f} BTC")
print(f"Revived 5Y: {result.revived_5y:,.2f} BTC")
print(f"USD Value: ${result.revived_total_usd:,.2f}")
print(f"Avg Age: {result.revived_avg_age:.1f} days")
print(f"Zone: {result.zone.value}")

# Signal interpretation
if result.zone == RevivedZone.SPIKE:
    print("SIGNAL: Major distribution event - LTH selling pressure")
elif result.zone == RevivedZone.ELEVATED:
    print("SIGNAL: Increased LTH activity - Watch for trend")
```

### REST API

```bash
# Get revived supply metrics (default parameters)
curl http://localhost:8000/api/metrics/revived-supply

# With custom threshold and window
curl "http://localhost:8000/api/metrics/revived-supply?threshold=730&window=7"
```

Response:
```json
{
    "revived_1y": 5432.50,
    "revived_2y": 1234.75,
    "revived_5y": 567.25,
    "revived_total_usd": 516087500.00,
    "revived_avg_age": 892.5,
    "zone": "elevated",
    "utxo_count": 15234,
    "window_days": 30,
    "current_price_usd": 95000.0,
    "block_height": 875000,
    "timestamp": "2025-12-17T10:00:00Z",
    "confidence": 0.85
}
```

## Signal Interpretation

| Zone | Revived/Day | Market Implication |
|------|-------------|-------------------|
| DORMANT | < 1000 BTC | Low LTH activity, stable holding |
| NORMAL | 1000-5000 BTC | Baseline movement, neutral |
| ELEVATED | 5000-10000 BTC | Increased LTH selling, watch closely |
| SPIKE | > 10000 BTC | Major distribution, potential top signal |

### Key Insights

- **Rising revived supply during rally**: LTH distributing to late buyers (bearish)
- **Low revived supply during dip**: LTH holding strong (bullish conviction)
- **5Y+ coins moving**: Extremely rare, significant holder behavior shift
- **Sustained elevated zone**: Distribution phase, potential trend reversal

## Testing

```bash
# Run unit tests
uv run pytest tests/test_revived_supply.py -v

# Run with coverage
uv run pytest tests/test_revived_supply.py --cov=scripts/metrics/revived_supply --cov-report=term-missing
```

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics/revived_supply.py` | Main calculator module |
| `scripts/models/metrics_models.py` | `RevivedZone` enum + `RevivedSupplyResult` dataclass |
| `api/main.py` | REST API endpoint |
| `tests/test_revived_supply.py` | TDD test suite |
