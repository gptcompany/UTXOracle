"""
Test fixtures for SOPR module - spec-016

Provides reusable test data for SOPR calculations, block aggregation,
and signal detection tests.
"""

import pytest
from datetime import datetime, timedelta


# =============================================================================
# SpentOutputSOPR Fixtures
# =============================================================================


@pytest.fixture
def sample_spent_output_profit():
    """Sample spent output sold at profit (SOPR = 2.0)."""
    return {
        "creation_price": 50000.0,
        "spend_price": 100000.0,
        "btc_value": 1.0,
        "age_days": 30,
        "expected_sopr": 2.0,
        "expected_cohort": "STH",
        "expected_profit_loss": "PROFIT",
    }


@pytest.fixture
def sample_spent_output_loss():
    """Sample spent output sold at loss (SOPR = 0.5)."""
    return {
        "creation_price": 100000.0,
        "spend_price": 50000.0,
        "btc_value": 1.0,
        "age_days": 30,
        "expected_sopr": 0.5,
        "expected_cohort": "STH",
        "expected_profit_loss": "LOSS",
    }


@pytest.fixture
def sample_spent_output_breakeven():
    """Sample spent output sold at breakeven (SOPR ≈ 1.0)."""
    return {
        "creation_price": 100000.0,
        "spend_price": 100000.0,
        "btc_value": 1.0,
        "age_days": 30,
        "expected_sopr": 1.0,
        "expected_cohort": "STH",
        "expected_profit_loss": "BREAKEVEN",
    }


@pytest.fixture
def sample_spent_output_lth():
    """Sample spent output from long-term holder (age >= 155 days)."""
    return {
        "creation_price": 30000.0,
        "spend_price": 100000.0,
        "btc_value": 2.5,
        "age_days": 200,
        "expected_sopr": 3.33,
        "expected_cohort": "LTH",
        "expected_profit_loss": "PROFIT",
    }


# =============================================================================
# BlockSOPR Fixtures
# =============================================================================


@pytest.fixture
def sample_block_outputs_mixed():
    """Mixed block outputs with STH and LTH, profit and loss."""
    # Import here to avoid circular import issues during fixture creation
    # The actual SpentOutputSOPR will be created by calculate_output_sopr

    # Return specs for creating outputs
    return _create_mixed_outputs()


def _create_mixed_outputs():
    """Helper to create mixed output list."""
    try:
        from scripts.metrics.sopr import calculate_output_sopr
    except ImportError:
        # Return empty list if module not yet implemented
        return []

    outputs = []

    # STH outputs (age < 155 days)
    for i in range(60):
        outputs.append(
            calculate_output_sopr(
                creation_price=50000.0 + (i * 100),
                spend_price=100000.0,
                btc_value=0.5 + (i * 0.01),
                age_days=30 + (i % 100),
            )
        )

    # LTH outputs (age >= 155 days)
    for i in range(40):
        outputs.append(
            calculate_output_sopr(
                creation_price=30000.0 + (i * 200),
                spend_price=100000.0,
                btc_value=1.0 + (i * 0.05),
                age_days=155 + (i * 10),
            )
        )

    return outputs


@pytest.fixture
def sample_block_sopr_valid():
    """Valid BlockSOPR with sufficient samples."""
    try:
        from scripts.metrics.sopr import BlockSOPR
    except ImportError:
        return None

    return BlockSOPR(
        block_height=800000,
        block_hash="0000000000000000000abc123def456",
        timestamp=datetime.now(),
        aggregate_sopr=1.5,
        sth_sopr=1.3,
        lth_sopr=2.1,
        total_outputs=150,
        valid_outputs=140,
        sth_outputs=90,
        lth_outputs=50,
        total_btc_moved=500.0,
        sth_btc_moved=200.0,
        lth_btc_moved=300.0,
        profit_outputs=100,
        loss_outputs=35,
        breakeven_outputs=5,
        profit_ratio=0.714,
        is_valid=True,
        min_samples=100,
    )


# =============================================================================
# SOPRWindow / Signal Fixtures
# =============================================================================


@pytest.fixture
def sample_sopr_window():
    """SOPR window showing STH capitulation pattern (STH-SOPR < 1.0 for 3+ days)."""
    try:
        from scripts.metrics.sopr import BlockSOPR
    except ImportError:
        return []

    # Create 7-day window with STH capitulation pattern
    base_time = datetime.now() - timedelta(days=7)
    window = []

    for i in range(7):
        window.append(
            BlockSOPR(
                block_height=800000 + (i * 144),  # ~144 blocks per day
                block_hash=f"000000000000000000{i:04d}",
                timestamp=base_time + timedelta(days=i),
                aggregate_sopr=0.85 + (i * 0.01),  # Slowly recovering
                sth_sopr=0.80 + (i * 0.02),  # STH below 1.0 for first 5 days
                lth_sopr=1.5,  # LTH stable
                total_outputs=150,
                valid_outputs=140,
                sth_outputs=90,
                lth_outputs=50,
                total_btc_moved=500.0,
                sth_btc_moved=200.0,
                lth_btc_moved=300.0,
                profit_outputs=40,
                loss_outputs=95,
                breakeven_outputs=5,
                profit_ratio=0.286,
                is_valid=True,
                min_samples=100,
            )
        )

    return window


@pytest.fixture
def sample_sopr_window_neutral():
    """SOPR window with no strong signals."""
    try:
        from scripts.metrics.sopr import BlockSOPR
    except ImportError:
        return []

    base_time = datetime.now() - timedelta(days=7)
    window = []

    for i in range(7):
        window.append(
            BlockSOPR(
                block_height=800000 + (i * 144),
                block_hash=f"000000000000000000{i:04d}",
                timestamp=base_time + timedelta(days=i),
                aggregate_sopr=1.1,
                sth_sopr=1.05,
                lth_sopr=1.2,
                total_outputs=150,
                valid_outputs=140,
                sth_outputs=90,
                lth_outputs=50,
                total_btc_moved=500.0,
                sth_btc_moved=200.0,
                lth_btc_moved=300.0,
                profit_outputs=80,
                loss_outputs=55,
                breakeven_outputs=5,
                profit_ratio=0.571,
                is_valid=True,
                min_samples=100,
            )
        )

    return window


# =============================================================================
# Price Lookup Fixtures
# =============================================================================


@pytest.fixture
def mock_historical_prices():
    """Mock historical price data for testing."""
    return {
        799000: 95000.0,
        799500: 96500.0,
        800000: 100000.0,
        800500: 102000.0,
        801000: 98000.0,
    }


@pytest.fixture
def mock_rpc_client():
    """Mock Bitcoin Core RPC client."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.getrawtransaction.return_value = {
        "txid": "abc123",
        "blockhash": "000000000000000000def456",
        "vin": [{"txid": "prev123", "vout": 0}],
        "vout": [{"value": 1.5, "n": 0}],
    }
    mock.getblock.return_value = {
        "height": 799000,
        "hash": "000000000000000000def456",
        "time": 1700000000,
    }

    return mock
