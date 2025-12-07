"""
Tests for Monte Carlo Fusion module (spec-007, spec-009, spec-014).

spec-014: Evidence-based weight adjustments.
TDD: These tests are written FIRST and must FAIL before implementation.
"""

import os
import pytest
from unittest.mock import patch


class TestEvidenceBasedWeights:
    """Tests for spec-014 evidence-based weights."""

    def test_evidence_based_weights_sum_to_one(self):
        """Evidence-based weights must sum to exactly 1.0."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        total = sum(EVIDENCE_BASED_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_legacy_weights_sum_to_one(self):
        """Legacy weights must sum to exactly 1.0."""
        from scripts.metrics.monte_carlo_fusion import LEGACY_WEIGHTS

        total = sum(LEGACY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_evidence_based_weights_funding_reduced(self):
        """Funding rate weight should be 0.05 (reduced from 0.15)."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        assert EVIDENCE_BASED_WEIGHTS["funding"] == 0.05, (
            f"Funding weight should be 0.05, got {EVIDENCE_BASED_WEIGHTS['funding']}"
        )

    def test_evidence_based_weights_whale_reduced(self):
        """Whale weight should be 0.15 (reduced from 0.25)."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        assert EVIDENCE_BASED_WEIGHTS["whale"] == 0.15, (
            f"Whale weight should be 0.15, got {EVIDENCE_BASED_WEIGHTS['whale']}"
        )

    def test_evidence_based_weights_utxo_increased(self):
        """UTXO weight should be 0.20 (increased from 0.15)."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        assert EVIDENCE_BASED_WEIGHTS["utxo"] == 0.20, (
            f"UTXO weight should be 0.20, got {EVIDENCE_BASED_WEIGHTS['utxo']}"
        )

    def test_evidence_based_weights_power_law_increased(self):
        """Power law weight should be 0.15 (increased from 0.10)."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        assert EVIDENCE_BASED_WEIGHTS["power_law"] == 0.15, (
            f"Power law weight should be 0.15, got {EVIDENCE_BASED_WEIGHTS['power_law']}"
        )

    def test_evidence_based_weights_has_wasserstein(self):
        """Evidence-based weights must include wasserstein component."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        assert "wasserstein" in EVIDENCE_BASED_WEIGHTS, (
            "Wasserstein component missing from evidence-based weights"
        )
        assert EVIDENCE_BASED_WEIGHTS["wasserstein"] == 0.10


class TestWeightValidation:
    """Tests for weight validation functions."""

    def test_weight_validation_accepts_valid_weights(self):
        """Validation should accept weights that sum to 1.0."""
        from scripts.metrics.monte_carlo_fusion import validate_weights

        valid_weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        assert validate_weights(valid_weights) is True

    def test_weight_validation_rejects_invalid_sum(self):
        """Validation should reject weights that don't sum to 1.0."""
        from scripts.metrics.monte_carlo_fusion import validate_weights

        invalid_weights = {"a": 0.5, "b": 0.3}  # Sum = 0.8
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_weights(invalid_weights)

    def test_weight_validation_rejects_negative_weights(self):
        """Validation should reject negative weight values."""
        from scripts.metrics.monte_carlo_fusion import validate_weights

        invalid_weights = {"a": 0.5, "b": 0.7, "c": -0.2}  # Sum = 1.0 but has negative
        with pytest.raises(ValueError, match="non-negative"):
            validate_weights(invalid_weights)

    def test_weight_validation_accepts_edge_case_tolerance(self):
        """Validation should accept weights within tolerance (0.001)."""
        from scripts.metrics.monte_carlo_fusion import validate_weights

        # Sum = 0.9999 (within tolerance)
        almost_valid = {"a": 0.33333, "b": 0.33333, "c": 0.33324}
        assert validate_weights(almost_valid) is True


class TestEnvironmentLoading:
    """Tests for environment-based weight loading."""

    def test_load_weights_from_env_default(self):
        """Default loading should return evidence-based weights."""
        from scripts.metrics.monte_carlo_fusion import (
            load_weights_from_env,
            EVIDENCE_BASED_WEIGHTS,
        )

        # Clear any env vars that might affect the test
        with patch.dict(os.environ, {}, clear=True):
            weights = load_weights_from_env()
            assert weights["funding"] == EVIDENCE_BASED_WEIGHTS["funding"]
            assert weights["whale"] == EVIDENCE_BASED_WEIGHTS["whale"]

    def test_load_weights_from_env_legacy_toggle(self):
        """FUSION_USE_LEGACY_WEIGHTS=true should return legacy weights."""
        from scripts.metrics.monte_carlo_fusion import (
            load_weights_from_env,
            LEGACY_WEIGHTS,
        )

        with patch.dict(os.environ, {"FUSION_USE_LEGACY_WEIGHTS": "true"}):
            weights = load_weights_from_env()
            assert weights == LEGACY_WEIGHTS

    def test_load_weights_from_env_custom_values(self):
        """Custom env vars should override default weights."""
        from scripts.metrics.monte_carlo_fusion import load_weights_from_env

        custom_env = {
            "FUSION_WHALE_WEIGHT": "0.10",
            "FUSION_UTXO_WEIGHT": "0.25",
            "FUSION_FUNDING_WEIGHT": "0.10",
            "FUSION_OI_WEIGHT": "0.10",
            "FUSION_POWER_LAW_WEIGHT": "0.10",
            "FUSION_SYMBOLIC_WEIGHT": "0.15",
            "FUSION_FRACTAL_WEIGHT": "0.10",
            "FUSION_WASSERSTEIN_WEIGHT": "0.10",
        }
        with patch.dict(os.environ, custom_env, clear=True):
            weights = load_weights_from_env()
            assert weights["whale"] == 0.10
            assert weights["utxo"] == 0.25


class TestFusionWithWeights:
    """Tests for enhanced fusion using evidence-based weights."""

    def test_enhanced_fusion_uses_evidence_based_by_default(self):
        """Enhanced fusion should use evidence-based weights by default."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        # Run fusion with all components
        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.9,
            utxo_vote=0.5,
            utxo_conf=0.9,
            funding_vote=0.5,
            oi_vote=0.5,
            power_law_vote=0.5,
            symbolic_vote=0.5,
            fractal_vote=0.5,
            wasserstein_vote=0.5,
            n_samples=100,
        )

        # Should use evidence-based weights (after normalization)
        # whale: 0.15, utxo: 0.20, funding: 0.05, etc.
        assert result.whale_weight < result.utxo_weight, (
            "UTXO should have higher weight than whale in evidence-based"
        )

    def test_enhanced_fusion_accepts_custom_weights(self):
        """Enhanced fusion should accept custom weight dict."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        custom_weights = {
            "whale": 0.50,
            "utxo": 0.50,
            "funding": 0.0,
            "oi": 0.0,
            "power_law": 0.0,
            "symbolic": 0.0,
            "fractal": 0.0,
            "wasserstein": 0.0,
        }

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=1.0,
            utxo_vote=0.2,
            utxo_conf=1.0,
            n_samples=100,
            weights=custom_weights,
        )

        # With 50/50 weights between whale (0.8) and utxo (0.2)
        # Mean should be around 0.5
        assert result.signal_mean is not None


class TestWeightConstants:
    """Tests verifying weight constant structure."""

    def test_evidence_based_weights_has_all_components(self):
        """Evidence-based weights must have all 8 components."""
        from scripts.metrics.monte_carlo_fusion import EVIDENCE_BASED_WEIGHTS

        required = [
            "whale",
            "utxo",
            "funding",
            "oi",
            "power_law",
            "symbolic",
            "fractal",
            "wasserstein",
        ]
        for component in required:
            assert component in EVIDENCE_BASED_WEIGHTS, (
                f"Missing component: {component}"
            )

    def test_legacy_weights_has_original_components(self):
        """Legacy weights should have original 7 components."""
        from scripts.metrics.monte_carlo_fusion import LEGACY_WEIGHTS

        required = [
            "whale",
            "utxo",
            "funding",
            "oi",
            "power_law",
            "symbolic",
            "fractal",
        ]
        for component in required:
            assert component in LEGACY_WEIGHTS, f"Missing component: {component}"
