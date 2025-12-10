"""
Tests for Monte Carlo Fusion module (spec-007, spec-009, spec-019).

spec-019: Derivatives weight reduction + SOPR integration.
"""

import pytest
from scripts.metrics.monte_carlo_fusion import (
    ENHANCED_WEIGHTS,
    enhanced_fusion,
    sopr_to_vote,
    monte_carlo_fusion,
    detect_bimodal,
    determine_action,
)


class TestEnhancedWeights:
    """Tests for spec-019 enhanced weights."""

    def test_weights_sum_to_one(self):
        """Enhanced weights must sum to exactly 1.0."""
        total = sum(ENHANCED_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_weights_has_all_11_components(self):
        """Enhanced weights must have all 11 components (spec-020)."""
        required = [
            "whale",
            "utxo",
            "funding",
            "oi",
            "power_law",
            "symbolic",
            "fractal",
            "wasserstein",
            "cointime",
            "sopr",
            "mvrv_z",  # spec-020
        ]
        for component in required:
            assert component in ENHANCED_WEIGHTS, f"Missing component: {component}"

    def test_derivatives_weight_reduced(self):
        """Derivatives (funding+oi) weight should be 10% (reduced from 21%)."""
        derivatives_total = ENHANCED_WEIGHTS["funding"] + ENHANCED_WEIGHTS["oi"]
        assert derivatives_total == pytest.approx(0.10, rel=0.01), (
            f"Derivatives weight should be 0.10, got {derivatives_total}"
        )

    def test_funding_weight_is_005(self):
        """Funding rate weight should be 0.05 (reduced from 0.12)."""
        assert ENHANCED_WEIGHTS["funding"] == 0.05, (
            f"Funding weight should be 0.05, got {ENHANCED_WEIGHTS['funding']}"
        )

    def test_oi_weight_is_005(self):
        """Open interest weight should be 0.05 (reduced from 0.09)."""
        assert ENHANCED_WEIGHTS["oi"] == 0.05, (
            f"OI weight should be 0.05, got {ENHANCED_WEIGHTS['oi']}"
        )

    def test_whale_weight_increased(self):
        """Whale weight should be 0.24 (increased from 0.21)."""
        assert ENHANCED_WEIGHTS["whale"] == 0.24, (
            f"Whale weight should be 0.24, got {ENHANCED_WEIGHTS['whale']}"
        )

    def test_wasserstein_weight_increased(self):
        """Wasserstein weight should be 0.08 (increased from 0.04)."""
        assert ENHANCED_WEIGHTS["wasserstein"] == 0.08, (
            f"Wasserstein weight should be 0.08, got {ENHANCED_WEIGHTS['wasserstein']}"
        )

    def test_cointime_weight_increased(self):
        """Cointime weight should be 0.14 (increased from 0.12)."""
        assert ENHANCED_WEIGHTS["cointime"] == 0.14, (
            f"Cointime weight should be 0.14, got {ENHANCED_WEIGHTS['cointime']}"
        )

    def test_sopr_weight_is_002(self):
        """SOPR weight should be 0.02 (NEW in spec-019)."""
        assert ENHANCED_WEIGHTS["sopr"] == 0.02, (
            f"SOPR weight should be 0.02, got {ENHANCED_WEIGHTS['sopr']}"
        )

    def test_all_weights_non_negative(self):
        """All weights must be non-negative."""
        for name, weight in ENHANCED_WEIGHTS.items():
            assert weight >= 0, f"Weight {name} is negative: {weight}"


class TestSoprToVote:
    """Tests for SOPR to vote conversion (spec-019)."""

    def test_sopr_neutral_at_one(self):
        """SOPR = 1.0 should return neutral vote (0.0)."""
        vote, conf = sopr_to_vote(1.0, 0.9)
        assert vote == 0.0
        assert conf == 0.9

    def test_sopr_bullish_below_one(self):
        """SOPR < 1.0 (capitulation) should return positive vote (bullish)."""
        vote, conf = sopr_to_vote(0.95, 0.8)
        assert vote > 0, f"Vote should be positive for SOPR < 1.0, got {vote}"
        assert conf == 0.8

    def test_sopr_bearish_above_one(self):
        """SOPR > 1.0 (profit taking) should return negative vote (bearish)."""
        vote, conf = sopr_to_vote(1.05, 0.85)
        assert vote < 0, f"Vote should be negative for SOPR > 1.0, got {vote}"
        assert conf == 0.85

    def test_sopr_vote_clamped_to_08(self):
        """Vote should be clamped to [-0.8, 0.8] range."""
        # Extreme bullish case
        vote_bull, _ = sopr_to_vote(0.5, 1.0)
        assert vote_bull <= 0.8, f"Vote should be clamped to 0.8, got {vote_bull}"

        # Extreme bearish case
        vote_bear, _ = sopr_to_vote(1.5, 1.0)
        assert vote_bear >= -0.8, f"Vote should be clamped to -0.8, got {vote_bear}"

    def test_sopr_vote_scaling(self):
        """Vote should scale proportionally with SOPR deviation from 1.0."""
        vote_small, _ = sopr_to_vote(0.98, 1.0)  # Small deviation
        vote_large, _ = sopr_to_vote(0.90, 1.0)  # Large deviation
        assert vote_large > vote_small, "Larger deviation should give larger vote"


class TestEnhancedFusionWithSopr:
    """Tests for enhanced fusion with SOPR integration (spec-019)."""

    def test_fusion_accepts_sopr_parameters(self):
        """Enhanced fusion should accept sopr_vote and sopr_conf parameters."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            sopr_vote=0.6,
            sopr_conf=0.85,
            n_samples=100,
        )
        assert result is not None
        assert result.sopr_vote == 0.6
        assert result.sopr_weight > 0

    def test_fusion_sopr_weight_in_result(self):
        """Result should include sopr_weight field."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            sopr_vote=0.6,
            sopr_conf=0.85,
            n_samples=100,
        )
        assert hasattr(result, "sopr_weight")
        assert 0 <= result.sopr_weight <= 1

    def test_fusion_sopr_in_components_used(self):
        """SOPR should appear in components_used when provided."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            sopr_vote=0.6,
            sopr_conf=0.85,
            n_samples=100,
        )
        assert "sopr" in result.components_used

    def test_fusion_without_sopr_backward_compatible(self):
        """Fusion should work without SOPR parameters (backward compatibility)."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            utxo_vote=0.5,
            utxo_conf=0.9,
            n_samples=100,
        )
        assert result is not None
        assert result.sopr_vote is None
        assert result.sopr_weight == 0.0
        assert "sopr" not in result.components_used


class TestEnhancedFusionGeneral:
    """General tests for enhanced fusion."""

    def test_fusion_accepts_custom_weights(self):
        """Enhanced fusion should accept custom weight dict."""
        custom_weights = {
            "whale": 0.50,
            "utxo": 0.50,
            "funding": 0.0,
            "oi": 0.0,
            "power_law": 0.0,
            "symbolic": 0.0,
            "fractal": 0.0,
            "wasserstein": 0.0,
            "cointime": 0.0,
            "sopr": 0.0,
        }

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=1.0,
            utxo_vote=0.2,
            utxo_conf=1.0,
            n_samples=100,
            weights=custom_weights,
        )
        assert result.signal_mean is not None

    def test_fusion_returns_valid_action(self):
        """Fusion should return valid action (BUY/SELL/HOLD)."""
        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            n_samples=100,
        )
        assert result.action in ["BUY", "SELL", "HOLD"]

    def test_fusion_returns_valid_confidence(self):
        """Action confidence should be between 0 and 1."""
        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            n_samples=100,
        )
        assert 0 <= result.action_confidence <= 1

    def test_fusion_no_components_returns_hold(self):
        """Fusion with no components should return HOLD with 0 confidence."""
        result = enhanced_fusion(n_samples=100)
        assert result.action == "HOLD"
        assert result.action_confidence == 0.0
        assert result.components_available == 0


class TestMonteCarloFusionLegacy:
    """Tests for legacy 2-component Monte Carlo fusion (spec-007)."""

    def test_legacy_fusion_returns_result(self):
        """Legacy fusion should return MonteCarloFusionResult."""
        result = monte_carlo_fusion(
            whale_vote=0.8,
            whale_confidence=0.9,
            utxo_vote=0.6,
            utxo_confidence=0.85,
            n_samples=100,
        )
        assert result is not None
        assert hasattr(result, "signal_mean")
        assert hasattr(result, "action")

    def test_legacy_fusion_action_valid(self):
        """Legacy fusion should return valid action."""
        result = monte_carlo_fusion(
            whale_vote=0.8,
            whale_confidence=0.9,
            utxo_vote=0.6,
            utxo_confidence=0.85,
            n_samples=100,
        )
        assert result.action in ["BUY", "SELL", "HOLD"]


class TestDetectBimodal:
    """Tests for bimodal distribution detection."""

    def test_insufficient_data(self):
        """Small sample should return insufficient_data."""
        result = detect_bimodal([0.1, 0.2, 0.3])
        assert result == "insufficient_data"

    def test_unimodal_distribution(self):
        """Normal distribution should be detected as unimodal."""
        import random

        random.seed(42)
        samples = [random.gauss(0.5, 0.1) for _ in range(100)]
        result = detect_bimodal(samples)
        assert result == "unimodal"


class TestDetermineAction:
    """Tests for action determination."""

    def test_buy_action_positive_mean(self):
        """Positive mean above threshold should return BUY."""
        action, _ = determine_action(0.6, 0.4, 0.8)
        assert action == "BUY"

    def test_sell_action_negative_mean(self):
        """Negative mean below threshold should return SELL."""
        action, _ = determine_action(-0.6, -0.8, -0.4)
        assert action == "SELL"

    def test_hold_action_neutral_mean(self):
        """Neutral mean should return HOLD."""
        action, _ = determine_action(0.1, -0.1, 0.3)
        assert action == "HOLD"


# =============================================================================
# Phase 7: FR-005 - MVRV-Z Fusion Tests (T035-T041) - spec-020
# =============================================================================


class TestMVRVFusion:
    """Tests for MVRV-Z integration into enhanced fusion (spec-020)."""

    def test_weights_sum_to_one_with_mvrv_z(self):
        """T035: Enhanced weights including mvrv_z must sum to 1.0."""
        total = sum(ENHANCED_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_mvrv_z_vote_integration(self):
        """T036: Fusion should accept mvrv_z_vote and mvrv_z_conf parameters."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            mvrv_z_vote=0.7,
            mvrv_z_conf=0.85,
            n_samples=100,
        )
        assert result is not None
        assert result.mvrv_z_vote == 0.7
        assert result.mvrv_z_weight > 0

    def test_mvrv_z_optional(self):
        """T037: Fusion should work without mvrv_z parameters (backward compatible)."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            utxo_vote=0.5,
            utxo_conf=0.9,
            n_samples=100,
        )
        assert result is not None
        assert result.mvrv_z_vote is None
        assert result.mvrv_z_weight == 0.0
        assert "mvrv_z" not in result.components_used

    def test_mvrv_z_in_components_used(self):
        """T036b: mvrv_z should appear in components_used when provided."""
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            mvrv_z_vote=0.6,
            mvrv_z_conf=0.8,
            n_samples=100,
        )
        assert "mvrv_z" in result.components_used

    def test_mvrv_z_affects_signal(self):
        """Strong mvrv_z signal should influence the fused result."""
        # Without mvrv_z
        result_without = enhanced_fusion(
            whale_vote=0.0,
            whale_conf=1.0,
            n_samples=500,
        )

        # With strong mvrv_z
        result_with = enhanced_fusion(
            whale_vote=0.0,
            whale_conf=1.0,
            mvrv_z_vote=0.9,
            mvrv_z_conf=1.0,
            n_samples=500,
        )

        # The mvrv_z should pull the signal in positive direction
        assert result_with.signal_mean > result_without.signal_mean
