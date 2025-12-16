"""
TDD tests for STH/LTH Cost Basis calculator (spec-023).

These tests follow the Red-Green-Refactor TDD cycle:
1. RED: Tests written FIRST, all should FAIL before implementation
2. GREEN: Implement minimal code to pass tests
3. REFACTOR: Improve code while maintaining test coverage

Test Coverage:
- T003: test_calculate_sth_cost_basis_basic
- T004: test_calculate_lth_cost_basis_basic
- T005: test_calculate_total_cost_basis
- T006: test_cost_basis_mvrv_calculation
- T007: test_zero_cost_basis_mvrv_returns_zero
- T008: test_empty_cohort_handling
- T009: test_calculate_cost_basis_signal_full
- T010: test_cost_basis_api_endpoint
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import duckdb

from scripts.models.metrics_models import CostBasisResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_connection():
    """Create in-memory DuckDB connection with test data."""
    conn = duckdb.connect(":memory:")

    # Create utxo_lifecycle_full VIEW structure
    conn.execute("""
        CREATE TABLE utxo_lifecycle_full (
            txid VARCHAR,
            vout INTEGER,
            creation_block INTEGER,
            btc_value DOUBLE,
            creation_price_usd DOUBLE,
            realized_value_usd DOUBLE,
            is_spent BOOLEAN,
            age_days INTEGER
        )
    """)

    return conn


@pytest.fixture
def populated_db_connection(mock_db_connection):
    """Create DB with sample UTXOs for testing."""
    conn = mock_db_connection

    # Insert sample data:
    # STH UTXOs (age < 155 days, creation_block > current_block - 22320)
    # Current block = 875000, so STH cutoff = 875000 - 22320 = 852680

    # STH UTXOs (created after block 852680)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx1', 0, 870000, 1.0, 60000.0, 60000.0, FALSE, 30),
        ('tx2', 0, 865000, 2.0, 70000.0, 140000.0, FALSE, 60),
        ('tx3', 0, 860000, 0.5, 65000.0, 32500.0, FALSE, 100)
    """)

    # LTH UTXOs (created before block 852680)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx4', 0, 800000, 5.0, 30000.0, 150000.0, FALSE, 500),
        ('tx5', 0, 750000, 10.0, 25000.0, 250000.0, FALSE, 800)
    """)

    # Spent UTXO (should be excluded)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx6', 0, 850000, 3.0, 50000.0, 150000.0, TRUE, 200)
    """)

    # UTXO with NULL price (should be excluded)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx7', 0, 860000, 1.0, NULL, NULL, FALSE, 100)
    """)

    return conn


# =============================================================================
# T003: test_calculate_sth_cost_basis_basic
# =============================================================================


def test_calculate_sth_cost_basis_basic(populated_db_connection):
    """Test STH cost basis calculation with sample data.

    STH UTXOs (block > 852680):
    - tx1: 1.0 BTC @ $60,000 = $60,000 realized
    - tx2: 2.0 BTC @ $70,000 = $140,000 realized
    - tx3: 0.5 BTC @ $65,000 = $32,500 realized

    Expected:
    - Total STH supply: 3.5 BTC
    - Total STH realized: $232,500
    - STH Cost Basis: $232,500 / 3.5 = $66,428.57
    """
    from scripts.metrics.cost_basis import calculate_sth_cost_basis

    result = calculate_sth_cost_basis(
        conn=populated_db_connection, current_block=875000
    )

    assert result is not None
    expected_cost_basis = 232500.0 / 3.5  # $66,428.57
    assert abs(result["sth_cost_basis"] - expected_cost_basis) < 0.01
    assert abs(result["sth_supply_btc"] - 3.5) < 0.001


# =============================================================================
# T004: test_calculate_lth_cost_basis_basic
# =============================================================================


def test_calculate_lth_cost_basis_basic(populated_db_connection):
    """Test LTH cost basis calculation with sample data.

    LTH UTXOs (block <= 852680):
    - tx4: 5.0 BTC @ $30,000 = $150,000 realized
    - tx5: 10.0 BTC @ $25,000 = $250,000 realized

    Expected:
    - Total LTH supply: 15.0 BTC
    - Total LTH realized: $400,000
    - LTH Cost Basis: $400,000 / 15.0 = $26,666.67
    """
    from scripts.metrics.cost_basis import calculate_lth_cost_basis

    result = calculate_lth_cost_basis(
        conn=populated_db_connection, current_block=875000
    )

    assert result is not None
    expected_cost_basis = 400000.0 / 15.0  # $26,666.67
    assert abs(result["lth_cost_basis"] - expected_cost_basis) < 0.01
    assert abs(result["lth_supply_btc"] - 15.0) < 0.001


# =============================================================================
# T005: test_calculate_total_cost_basis
# =============================================================================


def test_calculate_total_cost_basis(populated_db_connection):
    """Test total cost basis calculation (all unspent UTXOs).

    All unspent UTXOs with valid price:
    - tx1: 1.0 BTC @ $60,000 = $60,000
    - tx2: 2.0 BTC @ $70,000 = $140,000
    - tx3: 0.5 BTC @ $65,000 = $32,500
    - tx4: 5.0 BTC @ $30,000 = $150,000
    - tx5: 10.0 BTC @ $25,000 = $250,000

    Expected:
    - Total supply: 18.5 BTC
    - Total realized: $632,500
    - Total Cost Basis: $632,500 / 18.5 = $34,189.19
    """
    from scripts.metrics.cost_basis import calculate_total_cost_basis

    result = calculate_total_cost_basis(conn=populated_db_connection)

    assert result is not None
    expected_cost_basis = 632500.0 / 18.5  # $34,189.19
    assert abs(result["total_cost_basis"] - expected_cost_basis) < 0.01


# =============================================================================
# T006: test_cost_basis_mvrv_calculation
# =============================================================================


def test_cost_basis_mvrv_calculation():
    """Test MVRV calculation from cost basis.

    MVRV = current_price / cost_basis

    Example:
    - Current price: $95,000
    - STH cost basis: $66,428.57
    - STH MVRV: 95000 / 66428.57 = 1.43

    - LTH cost basis: $26,666.67
    - LTH MVRV: 95000 / 26666.67 = 3.56
    """
    from scripts.metrics.cost_basis import calculate_cost_basis_mvrv

    current_price = 95000.0
    sth_cost_basis = 66428.57
    lth_cost_basis = 26666.67

    sth_mvrv = calculate_cost_basis_mvrv(current_price, sth_cost_basis)
    lth_mvrv = calculate_cost_basis_mvrv(current_price, lth_cost_basis)

    expected_sth_mvrv = 95000.0 / 66428.57  # ~1.43
    expected_lth_mvrv = 95000.0 / 26666.67  # ~3.56

    assert abs(sth_mvrv - expected_sth_mvrv) < 0.01
    assert abs(lth_mvrv - expected_lth_mvrv) < 0.01


# =============================================================================
# T007: test_zero_cost_basis_mvrv_returns_zero
# =============================================================================


def test_zero_cost_basis_mvrv_returns_zero():
    """Test that MVRV returns 0 when cost_basis is 0 (no division error).

    Edge case: Empty cohort with no UTXOs has cost_basis = 0.
    MVRV should return 0.0, not raise ZeroDivisionError.
    """
    from scripts.metrics.cost_basis import calculate_cost_basis_mvrv

    current_price = 95000.0
    cost_basis = 0.0

    # Should NOT raise ZeroDivisionError
    mvrv = calculate_cost_basis_mvrv(current_price, cost_basis)

    assert mvrv == 0.0


# =============================================================================
# T008: test_empty_cohort_handling
# =============================================================================


def test_empty_cohort_handling(mock_db_connection):
    """Test handling of empty cohorts (no UTXOs matching criteria).

    When a cohort is empty:
    - cost_basis should be 0.0
    - supply_btc should be 0.0
    - No exceptions should be raised
    """
    from scripts.metrics.cost_basis import calculate_sth_cost_basis

    # Empty database - no UTXOs
    result = calculate_sth_cost_basis(conn=mock_db_connection, current_block=875000)

    assert result is not None
    assert result["sth_cost_basis"] == 0.0
    assert result["sth_supply_btc"] == 0.0


# =============================================================================
# T009: test_calculate_cost_basis_signal_full
# =============================================================================


def test_calculate_cost_basis_signal_full(populated_db_connection):
    """Test full cost basis signal calculation (orchestrator function).

    Should return a complete CostBasisResult with all fields populated.
    """
    from scripts.metrics.cost_basis import calculate_cost_basis_signal

    result = calculate_cost_basis_signal(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
        timestamp=datetime(2025, 12, 16, 10, 0, 0),
    )

    # Verify result is CostBasisResult instance
    assert isinstance(result, CostBasisResult)

    # Verify all required fields are present
    assert result.sth_cost_basis > 0
    assert result.lth_cost_basis > 0
    assert result.total_cost_basis > 0
    assert result.sth_mvrv > 0
    assert result.lth_mvrv > 0
    assert result.sth_supply_btc > 0
    assert result.lth_supply_btc > 0
    assert result.current_price_usd == 95000.0
    assert result.block_height == 875000
    assert result.confidence > 0

    # Verify to_dict works
    result_dict = result.to_dict()
    assert "sth_cost_basis" in result_dict
    assert "timestamp" in result_dict


# =============================================================================
# T010: test_cost_basis_api_endpoint
# =============================================================================


def test_cost_basis_api_endpoint():
    """Test GET /api/metrics/cost-basis endpoint.

    Should return JSON with all CostBasisResult fields.
    """
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)

    # Create mock result
    mock_result = CostBasisResult(
        sth_cost_basis=65000.0,
        lth_cost_basis=28000.0,
        total_cost_basis=42000.0,
        sth_mvrv=1.46,
        lth_mvrv=3.39,
        sth_supply_btc=2500000.0,
        lth_supply_btc=17000000.0,
        current_price_usd=95000.0,
        block_height=875000,
        timestamp=datetime(2025, 12, 16, 10, 0, 0),
        confidence=0.85,
    )

    # Mock the calculate_cost_basis_signal function where it's imported
    with patch(
        "scripts.metrics.cost_basis.calculate_cost_basis_signal",
        return_value=mock_result,
    ):
        # Mock duckdb.connect to return a mock connection
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (875000,)

        with patch("duckdb.connect", return_value=mock_conn):
            response = client.get("/api/metrics/cost-basis")

            # Should return 200 OK
            assert response.status_code == 200

            data = response.json()

            # Verify all fields present
            assert "sth_cost_basis" in data
            assert "lth_cost_basis" in data
            assert "total_cost_basis" in data
            assert "sth_mvrv" in data
            assert "lth_mvrv" in data
            assert "sth_supply_btc" in data
            assert "lth_supply_btc" in data
            assert "current_price_usd" in data
            assert "block_height" in data
            assert "timestamp" in data
            assert "confidence" in data
