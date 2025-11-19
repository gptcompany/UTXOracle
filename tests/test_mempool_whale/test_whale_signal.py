#!/usr/bin/env python3
"""
Tests for MempoolWhaleSignal Pydantic Model
Task T006 - Test Coverage
"""

import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError
from scripts.models.whale_signal import (
    MempoolWhaleSignal,
    FlowType,
)


def create_test_signal(**overrides):
    """Helper to create valid whale signal with overrides"""
    defaults = {
        "prediction_id": str(uuid.uuid4()),
        "transaction_id": "a" * 64,
        "flow_type": FlowType.INFLOW,
        "btc_value": 150.5,
        "fee_rate": 45.2,
        "urgency_score": 0.85,
        "rbf_enabled": False,
        "detection_timestamp": datetime.now(timezone.utc),
        "predicted_confirmation_block": 922500,
        "exchange_addresses": ["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
        "confidence_score": 0.78,
    }
    defaults.update(overrides)
    return MempoolWhaleSignal(**defaults)


class TestMempoolWhaleSignalValidation:
    """Test Pydantic validation rules"""

    def test_valid_whale_signal_creation(self):
        """Valid whale signal should be created successfully"""
        signal = create_test_signal()

        assert signal.transaction_id == "a" * 64
        assert signal.flow_type == FlowType.INFLOW
        assert signal.btc_value == 150.5
        assert signal.urgency_score == 0.85

    def test_invalid_transaction_id_too_short(self):
        """Transaction ID must be exactly 64 characters"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_signal(
                transaction_id="abc123",  # Too short
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

        assert "transaction_id" in str(exc_info.value)

    def test_invalid_transaction_id_not_hex(self):
        """Transaction ID must be hexadecimal"""
        with pytest.raises(ValidationError):
            create_test_signal(
                transaction_id="g" * 64,  # Invalid hex
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

    def test_btc_value_must_be_greater_than_100(self):
        """BTC value must be > 100 for whale classification"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_signal(
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=99.9,  # Below threshold
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

        assert "btc_value" in str(exc_info.value)

    def test_fee_rate_must_be_positive(self):
        """Fee rate must be > 0"""
        with pytest.raises(ValidationError) as exc_info:
            create_test_signal(
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=-10,  # Negative fee
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

        assert "fee_rate" in str(exc_info.value)

    def test_urgency_score_range_validation(self):
        """Urgency score must be between 0.0 and 1.0"""
        # Test upper bound
        with pytest.raises(ValidationError):
            create_test_signal(
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=1.5,  # Too high
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

        # Test lower bound
        with pytest.raises(ValidationError):
            create_test_signal(
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=-0.1,  # Too low
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

    def test_confidence_score_range_validation(self):
        """Confidence score must be between 0.0 and 1.0"""
        with pytest.raises(ValidationError):
            create_test_signal(
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=2.0,  # Too high
            )


class TestMempoolWhaleSignalProperties:
    """Test helper properties"""

    def test_is_high_urgency_true(self):
        """Urgency score > 0.7 should be high urgency"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=45.2,
            urgency_score=0.85,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.is_high_urgency is True

    def test_is_high_urgency_false(self):
        """Urgency score <= 0.7 should not be high urgency"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=45.2,
            urgency_score=0.5,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.is_high_urgency is False

    def test_is_large_whale_true(self):
        """BTC value > 500 should be large whale"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=750.0,
            fee_rate=45.2,
            urgency_score=0.85,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.is_large_whale is True

    def test_is_large_whale_false(self):
        """BTC value <= 500 should not be large whale"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=300.0,
            fee_rate=45.2,
            urgency_score=0.85,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.is_large_whale is False

    def test_expected_confirmation_soon_true(self):
        """High urgency + high fee should expect soon confirmation"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=100.0,  # High fee
            urgency_score=0.9,  # High urgency
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.expected_confirmation_soon is True

    def test_expected_confirmation_soon_false(self):
        """Low urgency or low fee should not expect soon confirmation"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=10.0,  # Low fee
            urgency_score=0.3,  # Low urgency
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        assert signal.expected_confirmation_soon is False


class TestMempoolWhaleSignalSerialization:
    """Test serialization for DB and broadcast"""

    def test_to_db_dict(self):
        """Test database serialization"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=45.2,
            urgency_score=0.85,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=922500,
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        db_dict = signal.to_db_dict()

        assert "transaction_id" in db_dict
        assert "flow_type" in db_dict
        assert "btc_value" in db_dict
        assert db_dict["btc_value"] == 150.5

    def test_to_broadcast_dict(self):
        """Test WebSocket broadcast serialization"""
        signal = create_test_signal(
            transaction_id="a" * 64,
            flow_type=FlowType.INFLOW,
            btc_value=150.5,
            fee_rate=45.2,
            urgency_score=0.85,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=922500,
            exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            confidence_score=0.78,
        )

        broadcast_dict = signal.to_broadcast_dict()

        assert "transaction_id" in broadcast_dict
        assert "flow_type" in broadcast_dict
        assert "type" in broadcast_dict  # Broadcast message type
        assert broadcast_dict["type"] == "whale_alert"
        assert broadcast_dict["urgency_score"] == 0.85


class TestFlowTypeEnum:
    """Test FlowType enum"""

    def test_all_flow_types_valid(self):
        """All flow types should be creatable"""
        for flow_type in [
            FlowType.INFLOW,
            FlowType.OUTFLOW,
            FlowType.INTERNAL,
            FlowType.UNKNOWN,
        ]:
            signal = create_test_signal(
                transaction_id="a" * 64,
                flow_type=flow_type,
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )

            assert signal.flow_type == flow_type

    def test_invalid_flow_type(self):
        """Invalid flow type should raise validation error"""
        with pytest.raises(ValidationError):
            create_test_signal(
                transaction_id="a" * 64,
                flow_type="invalid_flow",  # Not a valid FlowType
                btc_value=150.5,
                fee_rate=45.2,
                urgency_score=0.85,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc),
                exchange_addresses=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
                confidence_score=0.78,
            )
