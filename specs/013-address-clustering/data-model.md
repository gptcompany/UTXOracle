# Data Model: Address Clustering & CoinJoin Detection

**Feature**: spec-013 | **Date**: 2025-12-04

## Entities

### AddressCluster

```python
@dataclass
class AddressCluster:
    cluster_id: str
    addresses: set[str]
    total_balance: float
    tx_count: int
    first_seen: datetime
    last_seen: datetime
    is_exchange_likely: bool
    label: str | None
```

### CoinJoinResult

```python
@dataclass
class CoinJoinResult:
    txid: str
    is_coinjoin: bool
    confidence: float
    coinjoin_type: str | None   # "wasabi" | "joinmarket" | "whirlpool" | "generic"
    equal_output_count: int
    total_inputs: int
    total_outputs: int
    detection_reasons: list[str]
```

### ChangeDetectionResult

```python
@dataclass
class ChangeDetectionResult:
    txid: str
    outputs: list[dict]
    likely_payment_outputs: list[int]
    likely_change_outputs: list[int]
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS address_clusters (
    address VARCHAR PRIMARY KEY,
    cluster_id VARCHAR NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    is_exchange_likely BOOLEAN DEFAULT FALSE,
    label VARCHAR
);

CREATE TABLE IF NOT EXISTS coinjoin_cache (
    txid VARCHAR PRIMARY KEY,
    is_coinjoin BOOLEAN NOT NULL,
    confidence DOUBLE,
    coinjoin_type VARCHAR,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cluster_id ON address_clusters(cluster_id);
```
