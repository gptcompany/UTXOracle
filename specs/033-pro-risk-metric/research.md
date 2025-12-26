# Research: PRO Risk Metric (spec-033)

**Date**: 2025-12-25 | **Status**: Complete

## 1. Percentile Normalization Strategy

### Decision
**Static 4-year window with 2% winsorization** - Use full historical data (minimum 1,460 days) with winsorization to cap extreme outliers.

### Rationale
- Bitcoin's halving cycle is ~4 years; this captures at least one complete market cycle
- Existing UTXOracle precedent: `mvrv_z` uses 365-day history but benefits from longer windows
- Winsorization (capping at 2nd/98th percentile) prevents single events (e.g., 2021 blow-off top) from skewing distribution
- Static calculation avoids look-ahead bias for backtesting

### Alternatives Considered
- **Rolling window (365d)**: More responsive but introduces instability; rejected for composite indicator
- **Truncation (remove outliers)**: Loses data points; winsorization preserves while capping
- **Z-score normalization**: Assumes normal distribution; Bitcoin metrics are heavy-tailed

### Implementation Pattern
```python
def normalize_to_percentile(
    value: float,
    historical_data: list[float],
    winsorize_pct: float = 0.02
) -> float:
    if len(historical_data) < 1460:
        return 0.5  # Neutral when insufficient data

    lower = np.percentile(historical_data, winsorize_pct * 100)
    upper = np.percentile(historical_data, (1 - winsorize_pct) * 100)
    capped_value = max(lower, min(upper, value))

    return sum(1 for h in historical_data if h <= capped_value) / len(historical_data)
```

---

## 2. Composite Weight Selection

### Decision
**Evidence-based fixed weights** with Grade A metrics weighted 70% total, Grade B metrics 30% total.

### Final Weights

| Metric | Weight | Evidence Grade | Justification |
|--------|--------|----------------|---------------|
| MVRV Z-Score | **30%** | A | Proven cycle indicator, used in UTXOracle fusion |
| SOPR | **20%** | A | 82.44% directional accuracy (Omole & Enke 2024) |
| NUPL | **20%** | A | Direct profit/loss measure |
| Reserve Risk | **15%** | B | ARK Invest cointime framework |
| Puell Multiple | **10%** | B | Miner-centric, lagging indicator |
| HODL Waves | **5%** | B | Derivative of age cohorts |

**Total: 100%**

### Rationale
- Adjusted from spec's initial weights to align with evidence strength
- MVRV/SOPR/NUPL (Grade A) get higher weights due to academic validation
- HODL Waves reduced from 10%→5% because it's derivative of data already in MVRV/NUPL
- Follows UTXOracle fusion pattern: higher weights for validated signals

### Alternatives Considered
- **Dynamic ML-optimized weights**: Rejected due to overfitting risk with only 6 components
- **Equal weights (16.7% each)**: Simpler but ignores evidence quality differences
- **Geometric mean aggregation**: More conservative; recommended as secondary view in API

---

## 3. Puell Multiple Implementation

### Decision
**Extend cointime_metrics table** with fee tracking; calculate inline with daily metrics update.

### Definition
```
Puell Multiple = Daily Miner Revenue (USD) / 365-day MA(Daily Miner Revenue)
Daily Revenue = (Block Subsidy + Fees) × BTC Price
```

### Data Sources

| Data | Source | Status |
|------|--------|--------|
| Block subsidy | `block_height // 210_000` halving calculation | ✅ Available |
| Transaction fees | electrs `/api/block/{hash}` → `totalFees` | ⚠️ Need to add |
| BTC price | UTXOracle daily calculation or `utxo_snapshots` | ✅ Available |
| 365d MA | Rolling average over `cointime_metrics` | ✅ Can compute |

### Zone Classification

| Puell Value | Zone | Interpretation |
|-------------|------|----------------|
| > 3.5 | OVERHEATED | Potential cycle top |
| 0.5 - 3.5 | FAIR_VALUE | Normal range |
| < 0.5 | CAPITULATION | Potential cycle bottom |

### Implementation Notes
- Add `miner_revenue_usd` and `puell_multiple` columns to `cointime_metrics` table
- Query electrs for fees during daily sync (144 blocks/day = 144 HTTP requests)
- Historical backfill: one-time batch processing for 4+ years

---

## 4. Storage Format

### Decision
**DuckDB table** (`risk_percentiles`) rather than JSON file.

### Rationale
- UTXOracle already uses DuckDB for `cointime_metrics`, `utxo_snapshots`
- Efficient range queries for historical percentile windows
- Atomic updates with transaction support
- ~2.2MB for 6 metrics × 4 years

### Schema
```sql
CREATE TABLE IF NOT EXISTS risk_percentiles (
    metric_name VARCHAR NOT NULL,
    date DATE NOT NULL,
    value DOUBLE,           -- Raw metric value
    percentile DOUBLE,      -- 0-1 normalized
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (metric_name, date)
);

CREATE TABLE IF NOT EXISTS pro_risk_daily (
    date DATE PRIMARY KEY,
    value DOUBLE,           -- Composite 0-1 score
    zone VARCHAR,           -- Classification
    components JSON,        -- Individual normalized scores
    confidence DOUBLE,      -- Data availability score
    updated_at TIMESTAMP
);
```

---

## 5. Confidence Calculation

### Decision
**Weighted data availability** - Confidence reflects how many component metrics have sufficient history.

### Formula
```python
def calculate_confidence(components: dict[str, float | None]) -> float:
    weights = {"mvrv_z": 0.30, "sopr": 0.20, "nupl": 0.20,
               "reserve_risk": 0.15, "puell": 0.10, "hodl_waves": 0.05}
    available_weight = sum(
        weights[k] for k, v in components.items() if v is not None
    )
    return available_weight
```

### Interpretation
- Confidence 1.0: All 6 components available with 4+ years history
- Confidence 0.85: Missing one Grade B metric
- Confidence < 0.70: Missing Grade A metric - flag as low confidence

---

## Summary

| Research Question | Decision | Confidence |
|-------------------|----------|------------|
| Normalization method | Static 4-year with 2% winsorization | HIGH |
| Weight selection | Evidence-based fixed weights (30/20/20/15/10/5) | HIGH |
| Puell implementation | Extend cointime_metrics, add fee tracking | HIGH |
| Storage format | DuckDB tables | HIGH |
| Aggregation method | Weighted arithmetic mean (primary) | HIGH |

**All NEEDS CLARIFICATION items resolved. Ready for Phase 1.**
