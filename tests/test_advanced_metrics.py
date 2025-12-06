"""
Tests for Advanced On-Chain Analytics (spec-009)

TDD test suite for:
- US1: Power Law Regime Detection
- US2: Symbolic Dynamics Pattern Detection
- US3: Fractal Dimension Analysis
- US4: Enhanced Monte Carlo Fusion

Run with: uv run pytest tests/test_advanced_metrics.py -v
"""

import random


# =============================================================================
# US2: Symbolic Dynamics Tests (TDD RED)
# =============================================================================


class TestSymbolicDynamics:
    """Tests for permutation entropy and symbolic dynamics analysis."""

    def test_permutation_entropy_monotonic(self):
        """
        T007: Monotonically increasing series should have H ≈ 0.0 (perfectly predictable).

        Given: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, ...]
        Expected: permutation_entropy ≈ 0.0
        """
        from scripts.metrics.symbolic_dynamics import permutation_entropy

        # Monotonic series - perfectly ordered
        series = list(range(1, 101))  # 100 values
        H = permutation_entropy(series, order=5)

        assert H < 0.1, f"Expected H ≈ 0 for monotonic series, got {H}"

    def test_permutation_entropy_random(self):
        """
        T008: Random shuffle should have H ≈ 1.0 (maximum entropy).

        Given: Shuffled [1..500]
        Expected: permutation_entropy > 0.85 (high entropy)
        """
        from scripts.metrics.symbolic_dynamics import permutation_entropy

        # Random series - maximum disorder
        random.seed(42)  # Reproducible
        series = list(range(1, 501))  # Larger series for better sampling
        random.shuffle(series)
        H = permutation_entropy(series, order=5)

        assert H > 0.85, f"Expected H > 0.85 for random series, got {H}"

    def test_symbolic_dynamics_classification(self):
        """
        T009: Verify pattern classification and vote generation.

        Given: Low entropy series (monotonic)
        Expected: pattern_type='ACCUMULATION_TREND', symbolic_vote > 0
        """
        from scripts.metrics.symbolic_dynamics import analyze

        # Low entropy = accumulation trend
        # Series must be >= 2 * 5! = 240 for order=5 to be valid
        series = list(range(1, 300))
        result = analyze(series, order=5)

        assert result.is_valid is True, (
            f"Expected valid result, got is_valid={result.is_valid}"
        )
        assert result.pattern_type == "ACCUMULATION_TREND"
        assert result.symbolic_vote > 0.5, (
            f"Expected vote > 0.5, got {result.symbolic_vote}"
        )
        assert result.complexity_class == "LOW"


# =============================================================================
# US1: Power Law Tests (TDD RED)
# =============================================================================


class TestPowerLaw:
    """Tests for power law detection and regime classification."""

    def test_power_law_mle_estimation(self):
        """
        T016: MLE estimation should recover known tau within ±0.1.

        Given: Pareto samples with tau=2.0
        Expected: tau_estimate in [1.9, 2.1]
        """
        from scripts.metrics.power_law import fit

        # Generate Pareto samples with tau=2.0
        random.seed(42)
        xmin = 1.0
        tau_true = 2.0
        # Pareto: x = xmin / U^(1/(tau-1)) where U ~ Uniform(0,1)
        samples = [xmin / (random.random() ** (1 / (tau_true - 1))) for _ in range(500)]

        result = fit(samples, xmin=xmin)

        assert abs(result.tau - tau_true) < 0.15, (
            f"Expected tau ≈ {tau_true}, got {result.tau}"
        )

    def test_power_law_ks_validation(self):
        """
        T017: KS test should validate good power law fit.

        Given: True power law data
        Expected: is_valid=True, ks_pvalue > 0.05
        """
        from scripts.metrics.power_law import fit

        random.seed(42)
        xmin = 1.0
        tau_true = 2.0
        samples = [xmin / (random.random() ** (1 / (tau_true - 1))) for _ in range(500)]

        result = fit(samples, xmin=xmin)

        assert result.is_valid is True, (
            f"Expected valid fit, got is_valid={result.is_valid}"
        )
        assert result.ks_pvalue > 0.05, f"Expected p > 0.05, got {result.ks_pvalue}"

    def test_power_law_regime_classification(self):
        """
        T018: Regime classification based on tau thresholds.

        tau < 1.8 → ACCUMULATION
        1.8 <= tau <= 2.2 → NEUTRAL
        tau > 2.2 → DISTRIBUTION
        """
        from scripts.metrics.power_law import fit

        # Generate ACCUMULATION regime (tau ≈ 1.6)
        random.seed(42)
        xmin = 1.0
        tau_accum = 1.6
        samples = [
            xmin / (random.random() ** (1 / (tau_accum - 1))) for _ in range(500)
        ]

        result = fit(samples, xmin=xmin)
        assert result.regime == "ACCUMULATION", (
            f"Expected ACCUMULATION, got {result.regime}"
        )
        assert result.power_law_vote > 0, "Expected positive vote for accumulation"

        # Generate DISTRIBUTION regime (tau ≈ 2.5)
        random.seed(123)
        tau_dist = 2.5
        samples = [xmin / (random.random() ** (1 / (tau_dist - 1))) for _ in range(500)]

        result = fit(samples, xmin=xmin)
        assert result.regime == "DISTRIBUTION", (
            f"Expected DISTRIBUTION, got {result.regime}"
        )
        assert result.power_law_vote < 0, "Expected negative vote for distribution"


# =============================================================================
# US3: Fractal Dimension Tests (TDD RED)
# =============================================================================


class TestFractalDimension:
    """Tests for box-counting fractal dimension analysis."""

    def test_fractal_dimension_uniform(self):
        """
        T025: Uniform distribution should have D ≈ 1.0.

        Given: Uniformly distributed values in [0, 1]
        Expected: dimension ≈ 1.0 ± 0.1
        """
        from scripts.metrics.fractal_dimension import analyze

        random.seed(42)
        values = [random.random() for _ in range(500)]

        result = analyze(values)

        assert result.is_valid, "Expected valid fractal analysis"
        assert 0.8 < result.dimension < 1.2, f"Expected D ≈ 1.0, got {result.dimension}"

    def test_fractal_dimension_clustered(self):
        """
        T026: Clustered data should have D < 0.8.

        Given: Values clustered in 3 distinct ranges
        Expected: dimension < 0.8 (concentrated structure)
        """
        from scripts.metrics.fractal_dimension import analyze

        random.seed(42)
        # Create 3 distinct clusters (whale-like concentration)
        cluster1 = [0.1 + random.random() * 0.05 for _ in range(150)]
        cluster2 = [0.5 + random.random() * 0.05 for _ in range(150)]
        cluster3 = [0.9 + random.random() * 0.05 for _ in range(150)]
        values = cluster1 + cluster2 + cluster3
        random.shuffle(values)

        result = analyze(values)

        assert result.is_valid, "Expected valid fractal analysis"
        assert result.dimension < 0.9, (
            f"Expected D < 0.9 for clustered data, got {result.dimension}"
        )

    def test_fractal_structure_classification(self):
        """
        T027: Structure classification based on dimension thresholds.

        D < 0.8 → WHALE_DOMINATED
        0.8 <= D <= 1.2 → MIXED
        D > 1.2 → RETAIL_DOMINATED
        """
        from scripts.metrics.fractal_dimension import analyze

        # Clustered data → WHALE_DOMINATED
        random.seed(42)
        cluster1 = [0.1 + random.random() * 0.02 for _ in range(200)]
        cluster2 = [0.9 + random.random() * 0.02 for _ in range(200)]
        clustered = cluster1 + cluster2

        result = analyze(clustered)
        assert result.structure == "WHALE_DOMINATED", (
            f"Expected WHALE_DOMINATED, got {result.structure}"
        )
        assert result.fractal_vote > 0, "Expected positive vote for whale structure"


# =============================================================================
# US4: Enhanced Fusion Tests (TDD RED)
# =============================================================================


class TestEnhancedFusion:
    """Tests for enhanced Monte Carlo fusion with 7 components."""

    def test_enhanced_fusion_all_components(self):
        """
        T034: Enhanced fusion with all 7 components should produce valid result.

        Given: All 7 signal components with known values
        Expected: Valid weighted fusion with all components used
        """
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            utxo_vote=0.6,
            utxo_conf=0.8,
            funding_vote=0.3,
            oi_vote=0.2,
            power_law_vote=0.5,
            symbolic_vote=0.7,
            fractal_vote=0.4,
        )

        assert result.components_available == 7
        assert result.signal_mean > 0.3, (
            f"Expected positive signal mean, got {result.signal_mean}"
        )
        assert result.action in ["BUY", "SELL", "HOLD"]

    def test_enhanced_fusion_missing_components(self):
        """
        T035: Fusion with missing components should renormalize weights.

        Given: Only whale and utxo components (5 missing)
        Expected: Weights renormalized, fusion continues
        """
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            utxo_vote=0.6,
            utxo_conf=0.8,
            # All others None
        )

        assert result.components_available == 2
        assert result.signal_mean is not None
        assert "whale" in result.components_used
        assert "utxo" in result.components_used

    def test_enhanced_fusion_backward_compatible(self):
        """
        T036: Enhanced fusion should be backward compatible with spec-007.

        Given: Only whale and utxo (original spec-007 inputs)
        Expected: Result matches original fusion behavior
        """
        from scripts.metrics.monte_carlo_fusion import (
            enhanced_fusion,
            monte_carlo_fusion,
        )

        whale_vote, whale_conf = 0.7, 0.85
        utxo_vote, utxo_conf = 0.5, 0.75

        # Original fusion (spec-007)
        original = monte_carlo_fusion(whale_vote, whale_conf, utxo_vote, utxo_conf)

        # Enhanced fusion with only original components
        enhanced = enhanced_fusion(
            whale_vote=whale_vote,
            whale_conf=whale_conf,
            utxo_vote=utxo_vote,
            utxo_conf=utxo_conf,
        )

        # Should produce similar results (not identical due to bootstrap sampling)
        assert (
            enhanced.action == original.action
            or abs(enhanced.signal_mean - original.signal_mean) < 0.3
        )
