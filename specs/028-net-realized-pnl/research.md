# Research: Net Realized Profit/Loss (spec-028)

## Overview

This document resolves technical decisions for implementing the Net Realized P/L metric.
Feature complexity: **Low** - leverages existing infrastructure with no new dependencies.

---

## 1. Data Source Verification

### Decision
Use existing `utxo_lifecycle_full` VIEW without modification.

### Rationale
The VIEW already contains all required columns:
- `creation_price_usd`: Price at UTXO creation (from daily_prices join)
- `spent_price_usd`: Price at UTXO spending (from utxo_lifecycle table)
- `btc_value`: Amount in BTC (computed from satoshis)
- `is_spent`: Boolean flag for spent UTXOs
- `spent_timestamp`: When the UTXO was spent

### Evidence
```sql
-- From scripts/bootstrap/import_chainstate.py:103-157
CREATE OR REPLACE VIEW utxo_lifecycle_full AS
SELECT
    ...
    COALESCE(dp.price_usd, 0.0) AS creation_price_usd,
    u.spent_price_usd,
    CAST(u.amount AS DOUBLE) / 100000000.0 AS btc_value,
    u.is_spent,
    u.spent_timestamp,
    ...
```

### Alternatives Considered
1. **Query base table directly**: Rejected - VIEW already handles price joins
2. **Create new VIEW**: Rejected - YAGNI, existing VIEW sufficient

---

## 2. Profit/Loss Calculation Formula

### Decision
Calculate using spent_price vs creation_price comparison:

```sql
-- Realized Profit (USD)
SUM(CASE WHEN spent_price_usd > creation_price_usd
    THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END)

-- Realized Loss (USD)
SUM(CASE WHEN spent_price_usd < creation_price_usd
    THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END)

-- Net = Profit - Loss
```

### Rationale
- **Profit**: Coins sold at higher price than acquisition = positive cash flow
- **Loss**: Coins sold at lower price than acquisition = negative cash flow
- **Net**: Overall market sentiment indicator

### Edge Cases Handled
| Scenario | Handling |
|----------|----------|
| `creation_price_usd = 0` | Excluded (price data missing) |
| `spent_price_usd = 0` | Excluded (price data missing) |
| `spent_price = creation_price` | Neither profit nor loss (break-even) |
| NULL values | COALESCE to 0, excluded from sums |

### Alternatives Considered
1. **BTC-denominated P/L**: Rejected for primary metric - USD provides clearer capital flow signal
2. **Include break-even**: Rejected - adds noise without insight

---

## 3. Time Window Implementation

### Decision
Support configurable time windows via `spent_timestamp` filter:

```sql
WHERE is_spent = TRUE
  AND spent_timestamp >= (CURRENT_TIMESTAMP - INTERVAL ? hours)
  AND creation_price_usd > 0
  AND spent_price_usd > 0
```

### Rationale
- Filter on `spent_timestamp` (when realized) not `creation_timestamp` (when acquired)
- Index exists on `spent_timestamp` for efficient queries
- Price > 0 ensures valid price data

### Default Windows
| Window | Use Case |
|--------|----------|
| 24h | Real-time sentiment |
| 7d | Weekly trend |
| 30d | Monthly analysis |

### Alternatives Considered
1. **Block-based windows**: Rejected - time-based more intuitive for users
2. **Rolling vs snapshot**: Rolling selected - shows continuous flow

---

## 4. API Design Pattern

### Decision
Follow existing `/api/metrics/*` patterns:
- `GET /api/metrics/net-realized-pnl?window=24` - Current metrics
- `GET /api/metrics/net-realized-pnl/history?days=30` - Historical data

### Rationale
Matches existing endpoints:
- `/api/metrics/cdd-vdd`
- `/api/metrics/revived-supply`
- `/api/metrics/exchange-netflow`

### Response Format
```json
{
  "realized_profit_usd": 1234567.89,
  "realized_loss_usd": 987654.32,
  "net_realized_pnl_usd": 246913.57,
  "profit_utxo_count": 15234,
  "loss_utxo_count": 12456,
  "profit_loss_ratio": 1.22,
  "window_hours": 24,
  "timestamp": "2025-12-18T12:00:00Z"
}
```

---

## 5. Signal Interpretation Logic

### Decision
Include interpretation based on net P/L sign and magnitude:

| Net P/L | Signal | Description |
|---------|--------|-------------|
| > 0 | `PROFIT_DOMINANT` | More value realized as profit |
| < 0 | `LOSS_DOMINANT` | More value realized as loss |
| = 0 | `NEUTRAL` | Balanced profit/loss |

### Rationale
- Simple binary interpretation avoids over-engineering
- Users can apply their own thresholds

### Alternatives Considered
1. **Z-score normalization**: Rejected for MVP - requires historical baseline
2. **Market context integration**: Future enhancement, not MVP scope

---

## Summary

All technical decisions resolved. No NEEDS CLARIFICATION items remain.

| Decision | Choice | Complexity |
|----------|--------|------------|
| Data Source | Existing `utxo_lifecycle_full` VIEW | None |
| Formula | USD-based profit/loss | Low |
| Time Window | `spent_timestamp` filter | Low |
| API Pattern | Follow existing `/api/metrics/*` | Low |
| Interpretation | Simple sign-based signal | Low |

**Total Additional Complexity**: None - fully leverages existing infrastructure.
