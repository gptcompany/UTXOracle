# Quickstart: Cointime Economics

**Spec**: spec-018
**Time to First AVIV**: ~1 hour (after spec-017)

---

## Prerequisites

- [ ] spec-017 complete (UTXO Lifecycle)
- [ ] UTXO lifecycle data populated

## Step 1: Create Module (5 min)

```bash
touch scripts/metrics/cointime.py
touch tests/test_cointime.py

cat >> .env.example << 'EOF'
# Cointime Configuration (spec-018)
COINTIME_ENABLED=true
COINTIME_WEIGHT=0.12
COINTIME_AVIV_UNDERVALUED=1.0
COINTIME_AVIV_OVERVALUED=2.5
EOF
```

## Step 2: Write Tests (RED) (15 min)

```python
# tests/test_cointime.py
import pytest
from scripts.metrics.cointime import (
    calculate_coinblocks_destroyed,
    calculate_liveliness,
    calculate_aviv
)

def test_coinblocks_destroyed():
    """Coinblocks = BTC × age_blocks."""
    result = calculate_coinblocks_destroyed(
        btc_value=1.5,
        age_blocks=100
    )
    assert result == 150.0

def test_liveliness():
    """Liveliness = destroyed / created."""
    result = calculate_liveliness(
        cumulative_destroyed=3_000_000_000,
        cumulative_created=10_000_000_000
    )
    assert result == 0.3

def test_aviv_undervalued():
    """AVIV < 1 indicates undervaluation."""
    result = calculate_aviv(
        current_price=50000,
        true_market_mean=80000
    )
    assert result < 1.0
    assert result == 0.625
```

Run: `uv run pytest tests/test_cointime.py -v` → **FAIL**

## Step 3: Implement Core (GREEN) (30 min)

```python
# scripts/metrics/cointime.py
from dataclasses import dataclass
from datetime import datetime

def calculate_coinblocks_destroyed(
    btc_value: float,
    age_blocks: int
) -> float:
    """Calculate coinblocks destroyed when UTXO spent."""
    return btc_value * age_blocks

def calculate_liveliness(
    cumulative_destroyed: float,
    cumulative_created: float
) -> float:
    """Calculate network liveliness ratio."""
    if cumulative_created == 0:
        return 0.0
    return cumulative_destroyed / cumulative_created

def calculate_vaultedness(liveliness: float) -> float:
    """Calculate network vaultedness (inverse of liveliness)."""
    return 1.0 - liveliness

def calculate_active_supply(
    total_supply: float,
    liveliness: float
) -> float:
    """Calculate activity-weighted supply."""
    return total_supply * liveliness

def calculate_true_market_mean(
    market_cap: float,
    active_supply: float
) -> float:
    """Calculate True Market Mean price."""
    if active_supply == 0:
        return 0.0
    return market_cap / active_supply

def calculate_aviv(
    current_price: float,
    true_market_mean: float
) -> float:
    """Calculate AVIV ratio (activity-adjusted MVRV)."""
    if true_market_mean == 0:
        return 0.0
    return current_price / true_market_mean
```

Run: `uv run pytest tests/test_cointime.py -v` → **PASS**

## Step 4: Process Block (20 min)

```python
# scripts/metrics/cointime.py (add)

def process_block_cointime(
    block_height: int,
    spent_utxos: list[UTXOLifecycle],
    cumulative_created: float,
    cumulative_destroyed: float,
    total_supply: float,
    current_price: float,
    db_path: str
) -> CoinblocksMetrics:
    """Process one block for Cointime metrics."""

    # Calculate destroyed this block
    block_destroyed = sum(
        calculate_coinblocks_destroyed(u.btc_value, u.age_blocks)
        for u in spent_utxos
    )

    # Created this block = total BTC in new outputs × 1
    block_created = sum(u.btc_value for u in new_utxos)

    # Update cumulative
    cumulative_created += block_created
    cumulative_destroyed += block_destroyed

    # Calculate derived metrics
    liveliness = calculate_liveliness(cumulative_destroyed, cumulative_created)
    active_supply = calculate_active_supply(total_supply, liveliness)
    market_cap = total_supply * current_price
    tmm = calculate_true_market_mean(market_cap, active_supply)
    aviv = calculate_aviv(current_price, tmm)

    return CoinblocksMetrics(
        block_height=block_height,
        coinblocks_created=block_created,
        coinblocks_destroyed=block_destroyed,
        cumulative_created=cumulative_created,
        cumulative_destroyed=cumulative_destroyed,
        liveliness=liveliness,
        vaultedness=1 - liveliness,
        active_supply_btc=active_supply,
        true_market_mean_usd=tmm,
        aviv_ratio=aviv
    )
```

## Verification

- [ ] Coinblocks calculation correct
- [ ] Liveliness in range [0, 1]
- [ ] AVIV ratio calculated
- [ ] All tests pass

## Next: Full Implementation

See `tasks.md` for complete task list.
