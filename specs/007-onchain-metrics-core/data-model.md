# Data Model: On-Chain Metrics Core

**Feature**: 007-onchain-metrics-core
**Date**: 2025-12-03
**Status**: Complete

## Entity Relationship Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         price_history                             │
│  (existing table - NOT modified)                                  │
├──────────────────────────────────────────────────────────────────┤
│  id: INTEGER PK                                                   │
│  timestamp: TIMESTAMP UNIQUE                                      │
│  utxoracle_price: DOUBLE                                         │
│  exchange_price: DOUBLE                                          │
│  confidence: DOUBLE                                              │
│  ...                                                             │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ timestamp (FK-like, same granularity)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                           metrics                                 │
│  (NEW table)                                                      │
├──────────────────────────────────────────────────────────────────┤
│  id: INTEGER PK                                                   │
│  timestamp: TIMESTAMP UNIQUE                                      │
│                                                                   │
│  ┌─ Monte Carlo Fusion ─────────────────────────────────────────┐│
│  │  signal_mean: DOUBLE                                         ││
│  │  signal_std: DOUBLE                                          ││
│  │  ci_lower: DOUBLE                                            ││
│  │  ci_upper: DOUBLE                                            ││
│  │  action: VARCHAR(10)  -- BUY/SELL/HOLD                       ││
│  │  action_confidence: DOUBLE                                    ││
│  │  n_samples: INTEGER DEFAULT 1000                             ││
│  │  distribution_type: VARCHAR(20)  -- unimodal/bimodal         ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌─ Active Addresses ───────────────────────────────────────────┐│
│  │  block_height: INTEGER                                        ││
│  │  active_addresses_block: INTEGER                              ││
│  │  active_addresses_24h: INTEGER                                ││
│  │  unique_senders: INTEGER                                      ││
│  │  unique_receivers: INTEGER                                    ││
│  │  is_anomaly: BOOLEAN DEFAULT FALSE                           ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌─ TX Volume ──────────────────────────────────────────────────┐│
│  │  tx_count: INTEGER                                            ││
│  │  tx_volume_btc: DOUBLE                                        ││
│  │  tx_volume_usd: DOUBLE  -- NULL if price unavailable         ││
│  │  utxoracle_price_used: DOUBLE                                 ││
│  │  low_confidence: BOOLEAN DEFAULT FALSE                        ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP                  │
└──────────────────────────────────────────────────────────────────┘
```

## Python Data Models

### Location: `scripts/models/metrics_models.py`

```python
"""
Data models for on-chain metrics (spec-007).

These dataclasses mirror the DuckDB `metrics` table schema and provide
type-safe data transfer between calculation modules and storage/API.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal


@dataclass
class MonteCarloFusionResult:
    """
    Result of Monte Carlo bootstrap signal fusion.

    Upgrades linear fusion (0.7*whale + 0.3*utxo) to probabilistic
    estimation with confidence intervals.

    Attributes:
        signal_mean: Mean of bootstrap samples (-1.0 to 1.0)
        signal_std: Standard deviation of samples
        ci_lower: 95% confidence interval lower bound
        ci_upper: 95% confidence interval upper bound
        action: Trading action derived from signal (BUY/SELL/HOLD)
        action_confidence: Probability that action is correct (0.0 to 1.0)
        n_samples: Number of bootstrap iterations performed
        distribution_type: Shape of distribution (unimodal/bimodal)
    """
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: Literal["BUY", "SELL", "HOLD"]
    action_confidence: float
    n_samples: int = 1000
    distribution_type: Literal["unimodal", "bimodal", "insufficient_data"] = "unimodal"

    def __post_init__(self):
        """Validate signal bounds."""
        assert -1.0 <= self.signal_mean <= 1.0, f"signal_mean out of range: {self.signal_mean}"
        assert 0.0 <= self.action_confidence <= 1.0, f"action_confidence out of range: {self.action_confidence}"


@dataclass
class ActiveAddressesMetric:
    """
    Active address count for a block or time period.

    Counts unique addresses participating in transactions as either
    senders (inputs) or receivers (outputs).

    Attributes:
        timestamp: When metric was calculated
        block_height: Bitcoin block height (if single block)
        active_addresses_block: Unique addresses in single block
        active_addresses_24h: Unique addresses in last 24 hours (deduplicated)
        unique_senders: Unique addresses in transaction inputs
        unique_receivers: Unique addresses in transaction outputs
        is_anomaly: True if count > 3σ from 30-day moving average
    """
    timestamp: datetime
    block_height: int
    active_addresses_block: int
    active_addresses_24h: Optional[int] = None  # Requires multi-block aggregation
    unique_senders: int = 0
    unique_receivers: int = 0
    is_anomaly: bool = False

    def __post_init__(self):
        """Validate non-negative counts."""
        assert self.active_addresses_block >= 0
        assert self.unique_senders >= 0
        assert self.unique_receivers >= 0


@dataclass
class TxVolumeMetric:
    """
    Transaction volume metric using UTXOracle price.

    Calculates total BTC transferred and converts to USD using
    on-chain price (not exchange price) for privacy preservation.

    Attributes:
        timestamp: When metric was calculated
        tx_count: Number of transactions in period
        tx_volume_btc: Total BTC transferred (adjusted for change)
        tx_volume_usd: USD equivalent (None if price unavailable)
        utxoracle_price_used: Price used for BTC→USD conversion
        low_confidence: True if UTXOracle confidence < 0.3
    """
    timestamp: datetime
    tx_count: int
    tx_volume_btc: float
    tx_volume_usd: Optional[float] = None
    utxoracle_price_used: Optional[float] = None
    low_confidence: bool = False

    def __post_init__(self):
        """Validate non-negative values."""
        assert self.tx_count >= 0
        assert self.tx_volume_btc >= 0
        if self.tx_volume_usd is not None:
            assert self.tx_volume_usd >= 0


@dataclass
class OnChainMetricsBundle:
    """
    Combined metrics for a single timestamp.

    Used for API response and DuckDB storage. All three metrics
    are calculated together during daily_analysis.py run.

    Attributes:
        timestamp: Common timestamp for all metrics
        monte_carlo: Signal fusion result (may be None if whale data unavailable)
        active_addresses: Address activity metric
        tx_volume: Transaction volume metric
    """
    timestamp: datetime
    monte_carlo: Optional[MonteCarloFusionResult] = None
    active_addresses: Optional[ActiveAddressesMetric] = None
    tx_volume: Optional[TxVolumeMetric] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"timestamp": self.timestamp.isoformat()}

        if self.monte_carlo:
            result["monte_carlo"] = {
                "signal_mean": self.monte_carlo.signal_mean,
                "signal_std": self.monte_carlo.signal_std,
                "ci_lower": self.monte_carlo.ci_lower,
                "ci_upper": self.monte_carlo.ci_upper,
                "action": self.monte_carlo.action,
                "action_confidence": self.monte_carlo.action_confidence,
                "n_samples": self.monte_carlo.n_samples,
                "distribution_type": self.monte_carlo.distribution_type,
            }

        if self.active_addresses:
            result["active_addresses"] = {
                "block_height": self.active_addresses.block_height,
                "active_addresses_block": self.active_addresses.active_addresses_block,
                "active_addresses_24h": self.active_addresses.active_addresses_24h,
                "unique_senders": self.active_addresses.unique_senders,
                "unique_receivers": self.active_addresses.unique_receivers,
                "is_anomaly": self.active_addresses.is_anomaly,
            }

        if self.tx_volume:
            result["tx_volume"] = {
                "tx_count": self.tx_volume.tx_count,
                "tx_volume_btc": self.tx_volume.tx_volume_btc,
                "tx_volume_usd": self.tx_volume.tx_volume_usd,
                "utxoracle_price_used": self.tx_volume.utxoracle_price_used,
                "low_confidence": self.tx_volume.low_confidence,
            }

        return result
```

## DuckDB Schema

### Location: `scripts/init_metrics_db.py`

```sql
-- On-Chain Metrics table (spec-007)
-- Stores Monte Carlo fusion, Active Addresses, and TX Volume metrics

CREATE TABLE IF NOT EXISTS metrics (
    -- Primary key
    id INTEGER PRIMARY KEY,

    -- Timestamp (matches price_history granularity)
    timestamp TIMESTAMP NOT NULL UNIQUE,

    -- Monte Carlo Fusion (FR-001, FR-002)
    signal_mean DOUBLE,
    signal_std DOUBLE,
    ci_lower DOUBLE,
    ci_upper DOUBLE,
    action VARCHAR(10) CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    action_confidence DOUBLE CHECK (action_confidence >= 0 AND action_confidence <= 1),
    n_samples INTEGER DEFAULT 1000,
    distribution_type VARCHAR(20) CHECK (distribution_type IN ('unimodal', 'bimodal', 'insufficient_data')),

    -- Active Addresses (FR-003, FR-004)
    block_height INTEGER,
    active_addresses_block INTEGER CHECK (active_addresses_block >= 0),
    active_addresses_24h INTEGER CHECK (active_addresses_24h >= 0),
    unique_senders INTEGER CHECK (unique_senders >= 0),
    unique_receivers INTEGER CHECK (unique_receivers >= 0),
    is_anomaly BOOLEAN DEFAULT FALSE,

    -- TX Volume (FR-005, FR-006)
    tx_count INTEGER CHECK (tx_count >= 0),
    tx_volume_btc DOUBLE CHECK (tx_volume_btc >= 0),
    tx_volume_usd DOUBLE CHECK (tx_volume_usd >= 0 OR tx_volume_usd IS NULL),
    utxoracle_price_used DOUBLE,
    low_confidence BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp DESC);

-- Index for action filtering (find all BUY signals)
CREATE INDEX IF NOT EXISTS idx_metrics_action ON metrics(action);

-- Index for anomaly detection queries
CREATE INDEX IF NOT EXISTS idx_metrics_anomaly ON metrics(is_anomaly) WHERE is_anomaly = TRUE;
```

## Validation Rules

### From Functional Requirements

| Field | Rule | Source |
|-------|------|--------|
| `signal_mean` | -1.0 ≤ x ≤ 1.0 | FR-002 |
| `action_confidence` | 0.0 ≤ x ≤ 1.0 | FR-002 |
| `action` | IN ('BUY', 'SELL', 'HOLD') | FR-002 |
| `n_samples` | Default 1000, configurable | FR-001 |
| `active_addresses_*` | ≥ 0 | FR-003 |
| `tx_volume_usd` | NULL if price unavailable | FR-005, FR-006 |
| `low_confidence` | TRUE if UTXOracle confidence < 0.3 | FR-006 |

### State Transitions

**Monte Carlo Action**:
```
signal_mean > 0.5  → action = "BUY"
signal_mean < -0.5 → action = "SELL"
otherwise          → action = "HOLD"
```

**Anomaly Detection**:
```
IF active_addresses_block > (30_day_ma + 3 * 30_day_std):
    is_anomaly = TRUE
```

## Migration Notes

1. **No breaking changes**: Existing `price_history` table unchanged
2. **Additive only**: New `metrics` table can be added without downtime
3. **Backfill strategy**: Historical metrics can be calculated later (out of scope for MVP)
4. **JOIN pattern**: `SELECT * FROM price_history p JOIN metrics m ON p.timestamp = m.timestamp`
