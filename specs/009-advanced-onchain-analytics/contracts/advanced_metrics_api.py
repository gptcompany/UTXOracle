"""
API Contract: Advanced On-Chain Analytics

Feature: 009-advanced-onchain-analytics
Version: 1.0
Created: 2025-12-04

This module defines the public interfaces for the advanced on-chain analytics modules.
Implementations MUST conform to these interfaces.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


# =============================================================================
# Data Classes (Canonical Definitions)
# =============================================================================


@dataclass
class PowerLawResult:
    """Result of power law fit to UTXO value distribution."""

    tau: float
    tau_std: float
    xmin: float
    ks_statistic: float
    ks_pvalue: float
    is_valid: bool
    regime: str  # "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION"
    power_law_vote: float
    sample_size: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SymbolicDynamicsResult:
    """Result of symbolic dynamics analysis on time series."""

    permutation_entropy: float
    statistical_complexity: float
    order: int
    pattern_counts: dict
    dominant_pattern: str
    complexity_class: str  # "LOW" | "MEDIUM" | "HIGH"
    pattern_type: str  # "ACCUMULATION_TREND" | "DISTRIBUTION_TREND" | "CHAOTIC_TRANSITION" | "EDGE_OF_CHAOS"
    symbolic_vote: float
    series_length: int
    series_trend: float = (
        0.0  # Trend indicator: positive = accumulation, negative = distribution
    )
    is_valid: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FractalDimensionResult:
    """Result of fractal dimension analysis."""

    dimension: float
    dimension_std: float
    r_squared: float
    scales_used: list
    counts: list
    is_valid: bool
    structure: str  # "WHALE_DOMINATED" | "MIXED" | "RETAIL_DOMINATED"
    fractal_vote: float
    sample_size: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EnhancedFusionResult:
    """Result of enhanced Monte Carlo fusion with 7 components."""

    # Base Monte Carlo fields
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: str  # "BUY" | "SELL" | "HOLD"
    action_confidence: float
    n_samples: int
    distribution_type: str  # "unimodal" | "bimodal"

    # Component votes
    whale_vote: Optional[float] = None
    utxo_vote: Optional[float] = None
    funding_vote: Optional[float] = None
    oi_vote: Optional[float] = None
    power_law_vote: Optional[float] = None
    symbolic_vote: Optional[float] = None
    fractal_vote: Optional[float] = None

    # Component weights
    whale_weight: float = 0.25
    utxo_weight: float = 0.15
    funding_weight: float = 0.15
    oi_weight: float = 0.10
    power_law_weight: float = 0.10
    symbolic_weight: float = 0.15
    fractal_weight: float = 0.10

    # Metadata
    components_available: int = 0
    components_used: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# Protocol Definitions (Interfaces)
# =============================================================================


@runtime_checkable
class PowerLawDetector(Protocol):
    """
    Interface for power law detection on UTXO value distributions.

    Implementations MUST:
    - Use MLE for tau estimation
    - Validate fit using KS test
    - Return is_valid=False if sample_size < 100 or KS fails
    """

    def fit(self, values: list[float], xmin: Optional[float] = None) -> PowerLawResult:
        """
        Fit power law to value distribution.

        Args:
            values: List of UTXO values (satoshis or BTC)
            xmin: Minimum cutoff for fit (auto-detected if None)

        Returns:
            PowerLawResult with tau, validation metrics, and regime classification
        """
        ...

    def classify_regime(self, tau: float) -> tuple[str, float]:
        """
        Classify market regime based on tau.

        Args:
            tau: Power law exponent

        Returns:
            Tuple of (regime_name, vote)
            - regime_name: "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION"
            - vote: Signal vote in [-1, 1]
        """
        ...


@runtime_checkable
class SymbolicDynamicsProcessor(Protocol):
    """
    Interface for symbolic dynamics analysis.

    Implementations MUST:
    - Compute permutation entropy with configurable order
    - Compute statistical complexity for H-C classification
    - Return is_valid=False if series too short
    """

    def analyze(
        self, series: list[float], order: int = 5, delay: int = 1
    ) -> SymbolicDynamicsResult:
        """
        Analyze time series using symbolic dynamics.

        Args:
            series: Time series of UTXO flows or values
            order: Embedding dimension (default: 5)
            delay: Time delay (default: 1)

        Returns:
            SymbolicDynamicsResult with entropy, complexity, and pattern classification
        """
        ...

    def permutation_entropy(
        self, series: list[float], order: int = 5, delay: int = 1
    ) -> float:
        """
        Compute normalized permutation entropy.

        Args:
            series: Time series
            order: Embedding dimension
            delay: Time delay

        Returns:
            Normalized entropy H in [0, 1]
        """
        ...

    def statistical_complexity(self, pattern_distribution: dict[str, float]) -> float:
        """
        Compute statistical complexity from pattern distribution.

        Args:
            pattern_distribution: Dict mapping patterns to probabilities

        Returns:
            Complexity C in [0, 0.5]
        """
        ...


@runtime_checkable
class FractalDimensionAnalyzer(Protocol):
    """
    Interface for fractal dimension analysis.

    Implementations MUST:
    - Use box-counting algorithm
    - Validate fit quality (R^2 > 0.9)
    - Return is_valid=False if insufficient scales or poor fit
    """

    def analyze(
        self, values: list[float], min_scales: int = 5
    ) -> FractalDimensionResult:
        """
        Analyze value distribution using box-counting.

        Args:
            values: List of UTXO values
            min_scales: Minimum number of scales for valid fit

        Returns:
            FractalDimensionResult with dimension and structure classification
        """
        ...

    def box_count(self, values: list[float], epsilon: float) -> int:
        """
        Count boxes of size epsilon needed to cover the value set.

        Args:
            values: List of values
            epsilon: Box size

        Returns:
            Number of non-empty boxes
        """
        ...


@runtime_checkable
class EnhancedFusion(Protocol):
    """
    Interface for enhanced Monte Carlo fusion.

    Implementations MUST:
    - Support all 7 signal components
    - Renormalize weights when components unavailable
    - Maintain backward compatibility with spec-007 fusion
    """

    def fuse(
        self,
        whale_vote: Optional[float] = None,
        whale_conf: Optional[float] = None,
        utxo_vote: Optional[float] = None,
        utxo_conf: Optional[float] = None,
        funding_vote: Optional[float] = None,
        oi_vote: Optional[float] = None,
        power_law_result: Optional[PowerLawResult] = None,
        symbolic_result: Optional[SymbolicDynamicsResult] = None,
        fractal_result: Optional[FractalDimensionResult] = None,
        n_samples: int = 1000,
        weights: Optional[dict[str, float]] = None,
    ) -> EnhancedFusionResult:
        """
        Perform enhanced Monte Carlo fusion with all available components.

        Args:
            whale_vote: Whale flow vote (-1 to +1)
            whale_conf: Whale signal confidence (0 to 1)
            utxo_vote: UTXOracle vote (-1 to +1)
            utxo_conf: UTXOracle confidence (0 to 1)
            funding_vote: Funding rate vote (from spec-008)
            oi_vote: Open interest vote (from spec-008)
            power_law_result: Power law analysis result
            symbolic_result: Symbolic dynamics result
            fractal_result: Fractal dimension result
            n_samples: Number of bootstrap samples
            weights: Custom weights (default weights used if None)

        Returns:
            EnhancedFusionResult with combined signal and confidence intervals
        """
        ...


# =============================================================================
# Factory Functions (Convenience)
# =============================================================================


def create_power_law_detector() -> PowerLawDetector:
    """Factory function to create PowerLawDetector instance."""
    from scripts.metrics.power_law import PowerLawDetectorImpl

    return PowerLawDetectorImpl()


def create_symbolic_processor() -> SymbolicDynamicsProcessor:
    """Factory function to create SymbolicDynamicsProcessor instance."""
    from scripts.metrics.symbolic_dynamics import SymbolicDynamicsProcessorImpl

    return SymbolicDynamicsProcessorImpl()


def create_fractal_analyzer() -> FractalDimensionAnalyzer:
    """Factory function to create FractalDimensionAnalyzer instance."""
    from scripts.metrics.fractal_dimension import FractalDimensionAnalyzerImpl

    return FractalDimensionAnalyzerImpl()


def create_enhanced_fusion() -> EnhancedFusion:
    """Factory function to create EnhancedFusion instance."""
    from scripts.metrics.monte_carlo_fusion import EnhancedFusionImpl

    return EnhancedFusionImpl()


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_WEIGHTS = {
    "whale": 0.25,
    "utxo": 0.15,
    "funding": 0.15,
    "oi": 0.10,
    "power_law": 0.10,
    "symbolic": 0.15,
    "fractal": 0.10,
}

# Thresholds
POWER_LAW_MIN_SAMPLES = 100
POWER_LAW_KS_THRESHOLD = 0.05
POWER_LAW_TAU_ACCUMULATION = 1.8
POWER_LAW_TAU_DISTRIBUTION = 2.2

SYMBOLIC_DEFAULT_ORDER = 5
SYMBOLIC_H_LOW = 0.4
SYMBOLIC_H_HIGH = 0.7
SYMBOLIC_C_EDGE = 0.2

FRACTAL_MIN_SCALES = 5
FRACTAL_R_SQUARED_MIN = 0.9
FRACTAL_D_WHALE = 0.8
FRACTAL_D_RETAIL = 1.2
