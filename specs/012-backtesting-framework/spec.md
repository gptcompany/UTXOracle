# Feature Specification: Backtesting Framework

**Feature Branch**: `012-backtesting-framework`
**Created**: 2025-12-04
**Status**: Draft
**Prerequisites**: spec-009 (Advanced On-Chain Analytics), spec-010 (Wasserstein Distance)
**Input**: User description: "Implement a backtesting framework to validate all on-chain metrics and fusion signals against historical data (2024-2025). Calculate Sharpe ratio, win rate, max drawdown, and other performance metrics. Enable comparison between different signal combinations and weight configurations."

## Context & Motivation

### Background: Signal Validation

Before deploying trading signals in production, we need to validate their predictive power against historical data. Currently, we have 8 signal components (whale, utxo, funding, oi, power_law, symbolic, fractal, wasserstein) but no systematic way to:

1. Measure individual signal accuracy
2. Compare different weight configurations
3. Calculate risk-adjusted returns (Sharpe, Sortino)
4. Identify optimal signal combinations

| Current State | Gap | Solution |
|--------------|-----|----------|
| Live signals | No historical validation | Backtesting framework |
| Fixed weights | No optimization | Sharpe-based ranking |
| Point estimates | No confidence intervals | Monte Carlo backtesting |

**Expected Outcome**: Validated signal weights and empirical win rates

### Scientific Foundation

Backtesting follows standard quantitative finance methodology:

1. **Walk-Forward Optimization**: Train on window [t-N, t], test on [t, t+M], slide forward
2. **Sharpe Ratio**: Risk-adjusted return = (R - Rf) / σ_R
3. **Win Rate**: Percentage of trades with positive P&L
4. **Max Drawdown**: Largest peak-to-trough decline

**Key Constraint**: Avoid look-ahead bias - only use data available at signal time.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single Signal Backtest (Priority: P1)

As a Bitcoin analyst, I want to **backtest individual signals** against historical price data, so I can measure each metric's standalone predictive power.

**Why this priority**: Foundation for all backtesting. Need to know which signals actually work before optimizing combinations. ~150 LOC.

**Independent Test**: Can be fully tested by:
1. Providing synthetic signal series and price series with known correlation
2. Running backtest with simple long/short/hold strategy
3. Verifying P&L calculation matches expected

**Acceptance Scenarios**:

1. **Given** perfectly correlated signal (signal=+1 when price goes up)
   **When** backtest runs with 100% position sizing
   **Then** win_rate=100%, sharpe > 3.0

2. **Given** random signal (no correlation with price)
   **When** backtest runs
   **Then** win_rate ≈ 50%, sharpe ≈ 0.0

3. **Given** inverted signal (signal=+1 when price goes down)
   **When** backtest runs
   **Then** win_rate < 50%, sharpe < 0.0

4. **Given** historical whale_vote signal (30 days)
   **When** backtest runs against BTC/USD price
   **Then** returns sharpe, win_rate, max_drawdown, total_return

---

### User Story 2 - Multi-Signal Comparison (Priority: P1)

As a Bitcoin trader, I want to **compare multiple signals side-by-side**, so I can identify which metrics have the highest predictive power.

**Why this priority**: Enables data-driven weight allocation. Signals with higher Sharpe should get higher weight. ~80 LOC.

**Independent Test**: Can be fully tested by:
1. Providing 3 signals with different correlations to price
2. Running comparative backtest
3. Verifying ranking matches correlation order

**Acceptance Scenarios**:

1. **Given** signals: symbolic (r=0.6), power_law (r=0.4), fractal (r=0.2)
   **When** comparative backtest runs
   **Then** ranking: symbolic > power_law > fractal (by Sharpe)

2. **Given** 8 signal components (spec-009 + spec-010)
   **When** comparative backtest runs on 30 days
   **Then** returns ranked table with Sharpe, win_rate, max_dd for each

3. **Given** comparison with varying position sizes
   **When** backtest runs
   **Then** Sharpe remains consistent (risk-adjusted)

---

### User Story 3 - Fusion Weight Optimization (Priority: P2)

As a Bitcoin trader, I want to **optimize fusion weights** based on backtest results, so I can maximize risk-adjusted returns.

**Why this priority**: Current weights are heuristic (from literature). Empirical optimization should improve performance. ~100 LOC.

**Independent Test**: Can be fully tested by:
1. Providing historical signals and prices
2. Running grid search over weight combinations
3. Verifying optimal weights maximize Sharpe

**Acceptance Scenarios**:

1. **Given** grid search over weight space (10% increments)
   **When** optimizer runs
   **Then** returns best weight configuration with Sharpe > baseline

2. **Given** constraint: sum(weights) = 1.0, each weight >= 0.05
   **When** optimizer runs
   **Then** all returned weights satisfy constraints

3. **Given** walk-forward optimization (train 60 days, test 30 days)
   **When** optimizer runs
   **Then** out-of-sample Sharpe within 20% of in-sample

---

### User Story 4 - Historical Data Integration (Priority: P1)

As a Bitcoin analyst, I want to **load historical UTXOracle and exchange prices**, so backtesting uses real production data.

**Why this priority**: Backtesting is meaningless without real data. Must integrate with existing historical_data/ and DuckDB. ~60 LOC.

**Independent Test**: Can be fully tested by:
1. Loading historical data from existing storage
2. Aligning timestamps between UTXOracle and exchange prices
3. Verifying data completeness (no gaps)

**Acceptance Scenarios**:

1. **Given** DuckDB prices table with 672 days of data
   **When** data loader runs for date range
   **Then** returns aligned DataFrame with utxoracle_price, exchange_price, timestamp

2. **Given** request for 30-day window
   **When** data loader runs
   **Then** returns exactly 30 days of data (or error if incomplete)

3. **Given** historical_data/html_files/ with parsed UTXOracle outputs
   **When** fallback data loader runs
   **Then** extracts prices from HTML files

---

### Edge Cases

- **What happens when signal has NaN values?**
  → Forward-fill NaN from previous value, or exclude period from backtest.

- **What happens when price data has gaps?**
  → Interpolate small gaps (<6h), error on large gaps (>24h).

- **What happens when backtest period is too short?**
  → Require minimum 30 data points; return warning if <100.

- **What happens when all signals are neutral (near 0)?**
  → No trades executed; return 0% return, undefined Sharpe.

---

## Requirements *(mandatory)*

### Functional Requirements

**Core Backtest Engine**:
- **FR-001**: Backtest engine MUST simulate trades based on signal threshold crossing
- **FR-002**: Trade signals: BUY when signal > +0.3, SELL when signal < -0.3, HOLD otherwise (configurable)
- **FR-003**: Position sizing: 100% of capital per trade (configurable 0-100%)
- **FR-004**: Transaction costs: 0.1% per trade (configurable, includes spread + fees)

**Performance Metrics**:
- **FR-005**: Backtest MUST calculate Sharpe ratio (annualized, Rf=0)
- **FR-006**: Backtest MUST calculate Sortino ratio (downside deviation only)
- **FR-007**: Backtest MUST calculate win rate (% profitable trades)
- **FR-008**: Backtest MUST calculate max drawdown (peak-to-trough %)
- **FR-009**: Backtest MUST calculate total return (%)
- **FR-010**: Backtest MUST calculate profit factor (gross profit / gross loss)

**Data Management**:
- **FR-011**: Data loader MUST read from DuckDB `prices` table (primary)
- **FR-012**: Data loader MUST fallback to historical_data/html_files/ (secondary)
- **FR-013**: Data loader MUST align UTXOracle and exchange prices by timestamp
- **FR-014**: Data loader MUST handle timezone-aware timestamps

**Optimization**:
- **FR-015**: Weight optimizer MUST support grid search over weight space
- **FR-016**: Weight optimizer MUST support walk-forward validation
- **FR-017**: Weight optimizer MUST enforce constraints: sum(weights)=1.0, each weight≥0.0

**Output**:
- **FR-018**: Backtest MUST generate summary report (text format)
- **FR-019**: Backtest MUST generate equity curve data (for visualization)
- **FR-020**: Backtest results MUST be stored in DuckDB `backtest_results` table

### Non-Functional Requirements

- **NFR-001**: Full backtest on 365 days MUST complete in <60 seconds
- **NFR-002**: Pure Python implementation (pandas optional but recommended)
- **NFR-003**: Thread-safe for parallel backtest runs
- **NFR-004**: Memory usage <500MB for 1-year backtest

### Key Entities *(mandatory)*

```python
@dataclass
class BacktestConfig:
    start_date: datetime              # Backtest start
    end_date: datetime                # Backtest end
    signal_source: str                # "whale" | "utxo" | "fusion" | etc.
    buy_threshold: float              # Signal > this → BUY (default: 0.3)
    sell_threshold: float             # Signal < this → SELL (default: -0.3)
    position_size: float              # 0.0 to 1.0 (default: 1.0)
    transaction_cost: float           # Per-trade cost (default: 0.001)
    initial_capital: float            # Starting capital in USD (default: 10000)

@dataclass
class Trade:
    entry_time: datetime              # Trade entry timestamp
    exit_time: datetime               # Trade exit timestamp
    entry_price: float                # Entry BTC price
    exit_price: float                 # Exit BTC price
    direction: str                    # "LONG" | "SHORT"
    pnl: float                        # Profit/loss in USD
    pnl_pct: float                    # Profit/loss percentage
    signal_value: float               # Signal that triggered entry

@dataclass
class BacktestResult:
    config: BacktestConfig            # Configuration used
    trades: list[Trade]               # All executed trades
    equity_curve: list[float]         # Portfolio value over time
    timestamps: list[datetime]        # Timestamps for equity curve

    # Performance Metrics
    total_return: float               # Total return %
    sharpe_ratio: float               # Risk-adjusted return (annualized)
    sortino_ratio: float              # Downside-adjusted return
    win_rate: float                   # % winning trades
    max_drawdown: float               # Max peak-to-trough %
    profit_factor: float              # Gross profit / gross loss
    num_trades: int                   # Total trades executed
    avg_trade_duration: float         # Average holding period (hours)

@dataclass
class ComparisonResult:
    signals: list[str]                # Signal names compared
    results: dict[str, BacktestResult]  # Signal -> BacktestResult
    ranking: list[str]                # Signals ranked by Sharpe
    best_signal: str                  # Highest Sharpe signal
    best_sharpe: float                # Best Sharpe value

@dataclass
class OptimizationResult:
    best_weights: dict[str, float]    # Optimal weight configuration
    best_sharpe: float                # Sharpe with optimal weights
    baseline_sharpe: float            # Sharpe with default weights
    improvement: float                # % improvement over baseline
    walk_forward_sharpe: float        # Out-of-sample Sharpe
    weight_grid: list[dict]           # All tested configurations
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Backtest P&L calculation matches manual verification within 0.1%
- **SC-002**: Sharpe ratio calculation matches standard formula
- **SC-003**: 365-day backtest completes in <60 seconds
- **SC-004**: Walk-forward out-of-sample Sharpe within 30% of in-sample
- **SC-005**: Best signal Sharpe > 1.0 on real historical data
- **SC-006**: Code coverage for backtest module ≥85%

### Definition of Done

- [ ] Backtest engine with trade simulation
- [ ] Performance metrics (Sharpe, Sortino, win rate, max drawdown)
- [ ] Data loader from DuckDB and historical_data/
- [ ] Multi-signal comparison
- [ ] Weight optimization with grid search
- [ ] Walk-forward validation
- [ ] DuckDB table for backtest results
- [ ] Summary report generation
- [ ] Unit tests (≥85% coverage)
- [ ] Integration test: full backtest on 30 days
- [ ] Documentation updated

---

## Technical Notes

### Implementation Order (KISS)

1. **Data Loader** (~60 LOC) - Load historical prices
2. **Trade Simulator** (~100 LOC) - Execute trades based on signals
3. **Metrics Calculator** (~80 LOC) - Sharpe, win rate, etc.
4. **Comparison Engine** (~50 LOC) - Multi-signal ranking
5. **Weight Optimizer** (~100 LOC) - Grid search + walk-forward

### Files to Create

- `scripts/backtest/engine.py` - Core backtest logic
- `scripts/backtest/data_loader.py` - Historical data loading
- `scripts/backtest/metrics.py` - Performance metric calculations
- `scripts/backtest/optimizer.py` - Weight optimization
- `scripts/backtest/__init__.py` - Public API
- `tests/test_backtest.py` - Test suite

### Files to Modify

- `scripts/init_metrics_db.py` - Add `backtest_results` table
- `api/main.py` - Add `/api/backtest/*` endpoints (optional)

### Algorithm: Sharpe Ratio

```python
def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0) -> float:
    """
    Calculate annualized Sharpe ratio.

    Sharpe = (mean(R) - Rf) / std(R) * sqrt(252)

    Where 252 = trading days per year (for daily returns)
    """
    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_return = variance ** 0.5

    if std_return == 0:
        return 0.0

    daily_sharpe = (mean_return - risk_free_rate) / std_return
    annualized_sharpe = daily_sharpe * (252 ** 0.5)  # Annualize

    return annualized_sharpe
```

### Algorithm: Max Drawdown

```python
def max_drawdown(equity_curve: list[float]) -> float:
    """
    Calculate maximum drawdown (peak-to-trough decline).

    Returns negative percentage (e.g., -0.15 = 15% drawdown)
    """
    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (value - peak) / peak
        if drawdown < max_dd:
            max_dd = drawdown

    return max_dd
```

### DuckDB Schema Extension

```sql
-- Add to scripts/init_metrics_db.py
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signal_source VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_return DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    win_rate DOUBLE,
    max_drawdown DOUBLE,
    profit_factor DOUBLE,
    num_trades INTEGER,
    config_json VARCHAR,  -- JSON serialized BacktestConfig
    trades_json VARCHAR   -- JSON serialized trades list
);

CREATE INDEX idx_backtest_signal ON backtest_results(signal_source);
CREATE INDEX idx_backtest_date ON backtest_results(start_date, end_date);
```

### Configuration

```bash
# .env additions
BACKTEST_DEFAULT_CAPITAL=10000
BACKTEST_TRANSACTION_COST=0.001
BACKTEST_BUY_THRESHOLD=0.3
BACKTEST_SELL_THRESHOLD=-0.3
BACKTEST_MIN_DAYS=30
```

### Dependencies

- **Internal**: DuckDB database, historical_data/
- **External**: None required (pure Python); pandas optional for convenience
- **Data**: Prices from DuckDB `prices` table or HTML files

---

## Out of Scope

- Live paper trading (future feature)
- Portfolio-level backtesting (multi-asset)
- Machine learning weight optimization (spec-011 mentions GA)
- Real-time backtest updates
- Visualization dashboard (CLI reports only)

---

## Future Extensions

- **spec-013**: Genetic algorithm weight optimization (evolutionary approach)
- Visualization dashboard for equity curves
- Monte Carlo simulation for confidence intervals
- Multi-timeframe backtesting (hourly, daily, weekly)
- Slippage modeling for large positions
