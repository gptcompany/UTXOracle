"""Tests for Metrics Models.

Spec: spec-017, spec-020
TDD approach: RED phase tests for dataclass logic.
"""

from __future__ import annotations


from scripts.models.metrics_models import (
    AgeCohortsConfig,
)


# =============================================================================
# T003a: Test AgeCohortsConfig.classify() boundary logic
# =============================================================================


class TestAgeCohortsConfig:
    """Test age cohort classification logic."""

    def test_classify_sth_lth_boundary(self):
        """Test STH/LTH boundary at 155 days.

        T003a: Verify that:
        - age < 155 days -> STH
        - age >= 155 days -> LTH
        """
        config = AgeCohortsConfig()

        # Just under threshold -> STH
        cohort, sub_cohort = config.classify(154)
        assert cohort == "STH"
        assert sub_cohort == "3m-6m"  # 90-180 days

        # Exactly at threshold -> LTH
        cohort, sub_cohort = config.classify(155)
        assert cohort == "LTH"
        assert sub_cohort == "3m-6m"  # 90-180 days

        # Just over threshold -> LTH
        cohort, sub_cohort = config.classify(156)
        assert cohort == "LTH"
        assert sub_cohort == "3m-6m"  # 90-180 days

    def test_classify_sub_cohorts(self):
        """Test sub-cohort classification across all age ranges."""
        config = AgeCohortsConfig()

        # Test each sub-cohort boundary
        test_cases = [
            (0, "STH", "<1d"),
            (1, "STH", "1d-1w"),
            (6, "STH", "1d-1w"),
            (7, "STH", "1w-1m"),
            (29, "STH", "1w-1m"),
            (30, "STH", "1m-3m"),
            (89, "STH", "1m-3m"),
            (90, "STH", "3m-6m"),
            (154, "STH", "3m-6m"),
            (155, "LTH", "3m-6m"),  # STH/LTH boundary
            (180, "LTH", "6m-1y"),
            (364, "LTH", "6m-1y"),
            (365, "LTH", "1y-2y"),
            (729, "LTH", "1y-2y"),
            (730, "LTH", "2y-3y"),
            (1094, "LTH", "2y-3y"),
            (1095, "LTH", "3y-5y"),
            (1824, "LTH", "3y-5y"),
            (1825, "LTH", ">5y"),
            (3650, "LTH", ">5y"),  # 10 years
        ]

        for age_days, expected_cohort, expected_sub in test_cases:
            cohort, sub_cohort = config.classify(age_days)
            assert cohort == expected_cohort, (
                f"age={age_days}: expected {expected_cohort}, got {cohort}"
            )
            assert sub_cohort == expected_sub, (
                f"age={age_days}: expected {expected_sub}, got {sub_cohort}"
            )

    def test_classify_custom_threshold(self):
        """Test classification with custom STH/LTH threshold."""
        config = AgeCohortsConfig(sth_threshold_days=90)

        # 89 days -> STH with 90-day threshold
        cohort, _ = config.classify(89)
        assert cohort == "STH"

        # 90 days -> LTH with 90-day threshold
        cohort, _ = config.classify(90)
        assert cohort == "LTH"

    def test_classify_edge_case_zero_days(self):
        """Test classification for brand new UTXO (0 days)."""
        config = AgeCohortsConfig()

        cohort, sub_cohort = config.classify(0)
        assert cohort == "STH"
        assert sub_cohort == "<1d"
