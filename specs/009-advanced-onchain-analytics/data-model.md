# Data Model: Advanced On-Chain Analytics

**Feature**: 009-advanced-onchain-analytics
**Version**: 1.0
**Last Updated**: 2025-12-04

## Overview

This document defines the data models for the three advanced on-chain analytics modules:
1. Power Law Detector
2. Symbolic Dynamics Processor
3. Fractal Dimension Analyzer

All models use Python dataclasses for simplicity and compatibility with existing spec-007 patterns.

---

## Core Data Models

### PowerLawResult

Captures the result of power law analysis on UTXO value distributions.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class PowerLawResult:
    """
    Result of power law fit to UTXO value distribution.

    Power law: P(x) ~ x^(-tau)

    Regime classification based on tau:
    - ACCUMULATION: tau < 1.8 (heavy tail, whale concentration)
    - NEUTRAL: 1.8 <= tau <= 2.2 (typical market)
    - DISTRIBUTION: tau > 2.2 (light tail, dispersion)
    """
    # Fit parameters
    tau: float                           # Power law exponent (typically 1.5-2.5)
    tau_std: float                       # Standard error of tau estimate
    xmin: float                          # Minimum value cutoff for fit

    # Validation
    ks_statistic: float                  # Kolmogorov-Smirnov test statistic
    ks_pvalue: float                     # KS test p-value (>0.05 = valid fit)
    is_valid: bool                       # True if fit passes KS test and sample size sufficient

    # Classification
    regime: str                          # "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION"
    power_law_vote: float                # Signal vote for fusion (-1 to +1)

    # Metadata
    sample_size: int                     # Number of UTXO values used
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Thresholds (configurable)
    TAU_ACCUMULATION_THRESHOLD: float = field(default=1.8, repr=False)
    TAU_DISTRIBUTION_THRESHOLD: float = field(default=2.2, repr=False)

    def __post_init__(self):
        """Validate and classify after initialization."""
        if self.sample_size < 100:
            self.is_valid = False

        # Classify regime based on tau
        if self.is_valid:
            if self.tau < self.TAU_ACCUMULATION_THRESHOLD:
                self.regime = "ACCUMULATION"
                # Vote strength proportional to deviation from neutral
                self.power_law_vote = min(1.0, (self.TAU_ACCUMULATION_THRESHOLD - self.tau) / 0.5)
            elif self.tau > self.TAU_DISTRIBUTION_THRESHOLD:
                self.regime = "DISTRIBUTION"
                self.power_law_vote = -min(1.0, (self.tau - self.TAU_DISTRIBUTION_THRESHOLD) / 0.5)
            else:
                self.regime = "NEUTRAL"
                self.power_law_vote = 0.0
        else:
            self.regime = "INVALID"
            self.power_law_vote = 0.0
```

### SymbolicDynamicsResult

Captures permutation entropy and statistical complexity of UTXO flow time series.

```python
@dataclass
class SymbolicDynamicsResult:
    """
    Result of symbolic dynamics analysis on UTXO flow time series.

    Permutation entropy H measures temporal complexity:
    - H ~ 0: Perfectly predictable (monotonic trend)
    - H ~ 1: Maximum entropy (random noise)

    Statistical complexity C measures structure:
    - C ~ 0: Simple (either ordered or random)
    - C ~ 0.5: Maximum complexity (edge of chaos)

    Pattern classification based on H-C plane:
    - ACCUMULATION_TREND: H < 0.4, positive slope
    - DISTRIBUTION_TREND: H < 0.4, negative slope
    - CHAOTIC_TRANSITION: H > 0.7
    - EDGE_OF_CHAOS: 0.4 <= H <= 0.7, C > 0.2
    """
    # Entropy metrics
    permutation_entropy: float           # Normalized entropy H in [0, 1]
    statistical_complexity: float        # Complexity C in [0, 0.5]

    # Configuration
    order: int                           # Embedding dimension d (default: 5)
    delay: int = 1                       # Time delay tau (default: 1)

    # Pattern analysis
    pattern_counts: dict = field(default_factory=dict)  # Frequency of each ordinal pattern
    n_patterns: int = 0                  # Total number of patterns observed
    dominant_pattern: str = ""           # Most frequent pattern (e.g., "01234")
    series_trend: float = 0.0            # Trend indicator: (second_half_mean - first_half_mean) / std

    # Classification
    complexity_class: str = ""           # "LOW" | "MEDIUM" | "HIGH"
    pattern_type: str = ""               # Trend classification
    symbolic_vote: float = 0.0           # Signal vote for fusion (-1 to +1)

    # Metadata
    series_length: int = 0               # Input series length
    is_valid: bool = True                # False if series too short
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Thresholds
    H_LOW_THRESHOLD: float = field(default=0.4, repr=False)
    H_HIGH_THRESHOLD: float = field(default=0.7, repr=False)
    C_EDGE_THRESHOLD: float = field(default=0.2, repr=False)

    def __post_init__(self):
        """Classify patterns after initialization."""
        # Validate series length
        import math
        min_length = 2 * math.factorial(self.order)
        if self.series_length < min_length:
            self.is_valid = False
            self.pattern_type = "INVALID"
            self.symbolic_vote = 0.0
            return

        # Classify complexity
        H = self.permutation_entropy
        C = self.statistical_complexity

        if H < self.H_LOW_THRESHOLD:
            self.complexity_class = "LOW"
            # Low entropy = trending behavior
            # Use series_trend to determine direction:
            # positive trend (second_half > first_half) = accumulation
            # negative trend (second_half < first_half) = distribution
            if self.series_trend >= 0:
                self.pattern_type = "ACCUMULATION_TREND"
                self.symbolic_vote = 0.8 * (1 - H / self.H_LOW_THRESHOLD)
            else:
                self.pattern_type = "DISTRIBUTION_TREND"
                self.symbolic_vote = -0.6 * (1 - H / self.H_LOW_THRESHOLD)
        elif H > self.H_HIGH_THRESHOLD:
            self.complexity_class = "HIGH"
            self.pattern_type = "CHAOTIC_TRANSITION"
            self.symbolic_vote = 0.0  # No directional signal in chaos
        else:
            self.complexity_class = "MEDIUM"
            if C > self.C_EDGE_THRESHOLD:
                self.pattern_type = "EDGE_OF_CHAOS"
                # Edge of chaos is interesting but not directional
                self.symbolic_vote = 0.0
            else:
                self.pattern_type = "TRANSITIONAL"
                self.symbolic_vote = 0.0
```

### FractalDimensionResult

Captures box-counting fractal dimension of UTXO value distributions.

```python
@dataclass
class FractalDimensionResult:
    """
    Result of fractal dimension analysis on UTXO value distribution.

    Box-counting dimension D measures self-similarity:
    - D = 0: Single point (all values identical)
    - D = 1: Line (uniform distribution)
    - D > 1: Space-filling (complex structure)

    Structure classification based on D:
    - WHALE_DOMINATED: D < 0.8 (concentrated in few clusters)
    - MIXED: 0.8 <= D <= 1.2 (typical market)
    - RETAIL_DOMINATED: D > 1.2 (highly dispersed)
    """
    # Dimension estimate
    dimension: float                     # Box-counting dimension D
    dimension_std: float                 # Standard error of D estimate

    # Fit quality
    r_squared: float                     # Goodness of fit (>0.9 required)
    is_valid: bool                       # True if R^2 > 0.9 and sufficient scales

    # Box-counting details
    scales_used: list = field(default_factory=list)   # Box sizes (epsilon values)
    counts: list = field(default_factory=list)        # Box counts N(epsilon)
    n_scales: int = 0                    # Number of scales used

    # Classification
    structure: str = ""                  # "WHALE_DOMINATED" | "MIXED" | "RETAIL_DOMINATED"
    fractal_vote: float = 0.0            # Signal vote for fusion (-1 to +1)

    # Metadata
    sample_size: int = 0                 # Number of UTXO values used
    value_range: tuple = (0.0, 0.0)      # (min, max) of input values
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Thresholds
    D_WHALE_THRESHOLD: float = field(default=0.8, repr=False)
    D_RETAIL_THRESHOLD: float = field(default=1.2, repr=False)
    R_SQUARED_MIN: float = field(default=0.9, repr=False)

    def __post_init__(self):
        """Classify structure after initialization."""
        # Validate fit quality
        if self.r_squared < self.R_SQUARED_MIN or self.n_scales < 5:
            self.is_valid = False
            self.structure = "INVALID"
            self.fractal_vote = 0.0
            return

        D = self.dimension

        if D < self.D_WHALE_THRESHOLD:
            self.structure = "WHALE_DOMINATED"
            # Whale concentration is generally bullish (smart money)
            self.fractal_vote = 0.5 * (self.D_WHALE_THRESHOLD - D) / self.D_WHALE_THRESHOLD
        elif D > self.D_RETAIL_THRESHOLD:
            self.structure = "RETAIL_DOMINATED"
            # Retail dispersion is neutral to slightly bearish
            self.fractal_vote = -0.3 * (D - self.D_RETAIL_THRESHOLD) / (2.0 - self.D_RETAIL_THRESHOLD)
        else:
            self.structure = "MIXED"
            self.fractal_vote = 0.0
```

### EnhancedFusionResult

Extended Monte Carlo fusion result incorporating all 7 signal components.

```python
@dataclass
class EnhancedFusionResult:
    """
    Result of enhanced Monte Carlo signal fusion with 7 components.

    Extends spec-007 MonteCarloFusionResult with:
    - Power Law vote (from this spec)
    - Symbolic Dynamics vote (from this spec)
    - Fractal Dimension vote (from this spec)

    Plus spec-008 derivatives:
    - Funding Rate vote
    - Open Interest vote
    """
    # Base Monte Carlo fields (from spec-007)
    signal_mean: float                   # Mean of bootstrap samples
    signal_std: float                    # Standard deviation
    ci_lower: float                      # 95% CI lower bound
    ci_upper: float                      # 95% CI upper bound
    action: str                          # "BUY" | "SELL" | "HOLD"
    action_confidence: float             # Probability action is correct
    n_samples: int                       # Number of bootstrap iterations
    distribution_type: str               # "unimodal" | "bimodal"

    # Component votes (None if unavailable)
    whale_vote: Optional[float] = None
    utxo_vote: Optional[float] = None
    funding_vote: Optional[float] = None     # spec-008
    oi_vote: Optional[float] = None          # spec-008
    power_law_vote: Optional[float] = None   # NEW - this spec
    symbolic_vote: Optional[float] = None    # NEW - this spec
    fractal_vote: Optional[float] = None     # NEW - this spec

    # Component weights (sum to 1.0 after renormalization)
    whale_weight: float = 0.25
    utxo_weight: float = 0.15
    funding_weight: float = 0.15
    oi_weight: float = 0.10
    power_law_weight: float = 0.10
    symbolic_weight: float = 0.15
    fractal_weight: float = 0.10

    # Metadata
    components_available: int = 0        # Count of valid components (0-7)
    components_used: list = field(default_factory=list)  # Names of components used
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def get_component_breakdown(self) -> dict:
        """Return dictionary of all components with votes and weights."""
        return {
            "whale": {"vote": self.whale_vote, "weight": self.whale_weight},
            "utxo": {"vote": self.utxo_vote, "weight": self.utxo_weight},
            "funding": {"vote": self.funding_vote, "weight": self.funding_weight},
            "oi": {"vote": self.oi_vote, "weight": self.oi_weight},
            "power_law": {"vote": self.power_law_vote, "weight": self.power_law_weight},
            "symbolic": {"vote": self.symbolic_vote, "weight": self.symbolic_weight},
            "fractal": {"vote": self.fractal_vote, "weight": self.fractal_weight},
        }
```

---

## DuckDB Schema Extension

Extend the existing `metrics` table from spec-007:

```sql
-- Add columns for advanced metrics
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS power_law_tau REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS power_law_regime TEXT;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS power_law_vote REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS power_law_valid BOOLEAN;

ALTER TABLE metrics ADD COLUMN IF NOT EXISTS symbolic_entropy REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS symbolic_complexity REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS symbolic_pattern TEXT;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS symbolic_vote REAL;

ALTER TABLE metrics ADD COLUMN IF NOT EXISTS fractal_dimension REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS fractal_structure TEXT;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS fractal_vote REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS fractal_valid BOOLEAN;

ALTER TABLE metrics ADD COLUMN IF NOT EXISTS enhanced_signal_mean REAL;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS enhanced_action TEXT;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS components_available INTEGER;

-- Create index for advanced metric queries
CREATE INDEX IF NOT EXISTS idx_metrics_power_law_regime ON metrics(power_law_regime);
CREATE INDEX IF NOT EXISTS idx_metrics_symbolic_pattern ON metrics(symbolic_pattern);
CREATE INDEX IF NOT EXISTS idx_metrics_fractal_structure ON metrics(fractal_structure);
```

---

## API Response Models

### AdvancedMetricsResponse

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PowerLawResponse(BaseModel):
    tau: float = Field(..., description="Power law exponent")
    tau_std: float = Field(..., description="Standard error of tau")
    regime: str = Field(..., description="ACCUMULATION | NEUTRAL | DISTRIBUTION")
    vote: float = Field(..., description="Signal vote (-1 to +1)")
    is_valid: bool = Field(..., description="True if fit is statistically valid")
    ks_pvalue: float = Field(..., description="KS test p-value")

class SymbolicDynamicsResponse(BaseModel):
    entropy: float = Field(..., description="Permutation entropy H in [0,1]")
    complexity: float = Field(..., description="Statistical complexity C")
    pattern_type: str = Field(..., description="Pattern classification")
    vote: float = Field(..., description="Signal vote (-1 to +1)")
    complexity_class: str = Field(..., description="LOW | MEDIUM | HIGH")

class FractalDimensionResponse(BaseModel):
    dimension: float = Field(..., description="Box-counting dimension D")
    dimension_std: float = Field(..., description="Standard error of D")
    structure: str = Field(..., description="WHALE_DOMINATED | MIXED | RETAIL_DOMINATED")
    vote: float = Field(..., description="Signal vote (-1 to +1)")
    is_valid: bool = Field(..., description="True if R^2 > 0.9")

class EnhancedFusionResponse(BaseModel):
    signal_mean: float = Field(..., description="Weighted mean of all signals")
    signal_std: float = Field(..., description="Standard deviation")
    ci_lower: float = Field(..., description="95% CI lower bound")
    ci_upper: float = Field(..., description="95% CI upper bound")
    action: str = Field(..., description="BUY | SELL | HOLD")
    action_confidence: float = Field(..., description="Confidence in action")
    components_available: int = Field(..., description="Number of valid components")

class AdvancedMetricsResponse(BaseModel):
    """Complete advanced metrics response for /api/metrics/advanced"""
    timestamp: datetime
    power_law: Optional[PowerLawResponse] = None
    symbolic_dynamics: Optional[SymbolicDynamicsResponse] = None
    fractal_dimension: Optional[FractalDimensionResponse] = None
    enhanced_fusion: Optional[EnhancedFusionResponse] = None

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-12-04T12:00:00Z",
                "power_law": {
                    "tau": 1.85,
                    "tau_std": 0.05,
                    "regime": "NEUTRAL",
                    "vote": 0.0,
                    "is_valid": True,
                    "ks_pvalue": 0.12
                },
                "symbolic_dynamics": {
                    "entropy": 0.35,
                    "complexity": 0.18,
                    "pattern_type": "ACCUMULATION_TREND",
                    "vote": 0.65,
                    "complexity_class": "LOW"
                },
                "fractal_dimension": {
                    "dimension": 0.72,
                    "dimension_std": 0.08,
                    "structure": "WHALE_DOMINATED",
                    "vote": 0.35,
                    "is_valid": True
                },
                "enhanced_fusion": {
                    "signal_mean": 0.58,
                    "signal_std": 0.12,
                    "ci_lower": 0.45,
                    "ci_upper": 0.71,
                    "action": "BUY",
                    "action_confidence": 0.82,
                    "components_available": 7
                }
            }
        }
```

---

## Validation Rules

### Power Law
- `sample_size >= 100` required for valid fit
- `ks_pvalue > 0.05` required for valid fit
- `tau` typically in range [1.2, 3.0]

### Symbolic Dynamics
- `series_length >= 2 * factorial(order)` required
- `order` typically 3-7 (default: 5)
- `permutation_entropy` in [0, 1]
- `statistical_complexity` in [0, 0.5]

### Fractal Dimension
- `n_scales >= 5` required
- `r_squared > 0.9` required for valid estimate
- `dimension` typically in [0.5, 2.0] for financial data
