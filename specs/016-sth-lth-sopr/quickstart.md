# Quickstart: STH/LTH SOPR Implementation

**Spec**: spec-016
**Time to First Signal**: ~4 hours

---

## Prerequisites

- [ ] spec-010 complete (Wasserstein integration)
- [ ] Historical UTXOracle prices in DuckDB
- [ ] Bitcoin Core RPC accessible

## Step 1: Create Module Structure (10 min)

```bash
# Create files
touch scripts/metrics/sopr.py
touch tests/test_sopr.py

# Add to .env.example
cat >> .env.example << 'EOF'
# SOPR Configuration (spec-016)
SOPR_ENABLED=true
SOPR_STH_THRESHOLD_DAYS=155
SOPR_MIN_OUTPUTS=100
SOPR_CAPITULATION_DAYS=3
SOPR_WEIGHT=0.15
EOF
```

## Step 2: Write First Test (RED) (20 min)

```python
# tests/test_sopr.py
import pytest
from scripts.metrics.sopr import SpentOutputSOPR, calculate_output_sopr

def test_sopr_calculation_profit():
    """SOPR > 1 when sold at profit."""
    result = calculate_output_sopr(
        creation_price=50000.0,
        spend_price=100000.0,
        btc_value=1.0,
        age_days=30
    )
    assert result.sopr == 2.0
    assert result.profit_loss == "PROFIT"
    assert result.cohort == "STH"

def test_sopr_calculation_loss():
    """SOPR < 1 when sold at loss."""
    result = calculate_output_sopr(
        creation_price=100000.0,
        spend_price=50000.0,
        btc_value=1.0,
        age_days=30
    )
    assert result.sopr == 0.5
    assert result.profit_loss == "LOSS"

def test_lth_classification():
    """Output > 155 days classified as LTH."""
    result = calculate_output_sopr(
        creation_price=50000.0,
        spend_price=100000.0,
        btc_value=1.0,
        age_days=200
    )
    assert result.cohort == "LTH"
```

Run: `uv run pytest tests/test_sopr.py -v` → Should **FAIL** (RED)

## Step 3: Implement Core SOPR (GREEN) (1 hour)

```python
# scripts/metrics/sopr.py
from dataclasses import dataclass
from datetime import datetime
import os

@dataclass
class SpentOutputSOPR:
    creation_price: float
    spend_price: float
    btc_value: float
    age_days: int
    sopr: float = 0.0
    cohort: str = ""
    profit_loss: str = ""
    is_valid: bool = False

    def __post_init__(self):
        if self.creation_price > 0 and self.spend_price > 0:
            self.sopr = self.spend_price / self.creation_price
            self.is_valid = True

        sth_threshold = int(os.getenv("SOPR_STH_THRESHOLD_DAYS", "155"))
        self.cohort = "STH" if self.age_days < sth_threshold else "LTH"

        if self.sopr > 1.01:
            self.profit_loss = "PROFIT"
        elif self.sopr < 0.99:
            self.profit_loss = "LOSS"
        else:
            self.profit_loss = "BREAKEVEN"

def calculate_output_sopr(
    creation_price: float,
    spend_price: float,
    btc_value: float,
    age_days: int
) -> SpentOutputSOPR:
    """Calculate SOPR for a single spent output."""
    return SpentOutputSOPR(
        creation_price=creation_price,
        spend_price=spend_price,
        btc_value=btc_value,
        age_days=age_days
    )
```

Run: `uv run pytest tests/test_sopr.py -v` → Should **PASS** (GREEN)

## Step 4: Add Price Lookup (1 hour)

```python
# scripts/metrics/sopr.py (add)

def get_historical_price(block_height: int, db_path: str) -> float | None:
    """Get UTXOracle price for a block."""
    import duckdb
    conn = duckdb.connect(db_path)
    result = conn.execute(
        "SELECT price_usd FROM utxoracle_prices WHERE block_height = ?",
        [block_height]
    ).fetchone()
    return result[0] if result else None

def get_utxo_creation_block(txid: str, vout: int, rpc) -> int | None:
    """Get block height where UTXO was created."""
    try:
        tx = rpc.getrawtransaction(txid, True)
        block_hash = tx.get("blockhash")
        if block_hash:
            block = rpc.getblock(block_hash)
            return block["height"]
    except Exception:
        pass
    return None
```

## Step 5: Add Block Aggregation (1 hour)

```python
# scripts/metrics/sopr.py (add)

@dataclass
class BlockSOPR:
    block_height: int
    aggregate_sopr: float
    sth_sopr: float | None
    lth_sopr: float | None
    valid_outputs: int
    is_valid: bool

def calculate_block_sopr(
    outputs: list[SpentOutputSOPR],
    block_height: int,
    min_samples: int = 100
) -> BlockSOPR:
    """Aggregate outputs into block SOPR."""
    valid = [o for o in outputs if o.is_valid]
    sth = [o for o in valid if o.cohort == "STH"]
    lth = [o for o in valid if o.cohort == "LTH"]

    def weighted_avg(outs):
        if not outs:
            return None
        total = sum(o.btc_value for o in outs)
        return sum(o.sopr * o.btc_value for o in outs) / total if total else None

    return BlockSOPR(
        block_height=block_height,
        aggregate_sopr=weighted_avg(valid) or 0.0,
        sth_sopr=weighted_avg(sth),
        lth_sopr=weighted_avg(lth),
        valid_outputs=len(valid),
        is_valid=len(valid) >= min_samples
    )
```

## Step 6: Add Signal Detection (30 min)

```python
# scripts/metrics/sopr.py (add)

def detect_sopr_signals(
    window: list[BlockSOPR],
    capitulation_days: int = 3
) -> dict:
    """Detect SOPR patterns."""
    signals = {
        "sth_capitulation": False,
        "sth_breakeven_cross": False,
        "lth_distribution": False,
        "sopr_vote": 0.0
    }

    # Check for STH capitulation
    recent_sth = [b.sth_sopr for b in window[-capitulation_days:] if b.sth_sopr]
    if len(recent_sth) >= capitulation_days and all(s < 1.0 for s in recent_sth):
        signals["sth_capitulation"] = True
        signals["sopr_vote"] = 0.7  # Bullish

    # Check for LTH distribution
    recent_lth = [b.lth_sopr for b in window[-7:] if b.lth_sopr]
    if recent_lth and max(recent_lth) > 3.0:
        signals["lth_distribution"] = True
        signals["sopr_vote"] = -0.7  # Bearish

    return signals
```

## Step 7: Integrate with Fusion (30 min)

```python
# scripts/metrics/monte_carlo_fusion.py (modify)

# Add to EVIDENCE_BASED_WEIGHTS:
"sopr": 0.15,  # NEW - Grade A-B evidence (82.44% accuracy)

# In enhanced_monte_carlo_fusion():
if "sopr" in components and components["sopr"] is not None:
    votes["sopr"] = components["sopr"]
```

## Step 8: Run Full Test Suite

```bash
uv run pytest tests/test_sopr.py -v
uv run pytest tests/ -v --tb=short
```

## Verification Checklist

- [ ] `calculate_output_sopr()` works
- [ ] `calculate_block_sopr()` aggregates correctly
- [ ] STH/LTH split at 155 days
- [ ] Signal detection identifies patterns
- [ ] Fusion integration complete
- [ ] All tests pass

## Next: Full Implementation

See `tasks.md` for complete task list.
