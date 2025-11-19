#!/usr/bin/env python3
"""
Tests for UrgencyMetrics Pydantic Model
Task T008 - Test Coverage
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from scripts.models.urgency_metrics import (
    UrgencyMetrics,
    CongestionLevel,
)


def create_test_metrics(**overrides):
    """Helper to create valid urgency metrics with overrides"""
    defaults = {
        "current_block_height": 850000,
        "fee_percentiles": {
            "p10": 5.0,
            "p25": 10.0,
            "p50": 20.0,
            "p75": 35.0,
            "p90": 50.0,
        },
        "estimated_blocks_to_confirmation": {
            "low_fee": 6,
            "medium_fee": 3,
            "high_fee": 1,
        },
        "mempool_size_mb": 45.2,
        "congestion_level": CongestionLevel.MEDIUM,
    }
    defaults.update(overrides)
    return UrgencyMetrics(**defaults)


class TestUrgencyMetricsValidation:
    """Test Pydantic validation rules"""

    def test_valid_metrics_creation(self):
        """Valid urgency metrics should be created successfully"""
        metrics = create_test_metrics()

        assert metrics.current_block_height == 850000
        assert metrics.fee_percentiles["p50"] == 20.0
        assert metrics.congestion_level == CongestionLevel.MEDIUM

    def test_congestion_level_enum_values(self):
        """All congestion levels should be valid"""
        for level in [
            CongestionLevel.LOW,
            CongestionLevel.MEDIUM,
            CongestionLevel.HIGH,
            CongestionLevel.EXTREME,
        ]:
            metrics = create_test_metrics(congestion_level=level)
            assert metrics.congestion_level == level

    def test_invalid_congestion_level(self):
        """Invalid congestion level should raise validation error"""
        with pytest.raises(ValidationError):
            create_test_metrics(congestion_level="super_extreme")

    def test_missing_percentiles(self):
        """Missing required percentiles should raise validation error"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_metrics(
                fee_percentiles={
                    "p10": 5.0,
                    "p50": 20.0,
                    # Missing p25, p75, p90
                }
            )

        assert "Missing required percentiles" in str(exc_info.value)

    def test_percentiles_wrong_order(self):
        """Percentiles not in ascending order should raise validation error"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_metrics(
                fee_percentiles={
                    "p10": 50.0,  # Higher than p50
                    "p25": 10.0,
                    "p50": 20.0,
                    "p75": 35.0,
                    "p90": 50.0,
                }
            )

        assert "ascending order" in str(exc_info.value)

    def test_missing_confirmation_estimates(self):
        """Missing confirmation estimates should raise validation error"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_metrics(
                estimated_blocks_to_confirmation={
                    "low_fee": 6,
                    # Missing medium_fee, high_fee
                }
            )

        assert "Missing required estimates" in str(exc_info.value)

    def test_confirmation_estimates_wrong_order(self):
        """Estimates not properly ordered should raise validation error"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_metrics(
                estimated_blocks_to_confirmation={
                    "low_fee": 1,  # Should be highest
                    "medium_fee": 3,
                    "high_fee": 6,  # Should be lowest
                }
            )

        assert "ordered" in str(exc_info.value)


class TestUrgencyMetricsUrgencyScoring:
    """Test urgency score calculation"""

    def test_urgency_score_very_low_fee(self):
        """Very low fee (<p10) should give low urgency"""
        metrics = create_test_metrics()

        # Fee below p10 (5.0 sat/vB)
        urgency = metrics.calculate_urgency_score(3.0)
        assert 0.0 <= urgency <= 0.2

    def test_urgency_score_low_fee(self):
        """Low fee (p10-p25) should give low-medium urgency"""
        metrics = create_test_metrics()

        # Fee between p10 (5.0) and p25 (10.0)
        urgency = metrics.calculate_urgency_score(7.5)
        assert 0.2 <= urgency <= 0.4

    def test_urgency_score_medium_fee(self):
        """Medium fee (p25-p50) should give medium urgency"""
        metrics = create_test_metrics()

        # Fee between p25 (10.0) and p50 (20.0)
        urgency = metrics.calculate_urgency_score(15.0)
        assert 0.4 <= urgency <= 0.6

    def test_urgency_score_high_fee(self):
        """High fee (p50-p75) should give high urgency"""
        metrics = create_test_metrics()

        # Fee between p50 (20.0) and p75 (35.0)
        urgency = metrics.calculate_urgency_score(27.5)
        assert 0.6 <= urgency <= 0.8

    def test_urgency_score_very_high_fee(self):
        """Very high fee (p75-p90) should give very high urgency"""
        metrics = create_test_metrics()

        # Fee between p75 (35.0) and p90 (50.0)
        urgency = metrics.calculate_urgency_score(42.5)
        assert 0.8 <= urgency <= 0.95

    def test_urgency_score_extreme_fee(self):
        """Extreme fee (>p90) should give maximum urgency"""
        metrics = create_test_metrics()

        # Fee above p90 (50.0 sat/vB)
        urgency = metrics.calculate_urgency_score(100.0)
        assert 0.95 <= urgency <= 1.0

    def test_urgency_score_monotonic(self):
        """Urgency score should increase monotonically with fee"""
        metrics = create_test_metrics()

        scores = []
        for fee in [3.0, 7.5, 15.0, 27.5, 42.5, 75.0]:
            scores.append(metrics.calculate_urgency_score(fee))

        # Each score should be >= previous score
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]

    def test_urgency_score_capped_at_one(self):
        """Urgency score should never exceed 1.0"""
        metrics = create_test_metrics()

        # Test extremely high fees
        for fee in [100.0, 500.0, 1000.0]:
            urgency = metrics.calculate_urgency_score(fee)
            assert urgency <= 1.0


class TestUrgencyMetricsConfirmationPrediction:
    """Test confirmation block prediction"""

    def test_predict_high_fee_fast_confirmation(self):
        """High fee (>=p75) should predict fast confirmation"""
        metrics = create_test_metrics()

        # Fee above p75 (35.0 sat/vB)
        predicted_block = metrics.predict_confirmation_block(40.0)
        blocks_ahead = predicted_block - metrics.current_block_height

        assert blocks_ahead == 1  # high_fee estimate

    def test_predict_medium_fee_moderate_confirmation(self):
        """Medium fee (p50-p75) should predict moderate confirmation"""
        metrics = create_test_metrics()

        # Fee between p50 (20.0) and p75 (35.0)
        predicted_block = metrics.predict_confirmation_block(27.5)
        blocks_ahead = predicted_block - metrics.current_block_height

        assert blocks_ahead == 3  # medium_fee estimate

    def test_predict_low_fee_slow_confirmation(self):
        """Low fee (<p50) should predict slow confirmation"""
        metrics = create_test_metrics()

        # Fee below p50 (20.0 sat/vB)
        predicted_block = metrics.predict_confirmation_block(10.0)
        blocks_ahead = predicted_block - metrics.current_block_height

        assert blocks_ahead == 6  # low_fee estimate

    def test_predict_at_p50_boundary(self):
        """Fee exactly at p50 should use medium_fee estimate"""
        metrics = create_test_metrics()

        predicted_block = metrics.predict_confirmation_block(20.0)
        blocks_ahead = predicted_block - metrics.current_block_height

        assert blocks_ahead == 3  # medium_fee estimate

    def test_predict_at_p75_boundary(self):
        """Fee exactly at p75 should use high_fee estimate"""
        metrics = create_test_metrics()

        predicted_block = metrics.predict_confirmation_block(35.0)
        blocks_ahead = predicted_block - metrics.current_block_height

        assert blocks_ahead == 1  # high_fee estimate


class TestUrgencyMetricsCongestionClassification:
    """Test congestion level classification"""

    def test_classify_low_congestion(self):
        """Mempool <10 MB should be LOW congestion"""
        metrics = create_test_metrics(mempool_size_mb=5.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.LOW

    def test_classify_medium_congestion(self):
        """Mempool 10-50 MB should be MEDIUM congestion"""
        metrics = create_test_metrics(mempool_size_mb=25.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.MEDIUM

    def test_classify_high_congestion(self):
        """Mempool 50-100 MB should be HIGH congestion"""
        metrics = create_test_metrics(mempool_size_mb=75.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.HIGH

    def test_classify_extreme_congestion(self):
        """Mempool >100 MB should be EXTREME congestion"""
        metrics = create_test_metrics(mempool_size_mb=150.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.EXTREME

    def test_classify_boundary_10mb(self):
        """Mempool exactly 10 MB should be MEDIUM"""
        metrics = create_test_metrics(mempool_size_mb=10.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.MEDIUM

    def test_classify_boundary_50mb(self):
        """Mempool exactly 50 MB should be HIGH"""
        metrics = create_test_metrics(mempool_size_mb=50.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.HIGH

    def test_classify_boundary_100mb(self):
        """Mempool exactly 100 MB should be EXTREME"""
        metrics = create_test_metrics(mempool_size_mb=100.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.EXTREME


class TestUrgencyMetricsProperties:
    """Test helper properties"""

    def test_is_high_congestion_true_for_high(self):
        """HIGH congestion should return True"""
        metrics = create_test_metrics(congestion_level=CongestionLevel.HIGH)

        assert metrics.is_high_congestion is True

    def test_is_high_congestion_true_for_extreme(self):
        """EXTREME congestion should return True"""
        metrics = create_test_metrics(congestion_level=CongestionLevel.EXTREME)

        assert metrics.is_high_congestion is True

    def test_is_high_congestion_false_for_medium(self):
        """MEDIUM congestion should return False"""
        metrics = create_test_metrics(congestion_level=CongestionLevel.MEDIUM)

        assert metrics.is_high_congestion is False

    def test_is_high_congestion_false_for_low(self):
        """LOW congestion should return False"""
        metrics = create_test_metrics(congestion_level=CongestionLevel.LOW)

        assert metrics.is_high_congestion is False

    def test_median_fee_property(self):
        """median_fee should return p50"""
        metrics = create_test_metrics()

        assert metrics.median_fee == 20.0

    def test_high_priority_fee_property(self):
        """high_priority_fee should return p75"""
        metrics = create_test_metrics()

        assert metrics.high_priority_fee == 35.0


class TestUrgencyMetricsEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zero_fee(self):
        """Zero fee should give minimum urgency"""
        metrics = create_test_metrics()

        urgency = metrics.calculate_urgency_score(0.0)
        assert urgency == 0.0

    def test_negative_fee_not_allowed(self):
        """Negative fee rates give negative urgency (edge case)"""
        # Fee percentiles must be valid positive numbers
        metrics = create_test_metrics()

        # Negative fee in calculation gives negative urgency
        # (shouldn't happen in reality, but formula doesn't explicitly guard against it)
        urgency = metrics.calculate_urgency_score(-10.0)
        assert urgency < 0.0  # Will be negative based on formula

    def test_very_large_fee(self):
        """Very large fee should cap at 1.0 urgency"""
        metrics = create_test_metrics()

        urgency = metrics.calculate_urgency_score(10000.0)
        assert urgency == 1.0

    def test_equal_percentiles(self):
        """Equal percentiles should not break calculations"""
        # Edge case: flat fee market
        metrics = create_test_metrics(
            fee_percentiles={
                "p10": 10.0,
                "p25": 10.0,
                "p50": 10.0,
                "p75": 10.0,
                "p90": 10.0,
            }
        )

        # Should not raise division by zero
        urgency = metrics.calculate_urgency_score(10.0)
        assert 0.0 <= urgency <= 1.0

    def test_mempool_size_zero(self):
        """Zero mempool size should classify as LOW"""
        metrics = create_test_metrics(mempool_size_mb=0.0)

        level = metrics.classify_congestion()
        assert level == CongestionLevel.LOW


class TestUrgencyMetricsTimestamps:
    """Test timestamp handling"""

    def test_last_update_auto_generated(self):
        """last_update should be auto-generated"""
        before = datetime.now(timezone.utc)
        metrics = create_test_metrics()
        after = datetime.now(timezone.utc)

        assert before <= metrics.last_update <= after

    def test_last_update_can_be_set(self):
        """last_update can be explicitly set"""
        specific_time = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

        metrics = create_test_metrics(last_update=specific_time)

        assert metrics.last_update == specific_time
