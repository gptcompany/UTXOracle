# Quickstart: STH/LTH Cost Basis (spec-023)

**Date**: 2025-12-16

## Overview

STH/LTH Cost Basis calculates the weighted average acquisition price for Short-Term Holders (STH) and Long-Term Holders (LTH), providing key support/resistance levels for market analysis.

## Prerequisites

- Python 3.11+
- DuckDB database with `utxo_lifecycle_full` VIEW populated
- UTXOracle environment configured

## Usage

### Python API

```python
from scripts.metrics.cost_basis import calculate_cost_basis_signal
import duckdb
from datetime import datetime

# Connect to database
conn = duckdb.connect("/path/to/utxo_lifecycle.duckdb")

# Calculate cost basis
result = calculate_cost_basis_signal(
    conn=conn,
    current_block=875000,
    current_price_usd=95000.0,
    timestamp=datetime.utcnow()
)

# Access results
print(f"STH Cost Basis: ${result.sth_cost_basis:,.2f}")
print(f"LTH Cost Basis: ${result.lth_cost_basis:,.2f}")
print(f"STH MVRV: {result.sth_mvrv:.2f}")
print(f"LTH MVRV: {result.lth_mvrv:.2f}")

# Signal interpretation
if result.sth_mvrv < 1.0:
    print("SIGNAL: STH underwater - Capitulation risk")
elif result.lth_mvrv > 3.0:
    print("SIGNAL: LTH deep in profit - Distribution risk")
```

### REST API

```bash
# Get cost basis metrics
curl http://localhost:8000/api/metrics/cost-basis
```

Response:
```json
{
    "sth_cost_basis": 65432.10,
    "lth_cost_basis": 28500.00,
    "total_cost_basis": 42150.75,
    "sth_mvrv": 1.45,
    "lth_mvrv": 3.32,
    "sth_supply_btc": 2500000.0,
    "lth_supply_btc": 17000000.0,
    "current_price_usd": 95000.0,
    "block_height": 875000,
    "timestamp": "2025-12-16T10:00:00Z",
    "confidence": 0.85
}
```

## Signal Interpretation

| Condition | Signal | Market Implication |
|-----------|--------|-------------------|
| Price < STH Cost Basis | STH underwater | Capitulation risk, potential bottom |
| Price > LTH Cost Basis | LTH in profit | Distribution risk, potential top |
| STH MVRV < 1.0 | Short-term loss | Weak hands exiting |
| LTH MVRV > 3.0 | Strong holder profit | Long-term holders may distribute |

## Testing

```bash
# Run unit tests
uv run pytest tests/test_cost_basis.py -v

# Run with coverage
uv run pytest tests/test_cost_basis.py --cov=scripts/metrics/cost_basis --cov-report=term-missing
```

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics/cost_basis.py` | Main calculator module |
| `scripts/models/metrics_models.py` | `CostBasisResult` dataclass |
| `api/main.py` | REST API endpoint |
| `tests/test_cost_basis.py` | TDD test suite |
