#!/usr/bin/env python3
"""
Tests for PredictionOutcome Pydantic Model
Task T007 - Test Coverage
"""

import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError
from scripts.models.prediction_outcome import (
    PredictionOutcome,
    OutcomeType,
)


def create_test_outcome(**overrides):
    """Helper to create valid prediction outcome with overrides"""
    defaults = {
        "outcome_id": str(uuid.uuid4()),
        "prediction_id": str(uuid.uuid4()),
        "transaction_id": "a" * 64,
        "predicted_flow": "inflow",
        "actual_outcome": OutcomeType.CONFIRMED,
        "confirmation_block": 922501,
        "confirmation_time": datetime.now(timezone.utc),
        "time_to_confirmation": 15,
        "final_fee_rate": 45.2,
    }
    defaults.update(overrides)
    return PredictionOutcome(**defaults)


class TestPredictionOutcomeValidation:
    """Test Pydantic validation rules"""

    def test_valid_outcome_creation(self):
        """Valid prediction outcome should be created successfully"""
        outcome = create_test_outcome()

        assert outcome.transaction_id == "a" * 64
        assert outcome.actual_outcome == OutcomeType.CONFIRMED
        assert outcome.final_fee_rate == 45.2

    def test_outcome_type_enum_values(self):
        """All outcome types should be valid"""
        for outcome_type in [
            OutcomeType.CONFIRMED,
            OutcomeType.DROPPED,
            OutcomeType.REPLACED,
        ]:
            outcome = create_test_outcome(actual_outcome=outcome_type)
            assert outcome.actual_outcome == outcome_type

    def test_invalid_outcome_type(self):
        """Invalid outcome type should raise validation error"""
        with pytest.raises(ValidationError):
            create_test_outcome(actual_outcome="invalid_outcome")

    def test_invalid_transaction_id_length(self):
        """Transaction ID must be exactly 64 characters"""
        with pytest.raises(ValidationError):
            create_test_outcome(transaction_id="abc123")


class TestPredictionOutcomeAccuracy:
    """Test accuracy calculation logic"""

    def test_accuracy_perfect_prediction(self):
        """Perfect prediction (same block) should have high accuracy"""
        outcome = create_test_outcome(
            confirmation_block=922500,
            time_to_confirmation=20,
        )

        # Predicted same block, high urgency
        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )
        assert accuracy > 0.9  # Should be very high
        assert accuracy <= 1.0

    def test_accuracy_one_block_late(self):
        """Confirmation 1 block late should still have good accuracy"""
        outcome = create_test_outcome(
            confirmation_block=922501,
            time_to_confirmation=20,
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )
        assert 0.8 < accuracy < 1.0  # Still good

    def test_accuracy_many_blocks_late(self):
        """Confirmation many blocks late should have lower accuracy"""
        outcome = create_test_outcome(
            confirmation_block=922510,  # 10 blocks late
            time_to_confirmation=100,
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )
        assert accuracy < 0.7  # Significantly lower

    def test_accuracy_dropped_transaction(self):
        """Dropped transactions should have low accuracy"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.DROPPED,
            confirmation_block=None,
            confirmation_time=None,
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )
        assert accuracy == 0.1  # Very low for high urgency that dropped

    def test_accuracy_replaced_transaction(self):
        """Replaced transactions should have low accuracy"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.REPLACED,
            confirmation_block=None,
            confirmation_time=None,
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.7, predicted_block=922500
        )
        assert accuracy == 0.1  # Low for failed prediction


class TestPredictionOutcomeTimingScore:
    """Test timing score component of accuracy"""

    def test_timing_score_perfect(self):
        """Same block confirmation should give high timing score"""
        outcome = create_test_outcome(
            confirmation_block=922500,
            time_to_confirmation=20,
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.5, predicted_block=922500
        )
        # With perfect block timing (1.0) and fast confirmation
        assert accuracy > 0.8

    def test_timing_score_degrades_with_blocks(self):
        """Timing score should degrade as blocks increase"""
        scores = []
        for blocks_late in range(1, 7):
            outcome = create_test_outcome(
                confirmation_block=922500 + blocks_late,
                time_to_confirmation=blocks_late * 10,
            )
            accuracy = outcome.calculate_accuracy(
                predicted_urgency=0.5, predicted_block=922500
            )
            scores.append(accuracy)

        # Scores should generally be decreasing (allowing some variation)
        assert scores[0] > scores[-1]

    def test_timing_score_minimum_at_6_blocks(self):
        """Timing score should reach minimum at 6+ blocks"""
        outcome_6_late = create_test_outcome(
            confirmation_block=922506,
            time_to_confirmation=60,
        )
        outcome_10_late = create_test_outcome(
            confirmation_block=922510,
            time_to_confirmation=100,
        )

        accuracy_6 = outcome_6_late.calculate_accuracy(
            predicted_urgency=0.5, predicted_block=922500
        )
        accuracy_10 = outcome_10_late.calculate_accuracy(
            predicted_urgency=0.5, predicted_block=922500
        )

        # Both should be low and similar (timing floor reached)
        assert accuracy_6 <= 0.7
        assert accuracy_10 <= 0.7


class TestPredictionOutcomeProperties:
    """Test helper properties"""

    def test_was_accurate_true(self):
        """Accurate predictions should return True"""
        outcome = create_test_outcome(
            confirmation_block=922500,
            time_to_confirmation=20,
        )
        # Calculate and set accuracy
        outcome.accuracy_score = outcome.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )

        # Accuracy threshold is 0.7
        assert outcome.was_accurate is True

    def test_was_accurate_false(self):
        """Inaccurate predictions should return False"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.DROPPED,
            confirmation_block=None,
        )
        outcome.accuracy_score = 0.3  # Low accuracy

        assert outcome.was_accurate is False

    def test_was_confirmed_true(self):
        """Confirmed outcomes should return True"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.CONFIRMED,
        )

        assert outcome.was_confirmed is True

    def test_was_confirmed_false_dropped(self):
        """Dropped outcomes should return False"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.DROPPED,
        )

        assert outcome.was_confirmed is False

    def test_was_replaced_true(self):
        """Replaced outcomes should return True"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.REPLACED,
        )

        assert outcome.was_replaced is True

    def test_was_replaced_false(self):
        """Non-replaced outcomes should return False"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.CONFIRMED,
        )

        assert outcome.was_replaced is False


class TestPredictionOutcomeTimeToConfirmation:
    """Test time-to-confirmation field"""

    def test_time_to_confirmation_stored(self):
        """Should store minutes correctly"""
        outcome = create_test_outcome(
            time_to_confirmation=25,
        )

        assert outcome.time_to_confirmation == 25

    def test_time_to_confirmation_none_if_not_confirmed(self):
        """Should be None if not confirmed"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.DROPPED,
            confirmation_time=None,
            time_to_confirmation=None,
        )

        assert outcome.time_to_confirmation is None


class TestPredictionOutcomeSerialization:
    """Test database serialization"""

    def test_to_db_dict(self):
        """Should serialize correctly for database"""
        outcome = create_test_outcome()

        db_dict = outcome.to_db_dict()

        assert "outcome_id" in db_dict
        assert "prediction_id" in db_dict
        assert "transaction_id" in db_dict
        assert "actual_outcome" in db_dict
        assert "predicted_flow" in db_dict
        assert db_dict["final_fee_rate"] == 45.2

    def test_to_db_dict_with_none_values(self):
        """Should handle None values correctly"""
        outcome = create_test_outcome(
            actual_outcome=OutcomeType.DROPPED,
            confirmation_block=None,
            confirmation_time=None,
            time_to_confirmation=None,
            final_fee_rate=None,
        )

        db_dict = outcome.to_db_dict()

        assert db_dict["confirmation_block"] is None
        assert db_dict["confirmation_time"] is None
        assert db_dict["time_to_confirmation"] is None


class TestPredictionOutcomeWeightedAccuracy:
    """Test weighted accuracy formula"""

    def test_accuracy_formula_weights(self):
        """Accuracy uses timing and urgency components"""
        outcome = create_test_outcome(
            confirmation_block=922500,  # Perfect timing
            time_to_confirmation=20,  # Fast confirmation
        )

        accuracy = outcome.calculate_accuracy(
            predicted_urgency=0.8, predicted_block=922500
        )

        # With perfect block match and fast confirmation matching high urgency
        # timing_score = 1.0, urgency_score = 1.0
        # accuracy = (1.0 * 0.6) + (1.0 * 0.4) = 1.0
        assert accuracy >= 0.9

    def test_accuracy_urgency_impact(self):
        """Urgency affects accuracy score"""
        # High urgency, slow confirmation - mismatch
        outcome_slow = create_test_outcome(
            confirmation_block=922500,
            time_to_confirmation=100,  # Slow (>30 min)
        )

        # Low urgency, slow confirmation - match
        accuracy_high_urgency = outcome_slow.calculate_accuracy(
            predicted_urgency=0.9, predicted_block=922500
        )
        accuracy_low_urgency = outcome_slow.calculate_accuracy(
            predicted_urgency=0.3, predicted_block=922500
        )

        # Low urgency prediction should be more accurate for slow confirmation
        assert accuracy_low_urgency > accuracy_high_urgency
