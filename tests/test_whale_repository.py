"""
Test suite for whale repository and data models.
Task T038: Storage layer tests.
"""

import pytest
import tempfile
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import ValidationError

from api.models.data import WhaleTransaction, NetFlowMetrics, Alert
from api.whale_repository import WhaleRepository


@pytest.fixture
def temp_db():
    """Fixture for temporary test database."""
    # Create temp file path but don't create the file yet

    db_path = tempfile.mktemp(suffix=".duckdb")

    # Initialize database schema
    from scripts.init_whale_db import init_whale_database

    init_whale_database(db_path)

    yield db_path

    # Cleanup
    try:
        Path(db_path).unlink()
    except FileNotFoundError:
        pass


@pytest.fixture
def repository(temp_db):
    """Fixture for repository with temp database."""
    return WhaleRepository(db_path=temp_db)


class TestWhaleTransactionModel:
    """Test WhaleTransaction data model."""

    def test_transaction_creation(self):
        """Test basic transaction creation."""
        tx = WhaleTransaction(
            transaction_id="abc123",
            timestamp=datetime.utcnow(),
            amount_btc=Decimal("150.5"),
            amount_usd=Decimal("15050000"),
            direction="BUY",
            urgency_score=75,
            fee_rate=50.0,
            confidence=0.95,
        )

        assert tx.transaction_id == "abc123"
        assert tx.amount_btc == Decimal("150.5")
        assert tx.direction == "BUY"
        assert tx.urgency_score == 75

    def test_transaction_validation_positive_amount(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValidationError):
            WhaleTransaction(
                transaction_id="abc123",
                timestamp=datetime.utcnow(),
                amount_btc=Decimal("-10"),  # Invalid
                amount_usd=Decimal("1000"),
                direction="BUY",
                urgency_score=50,
                fee_rate=10.0,
                confidence=0.8,
            )

    def test_transaction_validation_urgency_range(self):
        """Test urgency score range validation."""
        with pytest.raises(ValidationError):
            WhaleTransaction(
                transaction_id="abc123",
                timestamp=datetime.utcnow(),
                amount_btc=Decimal("100"),
                amount_usd=Decimal("10000"),
                direction="SELL",
                urgency_score=150,  # Invalid
                fee_rate=10.0,
                confidence=0.8,
            )

    def test_transaction_validation_confidence_range(self):
        """Test confidence range validation."""
        with pytest.raises(ValidationError):
            WhaleTransaction(
                transaction_id="abc123",
                timestamp=datetime.utcnow(),
                amount_btc=Decimal("100"),
                amount_usd=Decimal("10000"),
                direction="BUY",
                urgency_score=50,
                fee_rate=10.0,
                confidence=1.5,  # Invalid
            )

    def test_transaction_to_db_dict(self):
        """Test conversion to database dictionary."""
        tx = WhaleTransaction(
            transaction_id="abc123",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            amount_btc=Decimal("100.5"),
            amount_usd=Decimal("10050000"),
            direction="BUY",
            urgency_score=80,
            fee_rate=25.0,
            confidence=0.92,
        )

        db_dict = tx.to_db_dict()

        assert db_dict["transaction_id"] == "abc123"
        assert db_dict["amount_btc"] == 100.5
        assert db_dict["direction"] == "BUY"
        assert db_dict["urgency_score"] == 80
        assert isinstance(db_dict["timestamp"], str)


class TestNetFlowMetricsModel:
    """Test NetFlowMetrics data model."""

    def test_netflow_creation(self):
        """Test basic net flow metrics creation."""
        metrics = NetFlowMetrics(
            period_start=datetime(2025, 1, 1, 12, 0),
            period_end=datetime(2025, 1, 1, 12, 5),
            interval="5m",
            net_flow_btc=Decimal("50.0"),
            net_flow_usd=Decimal("5000000"),
            total_buy_btc=Decimal("100.0"),
            total_sell_btc=Decimal("50.0"),
            transaction_count=15,
            direction="ACCUMULATION",
            strength=0.75,
        )

        assert metrics.interval == "5m"
        assert metrics.net_flow_btc == Decimal("50.0")
        assert metrics.direction == "ACCUMULATION"
        assert metrics.transaction_count == 15

    def test_netflow_validation_transaction_count(self):
        """Test transaction count validation."""
        with pytest.raises(ValidationError):
            NetFlowMetrics(
                period_start=datetime.utcnow(),
                period_end=datetime.utcnow() + timedelta(minutes=5),
                interval="5m",
                net_flow_btc=Decimal("10"),
                net_flow_usd=Decimal("1000"),
                total_buy_btc=Decimal("20"),
                total_sell_btc=Decimal("10"),
                transaction_count=-5,  # Invalid
                direction="ACCUMULATION",
                strength=0.5,
            )

    def test_netflow_validation_strength_range(self):
        """Test strength range validation."""
        with pytest.raises(ValidationError):
            NetFlowMetrics(
                period_start=datetime.utcnow(),
                period_end=datetime.utcnow() + timedelta(minutes=5),
                interval="5m",
                net_flow_btc=Decimal("10"),
                net_flow_usd=Decimal("1000"),
                total_buy_btc=Decimal("20"),
                total_sell_btc=Decimal("10"),
                transaction_count=5,
                direction="ACCUMULATION",
                strength=1.5,  # Invalid
            )


class TestAlertModel:
    """Test Alert data model."""

    def test_alert_creation(self):
        """Test basic alert creation."""
        alert = Alert(
            alert_id="alert-123",
            transaction_id="tx-abc",
            severity="HIGH",
            trigger_type="SIZE",
            threshold_value=Decimal("500"),
            title="Large whale transaction detected",
            message="Transaction of 505 BTC detected",
            amount_btc=Decimal("505"),
            amount_usd=Decimal("50500000"),
            direction="BUY",
        )

        assert alert.severity == "HIGH"
        assert alert.trigger_type == "SIZE"
        assert alert.acknowledged is False

    def test_alert_validation_title_not_empty(self):
        """Test title validation."""
        with pytest.raises(ValidationError):
            Alert(
                alert_id="alert-123",
                transaction_id="tx-abc",
                severity="HIGH",
                trigger_type="SIZE",
                threshold_value=Decimal("500"),
                title="   ",  # Empty
                message="Valid message",
                amount_btc=Decimal("505"),
                amount_usd=Decimal("50500000"),
                direction="BUY",
            )


class TestWhaleRepository:
    """Test WhaleRepository functionality."""

    def test_repository_initialization(self, repository):
        """Test repository initializes correctly."""
        assert repository.db_path is not None
        assert Path(repository.db_path).exists()

    def test_save_transaction(self, repository):
        """Test saving single transaction."""
        tx = WhaleTransaction(
            transaction_id="tx-001",
            timestamp=datetime.utcnow(),
            amount_btc=Decimal("200"),
            amount_usd=Decimal("20000000"),
            direction="BUY",
            urgency_score=70,
            fee_rate=30.0,
            confidence=0.9,
        )

        result = repository.save_transaction(tx)
        assert result is True

        # Verify retrieval
        retrieved = repository.get_transaction("tx-001")
        assert retrieved is not None
        assert retrieved.transaction_id == "tx-001"
        assert retrieved.amount_btc == Decimal("200")

    def test_save_transactions_batch(self, repository):
        """Test batch saving transactions."""
        transactions = [
            WhaleTransaction(
                transaction_id=f"tx-{i:03d}",
                timestamp=datetime.utcnow(),
                amount_btc=Decimal(str(100 + i)),
                amount_usd=Decimal(str((100 + i) * 100000)),
                direction="BUY" if i % 2 == 0 else "SELL",
                urgency_score=50 + i,
                fee_rate=20.0 + i,
                confidence=0.85,
            )
            for i in range(10)
        ]

        count = repository.save_transactions_batch(transactions)
        assert count == 10

        # Verify all saved
        recent = repository.get_recent_transactions(limit=20)
        assert len(recent) >= 10

    def test_get_transaction_not_found(self, repository):
        """Test retrieving non-existent transaction."""
        result = repository.get_transaction("nonexistent")
        assert result is None

    def test_get_recent_transactions(self, repository):
        """Test getting recent transactions."""
        # Create test transactions
        for i in range(5):
            tx = WhaleTransaction(
                transaction_id=f"tx-recent-{i}",
                timestamp=datetime.utcnow() - timedelta(minutes=i),
                amount_btc=Decimal("150"),
                amount_usd=Decimal("15000000"),
                direction="BUY",
                urgency_score=60,
                fee_rate=25.0,
                confidence=0.88,
            )
            repository.save_transaction(tx)

        # Get recent
        recent = repository.get_recent_transactions(limit=3)

        assert len(recent) <= 3
        # Should be ordered by timestamp descending
        if len(recent) > 1:
            assert recent[0].timestamp >= recent[1].timestamp

    def test_get_recent_transactions_mempool_only(self, repository):
        """Test filtering mempool transactions."""
        # Create mempool and confirmed transactions
        for i in range(3):
            tx = WhaleTransaction(
                transaction_id=f"tx-mempool-{i}",
                timestamp=datetime.utcnow(),
                amount_btc=Decimal("120"),
                amount_usd=Decimal("12000000"),
                direction="BUY",
                urgency_score=65,
                fee_rate=28.0,
                confidence=0.87,
                is_mempool=True,
            )
            repository.save_transaction(tx)

        for i in range(2):
            tx = WhaleTransaction(
                transaction_id=f"tx-confirmed-{i}",
                block_height=800000 + i,
                timestamp=datetime.utcnow() - timedelta(hours=1),
                amount_btc=Decimal("110"),
                amount_usd=Decimal("11000000"),
                direction="SELL",
                urgency_score=55,
                fee_rate=22.0,
                confidence=0.91,
                is_mempool=False,
            )
            repository.save_transaction(tx)

        # Get mempool only
        mempool = repository.get_recent_transactions(limit=10, mempool_only=True)

        assert all(tx.is_mempool for tx in mempool)

    def test_get_transactions_by_timerange(self, repository):
        """Test getting transactions by time range."""
        now = datetime.utcnow()
        start = now - timedelta(hours=2)
        end = now

        # Create transactions at different times
        for i in range(5):
            tx = WhaleTransaction(
                transaction_id=f"tx-time-{i}",
                timestamp=start + timedelta(minutes=30 * i),
                amount_btc=Decimal("140"),
                amount_usd=Decimal("14000000"),
                direction="BUY",
                urgency_score=62,
                fee_rate=26.0,
                confidence=0.89,
            )
            repository.save_transaction(tx)

        # Query timerange
        results = repository.get_transactions_by_timerange(start, end)

        assert len(results) >= 5
        assert all(start <= tx.timestamp <= end for tx in results)

    def test_cleanup_old_transactions(self, repository):
        """Test cleanup of old transactions."""
        # Create old transaction
        old_tx = WhaleTransaction(
            transaction_id="tx-old",
            timestamp=datetime.utcnow() - timedelta(days=40),
            amount_btc=Decimal("100"),
            amount_usd=Decimal("10000000"),
            direction="BUY",
            urgency_score=50,
            fee_rate=20.0,
            confidence=0.85,
        )
        repository.save_transaction(old_tx)

        # Create recent transaction
        recent_tx = WhaleTransaction(
            transaction_id="tx-recent",
            timestamp=datetime.utcnow(),
            amount_btc=Decimal("110"),
            amount_usd=Decimal("11000000"),
            direction="SELL",
            urgency_score=55,
            fee_rate=22.0,
            confidence=0.87,
        )
        repository.save_transaction(recent_tx)

        # Cleanup with 30 day retention
        deleted = repository.cleanup_old_transactions(retention_days=30)

        # Old should be gone, recent should remain
        assert repository.get_transaction("tx-old") is None
        assert repository.get_transaction("tx-recent") is not None

    def test_save_net_flow(self, repository):
        """Test saving net flow metrics."""
        metrics = NetFlowMetrics(
            period_start=datetime(2025, 1, 1, 12, 0),
            period_end=datetime(2025, 1, 1, 12, 5),
            interval="5m",
            net_flow_btc=Decimal("75.0"),
            net_flow_usd=Decimal("7500000"),
            total_buy_btc=Decimal("125.0"),
            total_sell_btc=Decimal("50.0"),
            transaction_count=18,
            direction="ACCUMULATION",
            strength=0.8,
            largest_tx_btc=Decimal("50.0"),
        )

        result = repository.save_net_flow(metrics)
        assert result is True

        # Verify retrieval
        latest = repository.get_net_flow_latest(interval="5m", limit=1)
        assert len(latest) >= 1
        assert latest[0].net_flow_btc == Decimal("75.0")

    def test_get_net_flow_timerange(self, repository):
        """Test getting net flow by time range."""
        start = datetime(2025, 1, 1, 12, 0)

        # Create metrics for multiple intervals
        for i in range(5):
            metrics = NetFlowMetrics(
                period_start=start + timedelta(minutes=5 * i),
                period_end=start + timedelta(minutes=5 * (i + 1)),
                interval="5m",
                net_flow_btc=Decimal(str(10 + i)),
                net_flow_usd=Decimal(str((10 + i) * 100000)),
                total_buy_btc=Decimal(str(20 + i)),
                total_sell_btc=Decimal(str(10)),
                transaction_count=5 + i,
                direction="ACCUMULATION",
                strength=0.7,
            )
            repository.save_net_flow(metrics)

        # Query range
        end = start + timedelta(minutes=30)
        results = repository.get_net_flow_timerange(start, end, interval="5m")

        assert len(results) >= 5

    def test_save_alert(self, repository):
        """Test saving alert."""
        alert = Alert(
            alert_id="alert-001",
            transaction_id="tx-whale",
            severity="CRITICAL",
            trigger_type="SIZE",
            threshold_value=Decimal("500"),
            title="Massive whale transaction",
            message="Transaction of 750 BTC detected",
            amount_btc=Decimal("750"),
            amount_usd=Decimal("75000000"),
            direction="BUY",
        )

        result = repository.save_alert(alert)
        assert result is True

    def test_get_unacknowledged_alerts(self, repository):
        """Test getting unacknowledged alerts."""
        # Create alerts with different severities
        severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

        for i, severity in enumerate(severities):
            alert = Alert(
                alert_id=f"alert-sev-{i}",
                transaction_id=f"tx-{i}",
                severity=severity,
                trigger_type="SIZE",
                threshold_value=Decimal("100"),
                title=f"{severity} alert",
                message=f"Test {severity} severity",
                amount_btc=Decimal("150"),
                amount_usd=Decimal("15000000"),
                direction="BUY",
            )
            repository.save_alert(alert)

        # Get unacknowledged
        alerts = repository.get_unacknowledged_alerts(limit=10)

        assert len(alerts) >= 4
        # Should be ordered by severity (CRITICAL first)
        if len(alerts) >= 2:
            assert alerts[0].severity in ["CRITICAL", "HIGH"]

    def test_get_stats(self, repository):
        """Test database statistics."""
        # Create some test data
        tx = WhaleTransaction(
            transaction_id="tx-stats",
            timestamp=datetime.utcnow(),
            amount_btc=Decimal("100"),
            amount_usd=Decimal("10000000"),
            direction="BUY",
            urgency_score=60,
            fee_rate=25.0,
            confidence=0.9,
        )
        repository.save_transaction(tx)

        stats = repository.get_stats()

        assert "total_transactions" in stats
        assert "mempool_transactions" in stats
        assert "total_alerts" in stats
        assert stats["total_transactions"] >= 1
