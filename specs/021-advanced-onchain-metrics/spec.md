# spec-021: Advanced On-Chain Metrics

## Overview

Implement critical on-chain metrics for professional-grade Bitcoin analysis. These metrics build on `utxo_lifecycle` (spec-017) to provide institutional-quality signals comparable to Glassnode/CheckOnChain.

## Metrics Summary

| Priority | Metric | Evidence Grade | Effort | Module |
|----------|--------|----------------|--------|--------|
| P0 | URPD | A | 4-6h | `urpd.py` |
| P1 | Supply in Profit/Loss | A | 2h | `supply_profit_loss.py` |
| P1 | Reserve Risk | A | 2-3h | `reserve_risk.py` |
| P1 | Sell-side Risk Ratio | A | 2-3h | `sell_side_risk.py` |
| P2 | Coindays Destroyed | B | 2h | `coindays.py` |
| P2 | Value Days Destroyed | B | 1h | `coindays.py` |

**Total Effort: 13-17 hours**

---

## P0: URPD (UTXO Realized Price Distribution)

### Definition
Distribution of unspent BTC by acquisition price (cost basis). Shows where supply was accumulated.

### Formula
```
For each price bucket [P_low, P_high]:
    URPD[bucket] = Σ(btc_value) where creation_price ∈ [P_low, P_high]
```

### Use Case
- **Support/Resistance**: Large URPD clusters = strong S/R zones
- **Profit Taking**: Coins above current price = potential sell pressure
- **Accumulation**: Coins below current price = holder conviction

### Visualization
```
Price ($)  |  BTC Supply
-----------+------------------
$100,000+  |  ████████ 2.1M BTC
$90-100k   |  ██████████████ 3.5M BTC  ← Heavy cluster
$80-90k    |  ████████████ 2.8M BTC
$70-80k    |  ██████ 1.5M BTC
$60-70k    |  ████ 1.0M BTC
...
```

### Data Requirements
```sql
SELECT
    FLOOR(creation_price_usd / :bucket_size) * :bucket_size as price_bucket,
    SUM(btc_value) as btc_in_bucket,
    COUNT(*) as utxo_count
FROM utxo_lifecycle
WHERE is_spent = FALSE
GROUP BY price_bucket
ORDER BY price_bucket DESC
```

### Output Structure
```python
@dataclass
class URPDResult:
    buckets: list[URPDBucket]  # Price bucket -> BTC amount
    total_supply: float
    current_price: float
    supply_above_price: float  # Potential sell pressure
    supply_below_price: float  # In profit
    dominant_bucket: URPDBucket
    timestamp: datetime
```

---

## P1: Supply in Profit/Loss

### Definition
Breakdown of circulating supply by profit/loss status relative to current price.

### Formulas
```
Supply in Profit = Σ(btc_value) where current_price > creation_price
Supply in Loss   = Σ(btc_value) where current_price < creation_price
% in Profit      = Supply in Profit / Total Supply × 100
```

### Signals
| % in Profit | Market Phase |
|-------------|--------------|
| > 95% | Euphoria (cycle top warning) |
| 80-95% | Bull market |
| 50-80% | Transition |
| < 50% | Capitulation (accumulation zone) |

### Data Requirements
```sql
SELECT
    SUM(CASE WHEN :current_price > creation_price_usd THEN btc_value ELSE 0 END) as in_profit,
    SUM(CASE WHEN :current_price < creation_price_usd THEN btc_value ELSE 0 END) as in_loss,
    SUM(CASE WHEN :current_price = creation_price_usd THEN btc_value ELSE 0 END) as breakeven
FROM utxo_lifecycle
WHERE is_spent = FALSE
```

---

## P1: Reserve Risk

### Definition
Measures confidence of long-term holders relative to price. Low = high conviction, good buy. High = low conviction, potential top.

### Formula
```
HODL Bank = Σ(Coin Days Destroyed) [cumulative, opportunity cost of holding]
Reserve Risk = Price / (HODL Bank × Circulating Supply)
```

Alternative (simplified):
```
Reserve Risk = Price / (Liveliness_cumulative × MVRV)
```

### Interpretation
| Reserve Risk | Signal |
|--------------|--------|
| < 0.002 | Strong buy zone (historically cycle bottoms) |
| 0.002 - 0.008 | Accumulation zone |
| 0.008 - 0.02 | Fair value |
| > 0.02 | Distribution zone (cycle top warning) |

### Data Requirements
- Cumulative Coindays Destroyed from `cointime.py`
- Current price
- Circulating supply

---

## P1: Sell-side Risk Ratio

### Definition
Ratio of realized profit to market cap. High = aggressive profit-taking, potential top.

### Formula
```
Sell-side Risk = Realized Profit (30d) / Market Cap
```

Where:
```
Realized Profit = Σ((spend_price - creation_price) × btc_value) for spent UTXOs
```

### Interpretation
| Sell-side Risk | Signal |
|----------------|--------|
| < 0.1% | Low distribution, bullish |
| 0.1% - 0.3% | Normal profit-taking |
| 0.3% - 1.0% | Elevated distribution |
| > 1.0% | Aggressive distribution (top warning) |

### Data Requirements
```sql
SELECT SUM((spend_price_usd - creation_price_usd) * btc_value) as realized_profit
FROM utxo_lifecycle
WHERE is_spent = TRUE
  AND spent_timestamp >= :start_date
  AND spend_price_usd > creation_price_usd  -- Only profits
```

---

## P2: Coindays Destroyed (CDD)

### Definition
When a UTXO is spent, CDD = age_in_days × btc_value. Measures "old money" movement.

### Formula
```
CDD = Σ(age_days × btc_value) for spent UTXOs in period
```

### Existing Implementation
`cointime.py` has `calculate_coinblocks_destroyed()` - needs adaptation for days.

### Signals
- **Spike in CDD**: Long-term holders moving coins (distribution or exchange deposit)
- **Low CDD**: Diamond hands, accumulation phase

---

## P2: Value Days Destroyed (VDD)

### Definition
CDD weighted by price. Captures both time AND value of moved coins.

### Formula
```
VDD = CDD × Price = Σ(age_days × btc_value × price_at_spend)
```

### Multiple
```
VDD Multiple = VDD / 365d_MA(VDD)
```

Values > 2.0 indicate significant long-term holder distribution.

---

## Functional Requirements

### FR-001: URPD Calculation
- Calculate distribution with configurable bucket sizes
- Default buckets: $1,000, $5,000, $10,000
- Support custom bucket ranges

### FR-002: Supply Profit/Loss
- Real-time calculation given current price
- Separate STH/LTH profit/loss breakdown
- Historical time series: DEFERRED to spec-022 (metrics dashboard)
  - Note: Current scope returns point-in-time calculations only

### FR-003: Reserve Risk
- Daily calculation
- Integration with existing cointime liveliness

### FR-004: Sell-side Risk
- Rolling window (7d, 30d, 90d)
- Realized profit tracking from spent UTXOs

### FR-005: CDD/VDD
- Daily aggregation
- Rolling averages (7d, 30d, 365d)
- Multiple calculation

---

## Non-Functional Requirements

### NFR-001: Performance
- URPD calculation: < 30 seconds
- Other metrics: < 5 seconds each
- Use DuckDB aggregation, not Python loops

### NFR-002: Storage
- Daily snapshots in DuckDB
- Efficient time-series queries

### NFR-003: API Integration
- All metrics exposed via FastAPI endpoints
- JSON response format

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| `utxo_lifecycle.py` | ✅ Complete | Core UTXO data |
| `cointime.py` | ✅ Complete | Liveliness, coinblocks |
| `realized_metrics.py` | ✅ Complete | MVRV, NUPL |
| `hodl_waves.py` | ✅ Complete | Age cohorts |

---

## Acceptance Criteria

### URPD
- [ ] Distribution calculated for configurable buckets
- [ ] Supply above/below price calculated
- [ ] Visualization data exported

### Supply in Profit/Loss
- [ ] Accurate profit/loss split
- [ ] STH/LTH breakdown available
- [ ] % in profit signal classification

### Reserve Risk
- [ ] Formula matches Glassnode within 5%
- [ ] Signal zones implemented

### Sell-side Risk
- [ ] 30d rolling calculation
- [ ] Realized profit tracking

### CDD/VDD
- [ ] Daily values calculated
- [ ] Rolling averages working
- [ ] VDD Multiple implemented

---

## Files to Create

| File | Purpose |
|------|---------|
| `scripts/metrics/urpd.py` | URPD calculation |
| `scripts/metrics/supply_profit_loss.py` | Profit/Loss breakdown |
| `scripts/metrics/reserve_risk.py` | Reserve Risk metric |
| `scripts/metrics/sell_side_risk.py` | Sell-side Risk Ratio |
| `scripts/metrics/coindays.py` | CDD + VDD metrics |
| `tests/test_urpd.py` | URPD tests |
| `tests/test_supply_profit_loss.py` | Supply P/L tests |
| `tests/test_reserve_risk.py` | Reserve Risk tests |
| `tests/test_sell_side_risk.py` | Sell-side Risk tests |
| `tests/test_coindays.py` | CDD/VDD tests |

---

## Integration with Fusion

After implementation, add to Monte Carlo Fusion:

```python
ENHANCED_WEIGHTS = {
    # ... existing ...
    "urpd_signal": 0.02,      # Support/resistance proximity
    "supply_profit": 0.02,    # % in profit extremes
    "reserve_risk": 0.02,     # LTH conviction
    "sell_side": 0.02,        # Distribution pressure
}
```

Rebalance by reducing lower-evidence signals.
