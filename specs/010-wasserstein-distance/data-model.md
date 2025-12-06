# Data Model: Wasserstein Distance Calculator

**Feature**: spec-010 | **Date**: 2025-12-04

## Entities

### WassersteinResult

Single-pair distance calculation result.

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WassersteinResult:
    """Result of Wasserstein distance calculation between two distributions."""

    # Core metrics
    distance: float                   # W_1 distance (unnormalized)
    distance_normalized: float        # W_1 / max(range) for scale-invariance

    # Window metadata
    window_1_size: int               # Sample count in first window
    window_2_size: int               # Sample count in second window
    window_1_mean: float             # Mean of first distribution
    window_2_mean: float             # Mean of second distribution
    window_1_std: float              # Std of first distribution
    window_2_std: float              # Std of second distribution

    # Classification
    shift_direction: str             # "CONCENTRATION" | "DISPERSION" | "NONE"
    is_significant: bool             # True if distance > threshold
    is_valid: bool                   # True if both windows have sufficient samples

    # Validation
    min_samples: int = 50            # Minimum samples required
```

**Validation Rules**:
- `distance >= 0` (non-negative by definition)
- `distance_normalized in [0, 1]`
- `window_*_size >= min_samples` for `is_valid=True`
- `shift_direction in {"CONCENTRATION", "DISPERSION", "NONE"}`

**State Transitions**: None (stateless calculation)

---

### RollingWassersteinResult

Rolling window analysis result.

```python
@dataclass
class RollingWassersteinResult:
    """Result of rolling Wasserstein analysis over time series."""

    # Time series data
    distances: list[float]           # Rolling W values
    timestamps: list[datetime]       # Timestamp for each W value

    # Summary statistics
    mean_distance: float             # Average W over period
    max_distance: float              # Peak W (potential regime change)
    min_distance: float              # Minimum W (stable period)
    std_distance: float              # Stability measure

    # Regime detection
    sustained_shift_detected: bool   # True if 3+ consecutive high-W
    shift_windows: list[int]         # Indices where W > threshold
    regime_status: str               # "STABLE" | "TRANSITIONING" | "SHIFTED"

    # Signal output
    wasserstein_vote: float          # Signal vote (-1 to +1)
    vote_confidence: float           # Based on consistency of direction

    # Configuration used
    window_size: int                 # Blocks per window
    step_size: int                   # Blocks between windows
    threshold: float                 # Shift detection threshold

    # Metadata
    total_samples: int               # Total values analyzed
    windows_analyzed: int            # Number of window pairs compared
    is_valid: bool                   # True if sufficient data
```

**Validation Rules**:
- `len(distances) == len(timestamps)` (aligned arrays)
- `windows_analyzed >= 2` for meaningful analysis
- `regime_status in {"STABLE", "TRANSITIONING", "SHIFTED"}`
- `wasserstein_vote in [-1, 1]`

**State Transitions**:
```
STABLE ──(W > threshold for 1-2 windows)──> TRANSITIONING
TRANSITIONING ──(W > threshold for 3+ windows)──> SHIFTED
TRANSITIONING ──(W < threshold for 2+ windows)──> STABLE
SHIFTED ──(W < threshold for 5+ windows)──> STABLE
```

---

### EnhancedFusionResultV2

Extended fusion result with Wasserstein (8th component).

```python
@dataclass
class EnhancedFusionResultV2:
    """
    Extended Monte Carlo fusion with 8 signal components.
    Inherits all fields from EnhancedFusionResult (spec-009).
    """

    # Base Monte Carlo fields
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: str                       # "BUY" | "SELL" | "HOLD"
    action_confidence: float
    n_samples: int
    distribution_type: str            # "unimodal" | "bimodal" | "insufficient_data"

    # Component votes (all optional, None if unavailable)
    whale_vote: float | None
    utxo_vote: float | None
    funding_vote: float | None
    oi_vote: float | None
    power_law_vote: float | None
    symbolic_vote: float | None
    fractal_vote: float | None
    wasserstein_vote: float | None    # NEW (spec-010)

    # Component weights (after renormalization)
    whale_weight: float
    utxo_weight: float
    funding_weight: float
    oi_weight: float
    power_law_weight: float
    symbolic_weight: float
    fractal_weight: float
    wasserstein_weight: float         # NEW (spec-010)

    # Metadata
    components_available: int         # 0-8 (was 0-7)
    components_used: list[str]        # Names of components used
```

---

## Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                     Daily Analysis Pipeline                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  UTXO Values ─────┬────> WassersteinResult                      │
│  (from electrs)   │         │                                    │
│                   │         ▼                                    │
│                   │    RollingWassersteinResult                  │
│                   │         │                                    │
│                   │         │ wasserstein_vote                   │
│                   │         ▼                                    │
│                   └────> EnhancedFusionResultV2 <─── Other votes │
│                              │                                   │
│                              ▼                                   │
│                         DuckDB metrics table                     │
│                              │                                   │
│                              ▼                                   │
│                    /api/metrics/wasserstein                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema Extension

```sql
-- Extend existing metrics table or create new wasserstein_metrics table
-- Option: Add columns to existing metrics table

ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_distance DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_normalized DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_shift_direction VARCHAR;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_regime_status VARCHAR;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_vote DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_is_valid BOOLEAN;

-- Alternative: Dedicated table for rolling history
CREATE TABLE IF NOT EXISTS wasserstein_history (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    distance DOUBLE NOT NULL,
    distance_normalized DOUBLE,
    shift_direction VARCHAR,
    is_significant BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_wasserstein_timestamp ON wasserstein_history(timestamp);
```

---

## Default Weights (V2)

```python
# Updated weights for 8-component fusion (sum = 1.0)
ENHANCED_WEIGHTS_V2 = {
    "whale": 0.23,        # Primary signal (was 0.25)
    "utxo": 0.14,         # Price signal (was 0.15)
    "funding": 0.14,      # Derivatives (was 0.15)
    "oi": 0.09,           # Derivatives (was 0.10)
    "power_law": 0.09,    # Regime (was 0.10)
    "symbolic": 0.14,     # Temporal (was 0.15)
    "fractal": 0.09,      # Structure (was 0.10)
    "wasserstein": 0.08,  # Distribution shift (NEW)
}
```

---

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WASSERSTEIN_ENABLED` | `true` | Enable Wasserstein calculation |
| `WASSERSTEIN_WINDOW_SIZE` | `144` | Blocks per window (~24h) |
| `WASSERSTEIN_STEP_SIZE` | `6` | Blocks between windows (~1h) |
| `WASSERSTEIN_SHIFT_THRESHOLD` | `0.10` | W > this = significant shift |
| `WASSERSTEIN_MIN_SAMPLES` | `50` | Minimum samples per window |
| `WASSERSTEIN_SUSTAINED_COUNT` | `3` | Consecutive windows for sustained |
| `WASSERSTEIN_WEIGHT` | `0.08` | Weight in enhanced fusion |
