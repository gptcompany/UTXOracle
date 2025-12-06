# Data Model: Derivatives Historical Integration

**Feature**: 008-derivatives-historical
**Date**: 2025-12-03

## Entity Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LiquidationHeatmap DuckDB                          │
│                    (External - READ_ONLY via ATTACH)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────┐      ┌───────────────────────────┐         │
│  │   funding_rate_history    │      │   open_interest_history   │         │
│  ├───────────────────────────┤      ├───────────────────────────┤         │
│  │ timestamp: TIMESTAMP      │      │ timestamp: TIMESTAMP      │         │
│  │ symbol: VARCHAR           │      │ symbol: VARCHAR           │         │
│  │ funding_rate: DECIMAL     │      │ open_interest_value: DEC  │         │
│  │ funding_interval_hours: INT│     │ oi_delta: DECIMAL         │         │
│  └───────────┬───────────────┘      └───────────┬───────────────┘         │
│              │                                  │                          │
└──────────────┼──────────────────────────────────┼──────────────────────────┘
               │                                  │
               │  DuckDB ATTACH (READ_ONLY)       │
               ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            UTXOracle Application                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────┐      ┌───────────────────────────┐         │
│  │    FundingRateSignal      │      │    OpenInterestSignal     │         │
│  │    (Python dataclass)     │      │    (Python dataclass)     │         │
│  ├───────────────────────────┤      ├───────────────────────────┤         │
│  │ timestamp: datetime       │      │ timestamp: datetime       │         │
│  │ symbol: str               │      │ symbol: str               │         │
│  │ exchange: str             │      │ exchange: str             │         │
│  │ funding_rate: float       │      │ oi_value: float           │         │
│  │ funding_vote: float       │◄────►│ oi_change_1h: float       │         │
│  │ is_extreme: bool          │      │ oi_vote: float            │         │
│  └───────────┬───────────────┘      │ context: str              │         │
│              │                      └───────────┬───────────────┘         │
│              │                                  │                          │
│              └────────────┬─────────────────────┘                          │
│                           ▼                                                 │
│              ┌───────────────────────────┐                                 │
│              │   EnhancedFusionResult    │                                 │
│              │    (Python dataclass)     │                                 │
│              ├───────────────────────────┤                                 │
│              │ signal_mean: float        │  Extends spec-007              │
│              │ signal_std: float         │  MonteCarloFusionResult        │
│              │ ci_lower: float           │                                 │
│              │ ci_upper: float           │                                 │
│              │ action: str               │                                 │
│              │ action_confidence: float  │                                 │
│              │ whale_vote: float         │                                 │
│              │ whale_weight: float       │                                 │
│              │ utxo_vote: float          │                                 │
│              │ utxo_weight: float        │                                 │
│              │ funding_vote: float|None  │                                 │
│              │ funding_weight: float     │                                 │
│              │ oi_vote: float|None       │                                 │
│              │ oi_weight: float          │                                 │
│              │ derivatives_available: bool│                                │
│              │ data_freshness_minutes: int│                                │
│              └───────────┬───────────────┘                                 │
│                          │                                                  │
│                          ▼                                                  │
│              ┌───────────────────────────┐                                 │
│              │      BacktestResult       │                                 │
│              │    (Python dataclass)     │                                 │
│              ├───────────────────────────┤                                 │
│              │ start_date: datetime      │                                 │
│              │ end_date: datetime        │                                 │
│              │ total_signals: int        │                                 │
│              │ win_rate: float           │                                 │
│              │ sharpe_ratio: float       │                                 │
│              │ max_drawdown: float       │                                 │
│              │ optimal_weights: dict|None│                                 │
│              └───────────────────────────┘                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Entity Definitions

### FundingRateSignal

Represents a funding rate reading with contrarian signal vote.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class FundingRateSignal:
    """
    Funding rate signal from derivatives exchange.

    The funding_vote is a CONTRARIAN signal:
    - Positive funding (longs pay) → negative vote (bearish)
    - Negative funding (shorts pay) → positive vote (bullish)

    Attributes:
        timestamp: When the funding rate was collected
        symbol: Trading pair (e.g., "BTCUSDT")
        exchange: Source exchange (e.g., "binance")
        funding_rate: Raw rate (e.g., 0.0015 = 0.15%)
        funding_vote: Contrarian signal in [-1.0, 1.0]
        is_extreme: True if |rate| exceeds normal bounds
    """

    timestamp: datetime
    symbol: str
    exchange: str
    funding_rate: float
    funding_vote: float
    is_extreme: bool

    def __post_init__(self):
        """Validate vote bounds."""
        if not -1.0 <= self.funding_vote <= 1.0:
            raise ValueError(f"funding_vote out of range: {self.funding_vote}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "funding_rate": self.funding_rate,
            "funding_vote": self.funding_vote,
            "is_extreme": self.is_extreme,
        }
```

### OpenInterestSignal

Represents open interest with change calculation and context.

```python
@dataclass
class OpenInterestSignal:
    """
    Open Interest signal from derivatives exchange.

    The oi_vote depends on OI change direction AND whale signal context:
    - Rising OI + whale accumulation = confirming (bullish)
    - Rising OI + whale distribution = diverging (potential squeeze)
    - Falling OI = deleveraging (neutral)

    Attributes:
        timestamp: When OI was measured
        symbol: Trading pair (e.g., "BTCUSDT")
        exchange: Source exchange (e.g., "binance")
        oi_value: Absolute OI in USD
        oi_change_1h: Percentage change in last 1 hour
        oi_change_24h: Percentage change in last 24 hours
        oi_vote: Context-aware signal in [-1.0, 1.0]
        context: Relationship to whale signal
    """

    timestamp: datetime
    symbol: str
    exchange: str
    oi_value: float
    oi_change_1h: float
    oi_change_24h: float
    oi_vote: float
    context: Literal["confirming", "diverging", "deleveraging", "neutral", "no_data"]

    def __post_init__(self):
        """Validate vote bounds and context."""
        if not -1.0 <= self.oi_vote <= 1.0:
            raise ValueError(f"oi_vote out of range: {self.oi_vote}")
        valid_contexts = {"confirming", "diverging", "deleveraging", "neutral", "no_data"}
        if self.context not in valid_contexts:
            raise ValueError(f"Invalid context: {self.context}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "oi_value": self.oi_value,
            "oi_change_1h": self.oi_change_1h,
            "oi_change_24h": self.oi_change_24h,
            "oi_vote": self.oi_vote,
            "context": self.context,
        }
```

### EnhancedFusionResult

Extends MonteCarloFusionResult with derivatives components.

```python
from typing import Optional


@dataclass
class EnhancedFusionResult:
    """
    Result of 4-component Monte Carlo signal fusion.

    Extends spec-007 MonteCarloFusionResult with derivatives signals:
    whale (on-chain) + utxo (price confidence) + funding + oi.

    Attributes:
        signal_mean: Mean of bootstrap samples (-1.0 to 1.0)
        signal_std: Standard deviation of samples
        ci_lower: 95% confidence interval lower bound
        ci_upper: 95% confidence interval upper bound
        action: Trading action (BUY/SELL/HOLD)
        action_confidence: Probability action is correct (0.0 to 1.0)
        n_samples: Number of bootstrap iterations

        # Component breakdown
        whale_vote: Whale flow signal (-1.0 to 1.0)
        whale_weight: Weight applied to whale signal
        utxo_vote: UTXOracle confidence signal
        utxo_weight: Weight applied to UTXOracle signal
        funding_vote: Funding rate contrarian signal (None if unavailable)
        funding_weight: Weight applied to funding signal
        oi_vote: Open interest signal (None if unavailable)
        oi_weight: Weight applied to OI signal

        # Metadata
        derivatives_available: True if both funding and OI were used
        data_freshness_minutes: Age of newest derivatives data point
        distribution_type: Shape of distribution (unimodal/bimodal)
    """

    # Core Monte Carlo fields (from spec-007)
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: Literal["BUY", "SELL", "HOLD"]
    action_confidence: float
    n_samples: int = 1000

    # Component breakdown
    whale_vote: float = 0.0
    whale_weight: float = 0.40
    utxo_vote: float = 0.0
    utxo_weight: float = 0.20
    funding_vote: Optional[float] = None
    funding_weight: float = 0.25
    oi_vote: Optional[float] = None
    oi_weight: float = 0.15

    # Metadata
    derivatives_available: bool = False
    data_freshness_minutes: int = 0
    distribution_type: Literal["unimodal", "bimodal", "insufficient_data"] = "unimodal"

    def __post_init__(self):
        """Validate signal and confidence bounds."""
        if not -1.0 <= self.signal_mean <= 1.0:
            raise ValueError(f"signal_mean out of range: {self.signal_mean}")
        if not 0.0 <= self.action_confidence <= 1.0:
            raise ValueError(f"action_confidence out of range: {self.action_confidence}")

        # Validate weights sum to ~1.0
        total_weight = self.whale_weight + self.utxo_weight
        if self.funding_vote is not None:
            total_weight += self.funding_weight
        if self.oi_vote is not None:
            total_weight += self.oi_weight

        # Allow small tolerance for rounding
        if not 0.99 <= total_weight <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "signal_mean": self.signal_mean,
            "signal_std": self.signal_std,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "action": self.action,
            "action_confidence": self.action_confidence,
            "n_samples": self.n_samples,
            "components": {
                "whale": {"vote": self.whale_vote, "weight": self.whale_weight},
                "utxo": {"vote": self.utxo_vote, "weight": self.utxo_weight},
                "funding": {"vote": self.funding_vote, "weight": self.funding_weight},
                "oi": {"vote": self.oi_vote, "weight": self.oi_weight},
            },
            "derivatives_available": self.derivatives_available,
            "data_freshness_minutes": self.data_freshness_minutes,
            "distribution_type": self.distribution_type,
        }
```

### BacktestResult

Results from historical backtesting.

```python
@dataclass
class BacktestResult:
    """
    Results from backtesting the enhanced signal fusion.

    Provides performance metrics for evaluating signal quality
    on historical data.

    Attributes:
        start_date: Backtest period start
        end_date: Backtest period end
        total_signals: Total signals generated
        buy_signals: Count of BUY signals
        sell_signals: Count of SELL signals
        hold_signals: Count of HOLD signals
        win_rate: Percentage of correct directional calls
        total_return: Cumulative return if following signals
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown: Worst peak-to-trough decline
        optimal_weights: Best weights from optimization (if run)
    """

    start_date: datetime
    end_date: datetime
    total_signals: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    win_rate: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    optimal_weights: Optional[dict] = None

    def __post_init__(self):
        """Validate metrics."""
        if not 0.0 <= self.win_rate <= 1.0:
            raise ValueError(f"win_rate must be 0-1, got {self.win_rate}")
        if self.total_signals != self.buy_signals + self.sell_signals + self.hold_signals:
            raise ValueError("Signal counts don't match total")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "period": {
                "start": self.start_date.isoformat(),
                "end": self.end_date.isoformat(),
            },
            "signals": {
                "total": self.total_signals,
                "buy": self.buy_signals,
                "sell": self.sell_signals,
                "hold": self.hold_signals,
            },
            "performance": {
                "win_rate": self.win_rate,
                "total_return": self.total_return,
                "sharpe_ratio": self.sharpe_ratio,
                "max_drawdown": self.max_drawdown,
            },
            "optimal_weights": self.optimal_weights,
        }
```

## Database Schema (No New Tables)

**This feature does NOT create new database tables.**

Data is read from LiquidationHeatmap via DuckDB ATTACH. Results are:
1. Returned in API response (transient)
2. Optionally logged to backtest output file (JSON)

Future extension (spec-009) may add:
- `enhanced_signal_history` table for storing real-time signals
- `backtest_runs` table for storing backtest results

## Validation Rules

### FundingRateSignal
- `funding_vote` MUST be in [-1.0, 1.0]
- `funding_rate` raw value preserved for transparency
- `is_extreme` calculated from thresholds (±0.1% positive, ±0.05% negative)

### OpenInterestSignal
- `oi_vote` MUST be in [-1.0, 1.0]
- `context` MUST be one of: "confirming", "diverging", "deleveraging", "neutral", "no_data"
- `oi_value` MUST be positive (USD notional)

### EnhancedFusionResult
- All spec-007 MonteCarloFusionResult validations apply
- Active weights MUST sum to 1.0 (components with None vote are excluded)
- `derivatives_available` = True only if both funding AND oi have values

### BacktestResult
- `win_rate` MUST be in [0.0, 1.0]
- Signal counts MUST sum to total_signals
- `sharpe_ratio` can be negative (poor performance)
- `max_drawdown` should be negative (represents loss)

## State Transitions

### Signal Availability States

```
                 ┌──────────────────┐
                 │    FULL_MODE     │
                 │ (4 components)   │
                 │ whale+utxo+      │
                 │ funding+oi       │
                 └────────┬─────────┘
                          │
         LiquidationHeatmap unavailable
                          │
                          ▼
                 ┌──────────────────┐
                 │  DEGRADED_MODE   │
                 │ (2 components)   │
                 │ whale+utxo only  │
                 └──────────────────┘
```

### Backtest States

```
   ┌────────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
   │   START    │────►│  LOADING   │────►│  RUNNING   │────►│  COMPLETE  │
   │            │     │  DATA      │     │  SIGNALS   │     │  REPORT    │
   └────────────┘     └────────────┘     └────────────┘     └────────────┘
                            │                  │
                            │                  │ Error
                            ▼                  ▼
                      ┌────────────┐     ┌────────────┐
                      │   ERROR    │     │  PARTIAL   │
                      │  NO DATA   │     │  RESULTS   │
                      └────────────┘     └────────────┘
```
