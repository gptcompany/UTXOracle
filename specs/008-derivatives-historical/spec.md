# Feature Specification: Derivatives Historical Integration

**Feature Branch**: `008-derivatives-historical`
**Created**: 2025-12-03
**Status**: Draft
**Input**: User description: "Integrate Binance Futures historical data (Funding Rates, Open Interest) from existing LiquidationHeatmap DuckDB into UTXOracle signal fusion. Use DuckDB cross-database query to read data without duplication. Start with historical backtesting, then extend to real-time in future spec (009)."

## Context & Dependencies

### LiquidationHeatmap Integration

**Existing Infrastructure** (path: `/media/sam/1TB/LiquidationHeatmap`):
- DuckDB database: `data/processed/liquidations.duckdb`
- Funding Rates: Already ingested from Binance CSV
- Open Interest: Already ingested via `scripts/ingest_oi.py`
- Data source: `/media/sam/3TB-WDC/binance-history-data-downloader/data` (3TB historical)
- Granularity: 5-minute intervals (OI), 8-hour intervals (Funding)

**Approach**: DuckDB `ATTACH` for cross-database read (zero data duplication)

```sql
ATTACH '/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb'
AS liq (READ_ONLY);

-- Funding rates: 8-hour intervals (4,119 records)
SELECT timestamp, funding_rate
FROM liq.funding_rate_history
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC;

-- Open Interest: 5-minute intervals (417,460 records)
SELECT timestamp, open_interest_value
FROM liq.open_interest_history
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC;
```

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Funding Rate Signal Integration (Priority: P1)

As a Bitcoin trader, I want to see **Binance Funding Rate** incorporated into the signal fusion, so I can detect leverage sentiment (positive = longs pay shorts = bullish crowded trade).

**Why this priority**: Funding rate is a strong contrarian indicator. Extreme positive funding (>0.1%) often precedes corrections; extreme negative (<-0.05%) precedes rallies. Already ingested in LiquidationHeatmap - just need to read and integrate.

**Independent Test**: Can be fully tested by:
1. Querying LiquidationHeatmap DuckDB for funding rate at specific timestamp
2. Converting to signal vote (-1 to +1)
3. Adding to Monte Carlo fusion with configurable weight

**Acceptance Scenarios**:

1. **Given** Funding rate is +0.15% (extremely positive, longs paying)
   **When** funding signal is calculated
   **Then** funding_vote is **-0.8** (contrarian: bearish for BTC price)

2. **Given** Funding rate is -0.08% (negative, shorts paying)
   **When** funding signal is calculated
   **Then** funding_vote is **+0.6** (contrarian: bullish for BTC price)

3. **Given** Funding rate is +0.01% (neutral)
   **When** funding signal is calculated
   **Then** funding_vote is **0.0** (no strong signal)

4. **Given** Funding rate data is unavailable (LiquidationHeatmap offline)
   **When** signal fusion runs
   **Then** funding_vote is excluded (graceful degradation), fusion continues with whale + utxo only

---

### User Story 2 - Open Interest Signal Integration (Priority: P1)

As a Bitcoin trader, I want to see **Open Interest changes** as a signal component, so I can detect leverage buildup (rising OI = new positions opening = potential for squeeze).

**Why this priority**: OI change rate indicates leverage buildup. Rising OI + rising price = healthy trend. Rising OI + falling price = potential short squeeze setup. Data already in LiquidationHeatmap.

**Independent Test**: Can be fully tested by:
1. Querying OI at t and t-1h from LiquidationHeatmap
2. Calculating % change
3. Converting to signal vote based on price direction

**Acceptance Scenarios**:

1. **Given** OI increased +5% in last 1h AND whale signal is ACCUMULATION
   **When** OI signal is calculated
   **Then** oi_vote is **+0.5** (leverage confirming whale accumulation)

2. **Given** OI increased +5% in last 1h AND whale signal is DISTRIBUTION
   **When** OI signal is calculated
   **Then** oi_vote is **-0.3** (leverage building against whales = potential squeeze)

3. **Given** OI decreased -3% in last 1h (deleveraging)
   **When** OI signal is calculated
   **Then** oi_vote is **0.0** (neutral - positions closing, no directional signal)

4. **Given** OI data has gap (missing timestamps)
   **When** signal calculation runs
   **Then** system uses last known OI or excludes from fusion with warning log

---

### User Story 3 - Combined Derivatives-Enhanced Signal (Priority: P2)

As a Bitcoin trader, I want the **Monte Carlo fusion to include derivatives signals** (Funding + OI) alongside whale flow and UTXOracle, so I get a comprehensive market view.

**Why this priority**: Multi-factor model improves signal quality. Derivatives add leverage sentiment dimension that on-chain metrics miss. Builds on spec-007 Monte Carlo fusion.

**Independent Test**: Can be fully tested by:
1. Providing all four signals (whale, utxo, funding, oi)
2. Running Monte Carlo fusion with configurable weights
3. Verifying output reflects all components

**Acceptance Scenarios**:

1. **Given** whale=ACCUMULATION, utxo_confidence=0.8, funding=-0.05%, OI+3%
   **When** enhanced fusion runs with weights [0.4, 0.2, 0.25, 0.15]
   **Then** combined signal is strongly bullish (>0.7) with tight CI

2. **Given** whale=DISTRIBUTION, utxo_confidence=0.6, funding=+0.2%, OI+8%
   **When** enhanced fusion runs
   **Then** combined signal is bearish (<-0.5) due to whale + extreme funding

3. **Given** conflicting signals (whale bullish, funding bearish, OI neutral)
   **When** enhanced fusion runs
   **Then** signal_std is high (>0.3) indicating uncertainty

---

### User Story 4 - Historical Backtesting (Priority: P2)

As a quantitative researcher, I want to **backtest the derivatives-enhanced signal** against historical price data, so I can validate and optimize signal weights.

**Why this priority**: Backtesting ensures the model works before production. LiquidationHeatmap has months of historical data ready.

**Independent Test**: Can be fully tested by:
1. Running enhanced fusion on historical data (30+ days)
2. Comparing signals with actual BTC price changes (24h forward)
3. Calculating Sharpe ratio and win rate

**Acceptance Scenarios**:

1. **Given** 30 days of historical data (funding, OI, whale flow, UTXOracle)
   **When** backtest runs with default weights
   **Then** report shows: total signals, win rate, avg return, Sharpe ratio

2. **Given** backtest identifies BUY signals with >0.7 confidence
   **When** checking 24h price change after each signal
   **Then** win rate is **>60%** (better than random)

3. **Given** backtest results show poor performance with default weights
   **When** weight optimization runs (grid search)
   **Then** optimal weights are reported with improved Sharpe ratio

---

### Edge Cases

- **What happens when LiquidationHeatmap DuckDB is locked (concurrent write)?**
  → Use `READ_ONLY` mode; retry with exponential backoff (max 3 attempts).

- **What happens when funding/OI timestamps don't align with block times?**
  → Use nearest timestamp within 10-minute tolerance; flag if gap > 10min.

- **What happens when Bybit data is added later?**
  → Abstract exchange source; weight aggregation across exchanges (future spec-009).

- **What happens during exchange maintenance (missing data periods)?**
  → Detect gaps, exclude derivatives signals during gaps, log warning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read Funding Rate from LiquidationHeatmap DuckDB via ATTACH
- **FR-002**: System MUST read Open Interest from LiquidationHeatmap DuckDB via ATTACH
- **FR-003**: Funding Rate MUST be converted to contrarian signal (-1 to +1)
- **FR-004**: OI change MUST be calculated as % change over configurable window (default: 1h)
- **FR-005**: OI signal MUST consider whale direction for context (confirmation vs divergence)
- **FR-006**: Enhanced fusion MUST support configurable weights for 4 components
- **FR-007**: Default weights: whale=0.40, utxo=0.20, funding=0.25, oi=0.15
- **FR-008**: System MUST gracefully degrade if derivatives data unavailable
- **FR-009**: Backtest script MUST output: win rate, total return, Sharpe ratio, max drawdown
- **FR-010**: Derivatives data MUST use 5-minute TTL cache to avoid repeated cross-DB queries (DuckDB ATTACH satisfies this - no data duplication)
- **FR-011**: System MUST log data freshness (last update timestamp from LiquidationHeatmap)

### Non-Functional Requirements

- **NFR-001**: Cross-DB query latency MUST be <500ms for 24h of funding+OI data
- **NFR-002**: Zero data duplication (read from LiquidationHeatmap, don't copy)
- **NFR-003**: Path to LiquidationHeatmap DuckDB MUST be configurable via .env
- **NFR-004**: Backward compatible: existing whale+utxo fusion still works if derivatives disabled

### Key Entities *(include if feature involves data)*

```python
@dataclass
class FundingRateSignal:
    timestamp: datetime
    symbol: str                  # "BTCUSDT"
    exchange: str                # "binance" (extensible to "bybit")
    funding_rate: float          # Raw rate (e.g., 0.0015 = 0.15%)
    funding_vote: float          # Contrarian signal (-1 to +1)
    is_extreme: bool             # True if |rate| > 0.1%

@dataclass
class OpenInterestSignal:
    timestamp: datetime
    symbol: str
    exchange: str
    oi_value: float              # Absolute OI in USD
    oi_change_1h: float          # % change in last 1h
    oi_change_24h: float         # % change in last 24h
    oi_vote: float               # Signal vote (-1 to +1)
    context: str                 # "confirming" | "diverging" | "neutral"

@dataclass
class EnhancedFusionResult:
    # Base Monte Carlo fields (from spec-007)
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: str
    action_confidence: float

    # Component breakdown
    whale_vote: float
    whale_weight: float
    utxo_vote: float
    utxo_weight: float
    funding_vote: float | None   # None if unavailable
    funding_weight: float
    oi_vote: float | None        # None if unavailable
    oi_weight: float

    # Metadata
    derivatives_available: bool
    data_freshness_minutes: int  # Age of newest derivatives data

@dataclass
class BacktestResult:
    start_date: datetime
    end_date: datetime
    total_signals: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    win_rate: float              # % of correct directional calls
    total_return: float          # Cumulative return if following signals
    sharpe_ratio: float          # Risk-adjusted return
    max_drawdown: float          # Worst peak-to-trough
    optimal_weights: dict | None # If optimization ran
```

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Single funding rate record read from LiquidationHeatmap in <100ms (batch 24h <500ms per NFR-001)
- **SC-002**: OI data successfully read and % change calculated correctly
- **SC-003**: Enhanced fusion produces valid output with all 4 components
- **SC-004**: Backtest on 30 days shows win rate >55% (better than baseline)
- **SC-005**: Graceful degradation works: system runs with whale+utxo if derivatives fail
- **SC-006**: Zero data duplication: LiquidationHeatmap remains single source of truth

### Definition of Done

- [ ] DuckDB cross-database query working (ATTACH LiquidationHeatmap)
- [ ] Funding rate reader implemented with contrarian signal conversion
- [ ] OI reader implemented with % change calculation
- [ ] Enhanced fusion integrates all 4 signal components
- [ ] Weights configurable via .env or config
- [ ] Backtest script produces performance report
- [ ] Unit tests for funding/OI readers (≥80% coverage)
- [ ] Integration test: full fusion with real LiquidationHeatmap data
- [ ] Graceful degradation tested (derivatives unavailable scenario)
- [ ] Documentation updated in CLAUDE.md

## Technical Notes

### Implementation Order (KISS)

1. **DuckDB Cross-DB Setup** (~50 LOC) - ATTACH and basic query
2. **Funding Rate Reader** (~100 LOC) - Read + contrarian conversion
3. **OI Reader** (~120 LOC) - Read + % change + context logic
4. **Enhanced Fusion** (~80 LOC) - Extend Monte Carlo from spec-007
5. **Backtest Script** (~150 LOC) - Historical validation

### Files to Modify

- `scripts/daily_analysis.py` - Add derivatives fetch to main flow
- `scripts/metrics/monte_carlo_fusion.py` - Extend for 4 components (from spec-007)
- `.env` - Add `LIQUIDATION_HEATMAP_DB_PATH`

### Files to Create

- `scripts/derivatives/funding_rate_reader.py` - Funding rate from LiquidationHeatmap
- `scripts/derivatives/oi_reader.py` - Open Interest from LiquidationHeatmap
- `scripts/derivatives/enhanced_fusion.py` - 4-component fusion logic
- `scripts/backtest_derivatives.py` - Historical performance validation
- `tests/test_derivatives_integration.py` - Test suite

### Configuration

```bash
# .env additions
LIQUIDATION_HEATMAP_DB_PATH=/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb
DERIVATIVES_ENABLED=true
FUNDING_WEIGHT=0.25
OI_WEIGHT=0.15
OI_CHANGE_WINDOW_HOURS=1
```

### Dependencies

- **Internal**: spec-007 Monte Carlo fusion (prerequisite)
- **External**: LiquidationHeatmap DuckDB (must be accessible)
- **Data**: Binance BTCUSDT funding + OI (already in LiquidationHeatmap)

## Out of Scope

- Real-time WebSocket integration (→ spec-009-derivatives-realtime)
- Bybit exchange data (→ future extension)
- Liquidation price levels from LiquidationHeatmap (different use case)
- Automatic weight optimization via ML (research task)

## Future Extensions (spec-009)

After historical validation, spec-009 will add:
- Binance WebSocket for real-time funding/OI
- Bybit WebSocket integration
- Multi-exchange aggregation
- Alert system for extreme funding rates
