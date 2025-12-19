# Data Model: Net Realized Profit/Loss (spec-028)

## Overview

Data models for the Net Realized P/L metric. Follows existing patterns in `scripts/models/metrics_models.py`.

---

## Entities

### NetRealizedPnLResult

Primary result dataclass for Net Realized P/L calculations.

```python
@dataclass
class NetRealizedPnLResult:
    """
    Net Realized Profit/Loss metric result.

    Aggregates realized gains/losses from spent UTXOs to show actual
    capital flows during the specified time window.

    Attributes:
        realized_profit_usd: Total profit realized (USD) from profitable UTXOs
        realized_loss_usd: Total loss realized (USD) from unprofitable UTXOs
        net_realized_pnl_usd: Net P/L = profit - loss
        realized_profit_btc: Profit in BTC terms (for reference)
        realized_loss_btc: Loss in BTC terms (for reference)
        net_realized_pnl_btc: Net P/L in BTC terms
        profit_utxo_count: Number of UTXOs spent at profit
        loss_utxo_count: Number of UTXOs spent at loss
        profit_loss_ratio: Profit/Loss ratio (> 1 = profit dominant)
        signal: Interpretation (PROFIT_DOMINANT, LOSS_DOMINANT, NEUTRAL)
        window_hours: Time window for calculation
        timestamp: When metric was calculated
    """

    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    realized_profit_btc: float
    realized_loss_btc: float
    net_realized_pnl_btc: float
    profit_utxo_count: int
    loss_utxo_count: int
    profit_loss_ratio: float
    signal: Literal["PROFIT_DOMINANT", "LOSS_DOMINANT", "NEUTRAL"]
    window_hours: int
    timestamp: datetime
```

**Field Constraints**:

| Field | Type | Constraint |
|-------|------|------------|
| `realized_profit_usd` | float | >= 0 |
| `realized_loss_usd` | float | >= 0 |
| `net_realized_pnl_usd` | float | Any (can be negative) |
| `profit_utxo_count` | int | >= 0 |
| `loss_utxo_count` | int | >= 0 |
| `profit_loss_ratio` | float | >= 0 (0 if no losses) |
| `window_hours` | int | > 0 |

---

### NetRealizedPnLHistoryPoint

Single data point for historical P/L data.

```python
@dataclass
class NetRealizedPnLHistoryPoint:
    """Single point in Net Realized P/L history."""

    date: date
    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    profit_utxo_count: int
    loss_utxo_count: int
```

---

## Pydantic Response Models

### NetRealizedPnLResponse

FastAPI response model for `/api/metrics/net-realized-pnl`.

```python
class NetRealizedPnLResponse(BaseModel):
    """API response for Net Realized P/L endpoint."""

    realized_profit_usd: float = Field(..., ge=0, description="Total profit realized (USD)")
    realized_loss_usd: float = Field(..., ge=0, description="Total loss realized (USD)")
    net_realized_pnl_usd: float = Field(..., description="Net P/L (profit - loss)")
    realized_profit_btc: float = Field(..., ge=0, description="Total profit (BTC)")
    realized_loss_btc: float = Field(..., ge=0, description="Total loss (BTC)")
    net_realized_pnl_btc: float = Field(..., description="Net P/L (BTC)")
    profit_utxo_count: int = Field(..., ge=0, description="UTXOs spent at profit")
    loss_utxo_count: int = Field(..., ge=0, description="UTXOs spent at loss")
    profit_loss_ratio: float = Field(..., ge=0, description="Profit/Loss ratio")
    signal: str = Field(..., description="PROFIT_DOMINANT, LOSS_DOMINANT, or NEUTRAL")
    window_hours: int = Field(..., gt=0, description="Time window in hours")
    timestamp: datetime = Field(..., description="Calculation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
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
        }
```

### NetRealizedPnLHistoryResponse

FastAPI response model for `/api/metrics/net-realized-pnl/history`.

```python
class NetRealizedPnLHistoryResponse(BaseModel):
    """API response for Net Realized P/L history endpoint."""

    history: list[NetRealizedPnLHistoryPoint]
    days: int = Field(..., gt=0, description="Number of days in history")
    start_date: date
    end_date: date
```

---

## Database Schema

### Source: utxo_lifecycle_full VIEW (Existing)

No schema changes required. Query uses existing columns:

| Column | Type | Purpose |
|--------|------|---------|
| `creation_price_usd` | DOUBLE | Price when UTXO created |
| `spent_price_usd` | DOUBLE | Price when UTXO spent |
| `btc_value` | DOUBLE | UTXO amount in BTC |
| `is_spent` | BOOLEAN | Filter for spent UTXOs |
| `spent_timestamp` | TIMESTAMP | Time window filter |

### Query Template

```sql
SELECT
    -- USD metrics
    COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
        THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS realized_profit_usd,
    COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
        THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS realized_loss_usd,

    -- BTC metrics
    COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
        THEN btc_value ELSE 0 END), 0) AS profit_btc_volume,
    COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
        THEN btc_value ELSE 0 END), 0) AS loss_btc_volume,

    -- Counts
    COUNT(CASE WHEN spent_price_usd > creation_price_usd THEN 1 END) AS profit_count,
    COUNT(CASE WHEN spent_price_usd < creation_price_usd THEN 1 END) AS loss_count

FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND spent_timestamp >= ?
  AND creation_price_usd > 0
  AND spent_price_usd > 0
```

---

## State Transitions

This metric is stateless - no state transitions to track.

---

## Validation Rules

1. **Price Data Required**: Both `creation_price_usd` and `spent_price_usd` must be > 0
2. **Window Bounds**: `window_hours` must be between 1 and 720 (30 days)
3. **Division Safety**: Handle `realized_loss_usd = 0` when calculating ratio (return 0 or infinity indicator)

---

## Relationships

```
┌─────────────────────────┐
│   utxo_lifecycle_full   │
│  (VIEW - existing)      │
│  ─────────────────────  │
│  creation_price_usd     │◄─── Price at acquisition
│  spent_price_usd        │◄─── Price at disposal
│  btc_value              │◄─── Amount
│  is_spent               │◄─── Filter: TRUE only
│  spent_timestamp        │◄─── Time window filter
└─────────────────────────┘
           │
           │ Aggregate Query
           ▼
┌─────────────────────────┐
│  NetRealizedPnLResult   │
│  (Output Dataclass)     │
│  ─────────────────────  │
│  realized_profit_usd    │
│  realized_loss_usd      │
│  net_realized_pnl_usd   │
│  profit_utxo_count      │
│  loss_utxo_count        │
│  signal                 │
└─────────────────────────┘
```
