#!/usr/bin/env python3
"""
Tests for PRO Risk Metric (spec-033)

TDD Test Suite for User Story 1: Core PRO Risk Calculation

Test Coverage:
    T007: normalize_to_percentile function
    T008: classify_zone function
    T009: calculate_pro_risk function
    T010: calculate_confidence function
"""

import pytest
from datetime import datetime

from scripts.metrics.pro_risk import (
    normalize_to_percentile,
    classify_zone,
    calculate_pro_risk,
    calculate_confidence,
    ProRiskResult,
    ComponentScore,
    COMPONENT_WEIGHTS,
    ZONE_THRESHOLDS,
    MIN_HISTORY_DAYS,
)


# =============================================================================
# T007: Tests for normalize_to_percentile function
# =============================================================================


class TestNormalizeToPercentile:
    """Tests for the normalize_to_percentile function (T007)."""

    def test_returns_neutral_with_insufficient_history(self):
        """Should return 0.5 when history has fewer than MIN_HISTORY_DAYS."""
        value = 1.0
        # Only 100 days of history (need 1460)
        historical_data = list(range(100))

        result = normalize_to_percentile(value, historical_data)

        assert result == 0.5, "Should return neutral (0.5) with insufficient data"

    def test_returns_low_percentile_for_low_value(self):
        """Should return low percentile for value at bottom of distribution."""
        # Create uniform distribution from 0 to 100
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]
        value = 10.0  # Should be in low percentile

        result = normalize_to_percentile(value, historical_data)

        assert 0.0 <= result <= 0.1, f"Expected low percentile, got {result}"

    def test_returns_high_percentile_for_high_value(self):
        """Should return high percentile for value at top of distribution."""
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]
        value = 1500.0  # Should be in high percentile

        result = normalize_to_percentile(value, historical_data)

        assert 0.9 <= result <= 1.0, f"Expected high percentile, got {result}"

    def test_returns_middle_percentile_for_median_value(self):
        """Should return ~0.5 percentile for median value."""
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]
        median_value = (MIN_HISTORY_DAYS + 100) / 2

        result = normalize_to_percentile(median_value, historical_data)

        assert 0.45 <= result <= 0.55, f"Expected ~0.5 percentile, got {result}"

    def test_winsorization_caps_extreme_values(self):
        """Should cap extreme values at winsorization bounds."""
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]

        # Test extreme high value (should be capped at 98th percentile)
        extreme_high = 10000.0
        result_high = normalize_to_percentile(extreme_high, historical_data)

        # Should be capped at or near 0.98
        assert result_high >= 0.95, (
            f"Extreme high should be capped near 0.98, got {result_high}"
        )

        # Test extreme low value (should be capped at 2nd percentile)
        extreme_low = -1000.0
        result_low = normalize_to_percentile(extreme_low, historical_data)

        assert result_low <= 0.05, (
            f"Extreme low should be capped near 0.02, got {result_low}"
        )

    def test_returns_float_between_zero_and_one(self):
        """Should always return a float in [0, 1] range."""
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]

        for value in [-1000, 0, 500, 1000, 5000]:
            result = normalize_to_percentile(float(value), historical_data)
            assert isinstance(result, float), (
                f"Result should be float, got {type(result)}"
            )
            assert 0.0 <= result <= 1.0, f"Result should be in [0,1], got {result}"

    def test_with_negative_values_in_history(self):
        """Should handle negative values in historical data correctly."""
        # MVRV-Z can be negative, so test with negative range
        historical_data = [float(i - 500) for i in range(MIN_HISTORY_DAYS + 100)]

        result_positive = normalize_to_percentile(100.0, historical_data)
        result_negative = normalize_to_percentile(-100.0, historical_data)

        assert result_positive > result_negative, (
            "Positive should have higher percentile"
        )

    def test_custom_winsorize_pct(self):
        """Should respect custom winsorization percentage."""
        historical_data = [float(i) for i in range(MIN_HISTORY_DAYS + 100)]

        # With higher winsorization (10%), extreme values should be more heavily capped
        result_default = normalize_to_percentile(
            10000.0, historical_data, winsorize_pct=0.02
        )
        result_strict = normalize_to_percentile(
            10000.0, historical_data, winsorize_pct=0.10
        )

        # Both should be high but strict should be lower due to tighter bounds
        assert result_strict <= result_default


# =============================================================================
# T008: Tests for classify_zone function
# =============================================================================


class TestClassifyZone:
    """Tests for the classify_zone function (T008)."""

    def test_extreme_fear_zone(self):
        """Values in [0.00, 0.20) should be classified as extreme_fear."""
        assert classify_zone(0.00) == "extreme_fear"
        assert classify_zone(0.10) == "extreme_fear"
        assert classify_zone(0.19) == "extreme_fear"

    def test_fear_zone(self):
        """Values in [0.20, 0.40) should be classified as fear."""
        assert classify_zone(0.20) == "fear"
        assert classify_zone(0.30) == "fear"
        assert classify_zone(0.39) == "fear"

    def test_neutral_zone(self):
        """Values in [0.40, 0.60) should be classified as neutral."""
        assert classify_zone(0.40) == "neutral"
        assert classify_zone(0.50) == "neutral"
        assert classify_zone(0.59) == "neutral"

    def test_greed_zone(self):
        """Values in [0.60, 0.80) should be classified as greed."""
        assert classify_zone(0.60) == "greed"
        assert classify_zone(0.70) == "greed"
        assert classify_zone(0.79) == "greed"

    def test_extreme_greed_zone(self):
        """Values in [0.80, 1.00] should be classified as extreme_greed."""
        assert classify_zone(0.80) == "extreme_greed"
        assert classify_zone(0.90) == "extreme_greed"
        assert classify_zone(1.00) == "extreme_greed"

    def test_boundary_values(self):
        """Test exact boundary transitions."""
        # 0.20 is the start of fear, not extreme_fear
        assert classify_zone(0.199999) == "extreme_fear"
        assert classify_zone(0.20) == "fear"

        # 0.40 is the start of neutral
        assert classify_zone(0.399999) == "fear"
        assert classify_zone(0.40) == "neutral"

    def test_raises_on_invalid_value(self):
        """Should raise ValueError for values outside [0, 1]."""
        with pytest.raises(ValueError):
            classify_zone(-0.1)

        with pytest.raises(ValueError):
            classify_zone(1.1)

    def test_returns_valid_zone_type(self):
        """Should return a valid RiskZone literal type."""
        valid_zones = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}

        for value in [0.0, 0.25, 0.5, 0.75, 1.0]:
            zone = classify_zone(value)
            assert zone in valid_zones, f"Invalid zone: {zone}"


# =============================================================================
# T009: Tests for calculate_pro_risk function
# =============================================================================


class TestCalculateProRisk:
    """Tests for the calculate_pro_risk function (T009)."""

    def test_returns_pro_risk_result(self):
        """Should return a ProRiskResult dataclass."""
        result = calculate_pro_risk(mvrv_z=0.5)

        assert isinstance(result, ProRiskResult)

    def test_calculates_weighted_average(self):
        """Should calculate correct weighted average of components."""
        # All components at 0.5 should give 0.5 composite
        result = calculate_pro_risk(
            mvrv_z=0.5,
            sopr=0.5,
            nupl=0.5,
            reserve_risk=0.5,
            puell=0.5,
            hodl_waves=0.5,
        )

        assert abs(result.value - 0.5) < 0.01, f"Expected ~0.5, got {result.value}"

    def test_respects_component_weights(self):
        """Should respect the defined component weights."""
        # MVRV-Z has highest weight (30%), HODL Waves lowest (5%)
        # Set MVRV-Z high, others low
        result_mvrv_high = calculate_pro_risk(
            mvrv_z=1.0,
            sopr=0.0,
            nupl=0.0,
            reserve_risk=0.0,
            puell=0.0,
            hodl_waves=0.0,
        )

        # Set HODL Waves high, others low
        result_hodl_high = calculate_pro_risk(
            mvrv_z=0.0,
            sopr=0.0,
            nupl=0.0,
            reserve_risk=0.0,
            puell=0.0,
            hodl_waves=1.0,
        )

        # MVRV-Z high should produce higher composite than HODL Waves high
        assert result_mvrv_high.value > result_hodl_high.value

    def test_handles_missing_components(self):
        """Should handle None components gracefully."""
        result = calculate_pro_risk(
            mvrv_z=0.8,
            sopr=None,
            nupl=None,
            reserve_risk=None,
            puell=None,
            hodl_waves=None,
        )

        assert isinstance(result, ProRiskResult)
        assert (
            result.value > 0.5
        )  # Should be high since only MVRV-Z is provided and it's 0.8

    def test_returns_neutral_with_no_components(self):
        """Should return neutral (0.5) when all components are None."""
        result = calculate_pro_risk()

        assert result.value == 0.5
        assert result.zone == "neutral"

    def test_classifies_zone_correctly(self):
        """Should classify the correct zone based on composite value."""
        # Low value -> extreme_fear
        result_low = calculate_pro_risk(
            mvrv_z=0.1, sopr=0.1, nupl=0.1, reserve_risk=0.1, puell=0.1, hodl_waves=0.1
        )
        assert result_low.zone == "extreme_fear"

        # High value -> extreme_greed
        result_high = calculate_pro_risk(
            mvrv_z=0.9, sopr=0.9, nupl=0.9, reserve_risk=0.9, puell=0.9, hodl_waves=0.9
        )
        assert result_high.zone == "extreme_greed"

    def test_stores_component_values(self):
        """Should store individual component values in result."""
        result = calculate_pro_risk(
            mvrv_z=0.7,
            sopr=0.6,
            nupl=0.5,
        )

        assert "mvrv_z" in result.components
        assert result.components["mvrv_z"] == 0.7
        assert "sopr" in result.components
        assert result.components["sopr"] == 0.6

    def test_sets_date_correctly(self):
        """Should set the correct date in result."""
        target_date = datetime(2025, 12, 25)
        result = calculate_pro_risk(mvrv_z=0.5, target_date=target_date)

        assert result.date == target_date

    def test_defaults_to_today(self):
        """Should default to current date if no date provided."""
        result = calculate_pro_risk(mvrv_z=0.5)

        # Should be within a few seconds of now
        now = datetime.utcnow()
        delta = abs((result.date - now).total_seconds())
        assert delta < 60, "Date should be close to current time"

    def test_result_value_is_clamped(self):
        """Result value should be clamped to [0, 1]."""
        # Even with extreme inputs, result should be in [0, 1]
        result = calculate_pro_risk(
            mvrv_z=0.0, sopr=0.0, nupl=0.0, reserve_risk=0.0, puell=0.0, hodl_waves=0.0
        )
        assert 0.0 <= result.value <= 1.0

        result = calculate_pro_risk(
            mvrv_z=1.0, sopr=1.0, nupl=1.0, reserve_risk=1.0, puell=1.0, hodl_waves=1.0
        )
        assert 0.0 <= result.value <= 1.0

    def test_to_dict_serialization(self):
        """Should serialize to dict correctly."""
        result = calculate_pro_risk(mvrv_z=0.6, sopr=0.5)
        result_dict = result.to_dict()

        assert "date" in result_dict
        assert "value" in result_dict
        assert "zone" in result_dict
        assert "components" in result_dict
        assert "confidence" in result_dict


# =============================================================================
# T010: Tests for calculate_confidence function
# =============================================================================


class TestCalculateConfidence:
    """Tests for the calculate_confidence function (T010)."""

    def test_full_confidence_with_all_components(self):
        """Should return 1.0 when all components are available."""
        components = {
            "mvrv_z": 0.5,
            "sopr": 0.5,
            "nupl": 0.5,
            "reserve_risk": 0.5,
            "puell": 0.5,
            "hodl_waves": 0.5,
        }

        confidence = calculate_confidence(components)

        assert confidence == 1.0

    def test_zero_confidence_with_no_components(self):
        """Should return 0.0 when no components are available."""
        components = {
            "mvrv_z": None,
            "sopr": None,
            "nupl": None,
            "reserve_risk": None,
            "puell": None,
            "hodl_waves": None,
        }

        confidence = calculate_confidence(components)

        assert confidence == 0.0

    def test_partial_confidence_with_some_components(self):
        """Should return partial confidence when some components are missing."""
        # Only MVRV-Z available (30% weight)
        components = {
            "mvrv_z": 0.5,
            "sopr": None,
            "nupl": None,
            "reserve_risk": None,
            "puell": None,
            "hodl_waves": None,
        }

        confidence = calculate_confidence(components)

        assert abs(confidence - 0.30) < 0.01, f"Expected 0.30, got {confidence}"

    def test_confidence_matches_weight_sum(self):
        """Confidence should equal sum of weights for available components."""
        # Grade A components only (MVRV-Z: 30%, SOPR: 20%, NUPL: 20% = 70%)
        components = {
            "mvrv_z": 0.5,
            "sopr": 0.5,
            "nupl": 0.5,
            "reserve_risk": None,
            "puell": None,
            "hodl_waves": None,
        }

        confidence = calculate_confidence(components)

        assert abs(confidence - 0.70) < 0.01, f"Expected 0.70, got {confidence}"

    def test_handles_empty_dict(self):
        """Should handle empty components dict."""
        confidence = calculate_confidence({})

        assert confidence == 0.0

    def test_handles_unknown_component_names(self):
        """Should ignore unknown component names."""
        components = {
            "unknown_metric": 0.5,
            "mvrv_z": 0.5,
        }

        confidence = calculate_confidence(components)

        # Only MVRV-Z should count
        assert abs(confidence - 0.30) < 0.01

    def test_confidence_never_exceeds_one(self):
        """Confidence should never exceed 1.0."""
        # Even with extra components
        components = {
            "mvrv_z": 0.5,
            "sopr": 0.5,
            "nupl": 0.5,
            "reserve_risk": 0.5,
            "puell": 0.5,
            "hodl_waves": 0.5,
            "extra1": 0.5,
            "extra2": 0.5,
        }

        confidence = calculate_confidence(components)

        assert confidence <= 1.0


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case tests for PRO Risk module."""

    def test_component_score_validation(self):
        """ComponentScore should validate percentile and weight ranges."""
        # Valid component
        score = ComponentScore(
            metric_name="mvrv_z",
            raw_value=2.0,
            percentile=0.7,
            weight=0.30,
            history_days=1500,
        )
        assert score.weighted_contribution == 0.7 * 0.30

        # Invalid percentile
        with pytest.raises(ValueError):
            ComponentScore(
                metric_name="test",
                raw_value=0,
                percentile=1.5,  # Invalid: > 1
                weight=0.5,
                history_days=100,
            )

        # Invalid weight
        with pytest.raises(ValueError):
            ComponentScore(
                metric_name="test",
                raw_value=0,
                percentile=0.5,
                weight=-0.1,  # Invalid: < 0
                history_days=100,
            )

    def test_pro_risk_result_validation(self):
        """ProRiskResult should validate value and confidence ranges."""
        # Valid result
        result = ProRiskResult(
            date=datetime.utcnow(),
            value=0.5,
            zone="neutral",
        )
        assert result.value == 0.5

        # Invalid value
        with pytest.raises(ValueError):
            ProRiskResult(
                date=datetime.utcnow(),
                value=1.5,  # Invalid: > 1
                zone="greed",
            )

        # Invalid confidence
        with pytest.raises(ValueError):
            ProRiskResult(
                date=datetime.utcnow(),
                value=0.5,
                zone="neutral",
                confidence=-0.1,  # Invalid: < 0
            )

    def test_weights_sum_to_one(self):
        """Component weights should sum to exactly 1.0."""
        total_weight = sum(COMPONENT_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001, (
            f"Weights sum to {total_weight}, not 1.0"
        )

    def test_zone_thresholds_are_contiguous(self):
        """Zone thresholds should be contiguous from 0 to 1."""
        # Check no gaps
        prev_max = 0.0
        for min_val, max_val, zone in ZONE_THRESHOLDS:
            assert min_val == prev_max, f"Gap in thresholds at {min_val}"
            prev_max = max_val

        assert prev_max == 1.0, "Thresholds don't end at 1.0"
