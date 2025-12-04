# Quickstart: Derivatives Historical Integration

**Feature**: 008-derivatives-historical
**Prerequisites**: spec-007 (On-Chain Metrics Core) complete

## Overview

This guide covers integrating Binance Futures historical data (Funding Rates, Open Interest) into UTXOracle's signal fusion using DuckDB cross-database queries.

## Prerequisites

### 1. LiquidationHeatmap Database

Ensure LiquidationHeatmap DuckDB is accessible:

```bash
# Check database exists
ls -la /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb

# Verify data (from LiquidationHeatmap project)
cd /media/sam/1TB/LiquidationHeatmap
uv run python -c "
import duckdb
conn = duckdb.connect('data/processed/liquidations.duckdb', read_only=True)
print('Funding rates:', conn.execute('SELECT COUNT(*) FROM funding_rate_history').fetchone()[0])
print('OI records:', conn.execute('SELECT COUNT(*) FROM open_interest_history').fetchone()[0])
conn.close()
"
```

Expected output:
```
Funding rates: 4119
OI records: 417460
```

### 2. Environment Configuration

Add to `.env`:

```bash
# Derivatives Integration
LIQUIDATION_HEATMAP_DB_PATH=/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb
DERIVATIVES_ENABLED=true

# Signal Weights (optional - uses defaults if not set)
FUNDING_WEIGHT=0.25
OI_WEIGHT=0.15
OI_CHANGE_WINDOW_HOURS=1
```

### 3. Verify spec-007 is Complete

```bash
# Run spec-007 tests
cd /media/sam/1TB/UTXOracle
uv run pytest tests/test_onchain_metrics.py -v
```

All tests should pass.

## Quick Test

### Test Cross-Database Query

```python
# test_crossdb.py
import duckdb
from pathlib import Path

# Connect to UTXOracle cache
utxo_db = duckdb.connect()

# Attach LiquidationHeatmap (READ_ONLY)
liq_path = "/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb"
utxo_db.execute(f"ATTACH '{liq_path}' AS liq (READ_ONLY)")

# Query funding rates
result = utxo_db.execute("""
    SELECT timestamp, funding_rate
    FROM liq.funding_rate_history
    WHERE symbol = 'BTCUSDT'
    ORDER BY timestamp DESC
    LIMIT 5
""").fetchall()

print("Latest 5 funding rates:")
for row in result:
    print(f"  {row[0]} | {float(row[1])*100:.4f}%")

utxo_db.close()
```

Run:
```bash
uv run python test_crossdb.py
```

Expected output:
```
Latest 5 funding rates:
  2025-08-31 17:00:00.001000 | 0.0100%
  2025-08-31 09:00:00 | 0.0047%
  2025-08-31 01:00:00.016000 | -0.0012%
  2025-08-30 17:00:00.003000 | 0.0080%
  2025-08-30 09:00:00.002000 | 0.0080%
```

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b 008-derivatives-historical
```

### 2. Project Structure

After implementation, the new files will be:

```
scripts/
├── derivatives/
│   ├── __init__.py              # Module init
│   ├── funding_rate_reader.py   # US1: Read + convert funding
│   ├── oi_reader.py             # US2: Read + calculate OI change
│   └── enhanced_fusion.py       # US3: 4-component Monte Carlo
├── backtest_derivatives.py      # US4: Historical validation
└── models/
    └── derivatives_models.py    # New dataclasses

tests/
├── test_derivatives_integration.py  # Unit tests
└── integration/
    └── test_derivatives_e2e.py      # E2E with real DB
```

### 3. TDD Cycle

Follow Red-Green-Refactor for each user story:

**US1: Funding Rate** (start here - simplest)
```bash
# RED: Write failing test
uv run pytest tests/test_derivatives_integration.py::TestFundingRateReader -v

# GREEN: Implement funding_rate_reader.py
# ... edit code ...

# Verify pass
uv run pytest tests/test_derivatives_integration.py::TestFundingRateReader -v
```

**US2: Open Interest**
```bash
uv run pytest tests/test_derivatives_integration.py::TestOpenInterestReader -v
```

**US3: Enhanced Fusion**
```bash
uv run pytest tests/test_derivatives_integration.py::TestEnhancedFusion -v
```

**US4: Backtest**
```bash
uv run pytest tests/test_derivatives_integration.py::TestBacktest -v
```

### 4. Run All Tests

```bash
# All derivatives tests
uv run pytest tests/test_derivatives_integration.py -v

# With coverage
uv run pytest tests/test_derivatives_integration.py --cov=scripts/derivatives --cov-report=term-missing

# Target: ≥80% coverage
```

## API Usage (After Implementation)

### Get Enhanced Fusion Signal

```bash
# Start API server
uv run uvicorn api.main:app --reload

# Query enhanced metrics (includes derivatives)
curl http://localhost:8000/api/metrics/latest | jq
```

Expected response structure:
```json
{
  "timestamp": "2025-12-03T12:00:00Z",
  "monte_carlo": {
    "signal_mean": 0.65,
    "signal_std": 0.12,
    "action": "BUY",
    "action_confidence": 0.78,
    "components": {
      "whale": {"vote": 0.8, "weight": 0.40},
      "utxo": {"vote": 0.6, "weight": 0.20},
      "funding": {"vote": 0.5, "weight": 0.25},
      "oi": {"vote": 0.4, "weight": 0.15}
    },
    "derivatives_available": true
  }
}
```

### Run Backtest

```bash
# Run backtest script
uv run python scripts/backtest_derivatives.py \
  --start 2025-10-01 \
  --end 2025-10-31 \
  --optimize
```

Expected output:
```
Backtest Results (2025-10-01 to 2025-10-31)
============================================
Total Signals: 744
  BUY:  312 (42%)
  SELL: 198 (27%)
  HOLD: 234 (31%)

Performance:
  Win Rate:     62.3%
  Total Return: +8.5%
  Sharpe Ratio: 1.42
  Max Drawdown: -3.4%

Optimal Weights (if --optimize):
  whale:   0.35
  utxo:    0.25
  funding: 0.25
  oi:      0.15
```

## Graceful Degradation Testing

Test system behavior when LiquidationHeatmap is unavailable:

```bash
# Temporarily rename DB to simulate unavailability
mv /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb \
   /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb.bak

# Query API - should return degraded response
curl http://localhost:8000/api/metrics/latest | jq

# Expected: derivatives_available: false, uses 2-component fusion

# Restore DB
mv /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb.bak \
   /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb
```

## Common Issues

### DuckDB Lock Error

**Error**: `IO Error: Could not set lock on file`

**Solution**: Use `READ_ONLY` mode when attaching:
```python
conn.execute(f"ATTACH '{path}' AS liq (READ_ONLY)")
```

### Funding Rate Out of Range

**Error**: `funding_vote out of range`

**Solution**: Check normalization thresholds in `funding_rate_reader.py`:
```python
# Extreme thresholds
EXTREME_POSITIVE = 0.001  # 0.1%
EXTREME_NEGATIVE = -0.0005  # -0.05%
```

### OI Data Missing

**Error**: `No OI data for timestamp`

**Solution**: OI is 5-minute intervals. Use nearest timestamp within tolerance:
```python
# Query with 10-minute tolerance
WHERE timestamp BETWEEN (? - INTERVAL '10 minutes') AND (? + INTERVAL '10 minutes')
```

## Next Steps

After completing spec-008:

1. **Validate backtest results** - Ensure win rate >55%
2. **Monitor production** - Check data freshness logs
3. **Plan spec-009** - Real-time derivatives WebSocket

## Reference

- [spec.md](./spec.md) - Full feature specification
- [research.md](./research.md) - Technical decisions
- [data-model.md](./data-model.md) - Entity definitions
- [contracts/](./contracts/) - API schemas
