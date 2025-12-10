# Quickstart: UTXO Lifecycle Engine

**Spec**: spec-017
**Time to First Snapshot**: ~2-3 days (initial sync)

---

## Prerequisites

- [ ] spec-016 complete (SOPR uses lifecycle data)
- [ ] Bitcoin Core synced and RPC accessible
- [ ] ~10GB free disk space
- [ ] Historical UTXOracle prices available

## Step 1: Create Module Structure (10 min)

```bash
touch scripts/metrics/utxo_lifecycle.py
touch scripts/metrics/realized_metrics.py
touch scripts/metrics/hodl_waves.py
touch tests/test_utxo_lifecycle.py

# Add to .env.example
cat >> .env.example << 'EOF'
# UTXO Lifecycle Configuration (spec-017)
UTXO_LIFECYCLE_ENABLED=true
UTXO_RETENTION_DAYS=180
UTXO_STH_THRESHOLD_DAYS=155
UTXO_PRUNING_ENABLED=true
UTXO_BATCH_SIZE=10000
EOF
```

## Step 2: Write First Test (RED) (15 min)

```python
# tests/test_utxo_lifecycle.py
import pytest
from scripts.metrics.utxo_lifecycle import UTXOLifecycle, process_block_utxos

def test_utxo_creation():
    """New UTXO should be tracked with creation data."""
    utxo = UTXOLifecycle(
        outpoint="abc123:0",
        txid="abc123",
        vout_index=0,
        creation_block=850000,
        creation_timestamp=datetime(2024, 1, 1),
        creation_price_usd=50000.0,
        btc_value=1.5
    )
    assert utxo.realized_value_usd == 75000.0
    assert utxo.is_spent == False

def test_utxo_spending():
    """Spent UTXO should have spending data and SOPR."""
    utxo = UTXOLifecycle(...)
    utxo.mark_spent(
        spent_block=860000,
        spent_timestamp=datetime(2024, 4, 1),
        spent_price_usd=100000.0,
        spending_txid="def456"
    )
    assert utxo.is_spent == True
    assert utxo.sopr == 2.0  # 100k/50k
```

Run: `uv run pytest tests/test_utxo_lifecycle.py -v` → Should **FAIL**

## Step 3: Implement Core Lifecycle (GREEN) (2 hours)

```python
# scripts/metrics/utxo_lifecycle.py
from dataclasses import dataclass, field
from datetime import datetime
import os

@dataclass
class UTXOLifecycle:
    outpoint: str
    txid: str
    vout_index: int
    creation_block: int
    creation_timestamp: datetime
    creation_price_usd: float
    btc_value: float

    # Computed
    realized_value_usd: float = field(init=False)
    is_spent: bool = False
    spent_block: int | None = None
    sopr: float | None = None

    def __post_init__(self):
        self.realized_value_usd = self.btc_value * self.creation_price_usd

    def mark_spent(
        self,
        spent_block: int,
        spent_timestamp: datetime,
        spent_price_usd: float,
        spending_txid: str
    ):
        self.is_spent = True
        self.spent_block = spent_block
        self.spent_timestamp = spent_timestamp
        self.spent_price_usd = spent_price_usd
        self.spending_txid = spending_txid
        if self.creation_price_usd > 0:
            self.sopr = spent_price_usd / self.creation_price_usd
```

Run: `uv run pytest tests/test_utxo_lifecycle.py -v` → Should **PASS**

## Step 4: Add Block Processing (1 hour)

```python
# scripts/metrics/utxo_lifecycle.py (add)

def process_block_utxos(
    block: dict,
    current_price: float,
    db_path: str
) -> tuple[int, int]:
    """
    Process all UTXOs in a block.
    Returns (created_count, spent_count)
    """
    created = 0
    spent = 0

    for tx in block["tx"]:
        # Track new UTXOs (outputs)
        for vout_idx, vout in enumerate(tx["vout"]):
            utxo = UTXOLifecycle(
                outpoint=f"{tx['txid']}:{vout_idx}",
                txid=tx["txid"],
                vout_index=vout_idx,
                creation_block=block["height"],
                creation_timestamp=datetime.fromtimestamp(block["time"]),
                creation_price_usd=current_price,
                btc_value=vout["value"]
            )
            save_utxo(utxo, db_path)
            created += 1

        # Mark spent UTXOs (inputs)
        for vin in tx.get("vin", []):
            if "txid" in vin:  # Skip coinbase
                outpoint = f"{vin['txid']}:{vin['vout']}"
                mark_utxo_spent(outpoint, block, current_price, tx["txid"], db_path)
                spent += 1

    return created, spent
```

## Step 5: Add Realized Metrics (1 hour)

```python
# scripts/metrics/realized_metrics.py

def calculate_realized_cap(db_path: str) -> float:
    """Sum of all unspent UTXO realized values."""
    conn = duckdb.connect(db_path)
    result = conn.execute("""
        SELECT SUM(realized_value_usd)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
    """).fetchone()
    return result[0] or 0.0

def calculate_mvrv(market_cap: float, realized_cap: float) -> float:
    """Market Value to Realized Value ratio."""
    if realized_cap == 0:
        return 0.0
    return market_cap / realized_cap

def calculate_nupl(market_cap: float, realized_cap: float) -> float:
    """Net Unrealized Profit/Loss."""
    if market_cap == 0:
        return 0.0
    return (market_cap - realized_cap) / market_cap
```

## Step 6: Initial Sync Script (30 min)

```bash
# Create sync script
cat > scripts/sync_utxo_lifecycle.py << 'EOF'
#!/usr/bin/env python3
"""Initial sync for UTXO lifecycle tracking."""

import sys
from datetime import datetime, timedelta

def main():
    # Start from 6 months ago
    start_block = get_block_at_date(datetime.now() - timedelta(days=180))
    current_block = get_current_block_height()

    print(f"Syncing blocks {start_block} to {current_block}")

    for block_height in range(start_block, current_block + 1):
        block = get_block(block_height)
        price = get_historical_price(block_height)
        created, spent = process_block_utxos(block, price, DB_PATH)
        print(f"Block {block_height}: +{created} UTXOs, -{spent} spent")

if __name__ == "__main__":
    main()
EOF
```

## Verification Checklist

- [ ] UTXOLifecycle dataclass works
- [ ] Block processing creates/spends UTXOs
- [ ] Realized Cap calculation correct
- [ ] MVRV calculation correct
- [ ] Initial sync completes
- [ ] All tests pass

## Next: Full Implementation

See `tasks.md` for complete task list.
