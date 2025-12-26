# Research: Bitcoin Price Power Law Model

**Feature**: spec-034 | **Date**: 2025-12-26

This document consolidates research findings for Phase 0 of the implementation plan.

## Research Questions

### 1. Model Coefficients (RBN Research)

**Question**: What are the verified power law coefficients for Bitcoin price?

**Decision**: Use RBN-derived coefficients with validation capability

**Findings**:
- The Bitcoin Power Law model was popularized by Giovanni Santostasi and expanded by RBN (Robot Buena Noche)
- Core formula: `log10(Price) = α + β × log10(days_since_genesis)`
- Published coefficients (as of 2024):
  - α (intercept): -17.01 (range: -17.5 to -16.5 in literature)
  - β (slope/exponent): 5.82 (range: 5.7 to 5.9 in literature)
  - R² > 0.95 historically
  - Standard error: ~0.32 in log10 space

**Implementation**:
```python
DEFAULT_MODEL = PowerLawModel(
    alpha=-17.01,
    beta=5.82,
    r_squared=0.95,
    std_error=0.32,
    fitted_on=date(2025, 1, 1),
    sample_size=5800
)
```

**Alternatives Considered**:
- Hardcode only: Rejected - need recalibration capability
- Fetch from API: Rejected - violates local-first principle
- Allow user override: Accepted - provide default + fit_power_law() function

### 2. Data Source for Model Fitting

**Question**: Where to get historical BTC/USD prices for model fitting?

**Decision**: Use existing `daily_prices` DuckDB table

**Findings**:
- `daily_prices` table already exists (from `scripts/bootstrap/build_price_table.py`)
- Schema: `date DATE PRIMARY KEY, price_usd DOUBLE NOT NULL, block_height INTEGER`
- Data source: mempool.space historical API (local instance)
- Coverage: 2011-07-17 to present (~5,000+ rows)
- Format: Daily closing prices in USD

**Query for model fitting**:
```sql
SELECT date, price_usd
FROM daily_prices
WHERE price_usd > 0
ORDER BY date
```

**Alternatives Considered**:
- Fetch from external API: Rejected - already have local data
- Use UTXOracle-calculated prices: Rejected - need exchange prices for this model (market price vs on-chain price)

### 3. Zone Classification Thresholds

**Question**: What thresholds define undervalued/fair/overvalued zones?

**Decision**: Use standard deviation bands with configurable multipliers

**Findings**:
- Standard approach uses ±1σ bands in log space for support/resistance
- Zone classification based on deviation from fair value:
  - **Undervalued**: < -20% deviation (below lower band region)
  - **Fair value**: -20% to +50% deviation (within bands)
  - **Overvalued**: > +50% deviation (above upper band region)

**Rationale for asymmetric thresholds**:
- Bitcoin historically spends more time below fair value (accumulation)
- Tops are shorter but more extreme (up to +100-200% above fair value)
- 20% below is significant buying opportunity
- 50% above indicates late-stage bull market

**Implementation**:
```python
ZONE_UNDERVALUED_THRESHOLD = -0.20  # 20% below fair value
ZONE_OVERVALUED_THRESHOLD = 0.50    # 50% above fair value
```

**Alternatives Considered**:
- Symmetric bands (±30%): Rejected - doesn't match historical patterns
- Multiple zones (5 levels): Considered for future - keep simple for MVP

### 4. API Endpoint Design

**Question**: What API structure matches existing patterns?

**Decision**: Follow existing `/api/metrics/*` patterns

**Findings**:
- Existing endpoints use `/api/metrics/{metric-name}` pattern
- This model is a valuation model, not an on-chain metric
- Recommend: `/api/v1/models/power-law` (new namespace for price models)

**Endpoints**:
1. `GET /api/v1/models/power-law` - Get current model parameters
2. `GET /api/v1/models/power-law/predict?date=YYYY-MM-DD` - Get prediction for date
3. `POST /api/v1/models/power-law/recalibrate` - Trigger model recalibration (state-changing)

**Alternatives Considered**:
- `/api/metrics/power-law`: Rejected - this is a price model, not on-chain metric
- `/api/power-law`: Rejected - less organized than models namespace

### 5. Model Recalibration Strategy

**Question**: How often should the model be recalibrated?

**Decision**: Monthly automatic with manual override capability

**Findings**:
- Power law is long-term model - daily recalibration unnecessary
- Monthly recalibration captures new data without overfitting
- Each recalibration adds ~30 new data points
- Performance: <1s for ~5000 point regression

**Implementation**:
- Store model in memory (small: 6 floats)
- On API startup: Load default or recalibrate if stale (>30 days)
- Optional: `/api/v1/models/power-law/recalibrate` endpoint

**Alternatives Considered**:
- Real-time fit: Rejected - unnecessary overhead
- Never recalibrate: Rejected - model drifts over years
- Store in DB: Rejected for MVP - memory is sufficient

### 6. Frontend Visualization

**Question**: What chart type best displays power law model?

**Decision**: Plotly.js log-log scatter with regression line and bands

**Findings**:
- Log-log plot is essential (both axes logarithmic)
- Display elements:
  1. Historical prices (scatter points)
  2. Regression line (fair value)
  3. ±1σ bands (support/resistance corridor)
  4. Current price marker
- Color coding:
  - Green: Undervalued zone
  - Orange: Fair value zone
  - Red: Overvalued zone

**Plotly.js features**:
- `type: 'scatter', mode: 'markers'` for prices
- `type: 'scatter', mode: 'lines'` for regression
- `xaxis: {type: 'log'}`, `yaxis: {type: 'log'}`
- Hover template for zone indication

**Alternatives Considered**:
- Linear scale: Rejected - hides power law relationship
- Matplotlib (backend render): Rejected - existing stack is Plotly.js
- Canvas 2D: Rejected - Plotly.js already used, more features

### 7. Conflict with Existing power_law.py

**Question**: How to name the new module to avoid confusion?

**Decision**: Use `price_power_law.py` in `scripts/models/`

**Findings**:
- Existing `scripts/metrics/power_law.py` (spec-009) = UTXO distribution analysis
- New module = Price-over-time regression
- Clear separation:
  - `scripts/metrics/power_law.py` → UTXO distribution power law
  - `scripts/models/price_power_law.py` → Bitcoin price power law

**Directory structure rationale**:
- `scripts/metrics/` = On-chain metrics (UTXO analysis, SOPR, etc.)
- `scripts/models/` = Price models (power law, future: S2F, rainbow, etc.)

**Alternatives Considered**:
- `bitcoin_power_law.py`: Could work but `price_` prefix clearer
- `power_law_price.py`: Less readable
- Rename existing: Rejected - would break spec-009 imports

## Summary

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Coefficients | RBN defaults + recalibration | Balance accuracy with local-first |
| Data source | `daily_prices` table | Already exists, local data |
| Zone thresholds | -20%/+50% asymmetric | Matches historical patterns |
| API namespace | `/api/v1/models/power-law` | Separate from on-chain metrics |
| Recalibration | Monthly automatic | Balances freshness with stability |
| Visualization | Plotly.js log-log | Consistent with existing frontend |
| Module name | `price_power_law.py` | Clear distinction from spec-009 |

**All NEEDS CLARIFICATION items resolved.**
