"""
TDD tests for Address Balance Cohorts calculator (spec-039).

These tests follow the Red-Green-Refactor TDD cycle:
1. RED: Tests written FIRST, all should FAIL before implementation
2. GREEN: Implement minimal code to pass tests
3. REFACTOR: Improve code while maintaining test coverage

Test Coverage:
- T005: test_calculate_retail_cohort_basic
- T006: test_calculate_whale_cohort_basic
- T007: test_calculate_mid_tier_cohort_basic
- T008: test_cohort_mvrv_calculation
- T009: test_whale_retail_spread_calculation
- T010: test_empty_cohort_handling
- T011: test_null_address_excluded

Cohort Thresholds:
- RETAIL: < 1 BTC
- MID_TIER: 1-100 BTC
- WHALE: >= 100 BTC
"""

import pytest
import duckdb

from scripts.models.metrics_models import (
    AddressCohort,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_connection():
    """Create in-memory DuckDB connection with test schema."""
    conn = duckdb.connect(":memory:")

    # Create utxo_lifecycle_full VIEW structure with address column
    conn.execute("""
        CREATE TABLE utxo_lifecycle_full (
            txid VARCHAR,
            vout INTEGER,
            address VARCHAR,
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
    """Create DB with sample UTXOs covering all cohorts."""
    conn = mock_db_connection

    # RETAIL cohort addresses (total balance < 1 BTC per address)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx1', 0, 'addr_retail_1', 870000, 0.5, 40000.0, 20000.0, FALSE, 30),
        ('tx2', 0, 'addr_retail_2', 865000, 0.3, 50000.0, 15000.0, FALSE, 60),
        ('tx3', 0, 'addr_retail_3', 860000, 0.2, 45000.0, 9000.0, FALSE, 100)
    """)

    # MID_TIER cohort addresses (1-100 BTC per address)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx4', 0, 'addr_mid_1', 850000, 10.0, 35000.0, 350000.0, FALSE, 200),
        ('tx5', 0, 'addr_mid_1', 840000, 5.0, 30000.0, 150000.0, FALSE, 250),
        ('tx6', 0, 'addr_mid_2', 830000, 50.0, 28000.0, 1400000.0, FALSE, 300)
    """)

    # WHALE cohort addresses (>= 100 BTC per address)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx7', 0, 'addr_whale_1', 800000, 500.0, 25000.0, 12500000.0, FALSE, 500),
        ('tx8', 0, 'addr_whale_1', 750000, 200.0, 20000.0, 4000000.0, FALSE, 800),
        ('tx9', 0, 'addr_whale_2', 700000, 1000.0, 15000.0, 15000000.0, FALSE, 1200)
    """)

    # Spent UTXO (should be excluded)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx10', 0, 'addr_spent', 850000, 3.0, 50000.0, 150000.0, TRUE, 200)
    """)

    # UTXO with NULL address (should be excluded)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx11', 0, NULL, 860000, 1.0, 40000.0, 40000.0, FALSE, 100)
    """)

    # UTXO with NULL price (should be excluded)
    conn.execute("""
        INSERT INTO utxo_lifecycle_full VALUES
        ('tx12', 0, 'addr_null_price', 860000, 1.0, NULL, NULL, FALSE, 100)
    """)

    return conn


@pytest.fixture
def empty_db_connection(mock_db_connection):
    """Create DB with no UTXOs for edge case testing."""
    return mock_db_connection


# =============================================================================
# T005: test_calculate_retail_cohort_basic
# =============================================================================


def test_calculate_retail_cohort_basic(populated_db_connection):
    """Test retail cohort calculation with sample data.

    Sample data: 3 addresses with < 1 BTC each
    - addr_retail_1: 0.5 BTC @ $40,000
    - addr_retail_2: 0.3 BTC @ $50,000
    - addr_retail_3: 0.2 BTC @ $45,000

    Expected:
    - Total BTC: 1.0
    - Cost basis: (0.5*40000 + 0.3*50000 + 0.2*45000) / 1.0 = $44,000
    - Address count: 3
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    assert result.retail.cohort == AddressCohort.RETAIL
    assert result.retail.supply_btc == pytest.approx(1.0, rel=0.01)
    assert result.retail.cost_basis == pytest.approx(44000.0, rel=0.01)
    assert result.retail.address_count == 3


# =============================================================================
# T006: test_calculate_whale_cohort_basic
# =============================================================================


def test_calculate_whale_cohort_basic(populated_db_connection):
    """Test whale cohort calculation with sample data.

    Sample data: 2 addresses with >= 100 BTC each
    - addr_whale_1: 700 BTC (500 @ $25,000 + 200 @ $20,000)
      Cost basis: (500*25000 + 200*20000) / 700 = $23,571.43
    - addr_whale_2: 1000 BTC @ $15,000

    Expected:
    - Total BTC: 1700
    - Cost basis: (12500000 + 4000000 + 15000000) / 1700 = $18,529.41
    - Address count: 2
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    assert result.whale.cohort == AddressCohort.WHALE
    assert result.whale.supply_btc == pytest.approx(1700.0, rel=0.01)
    # Cost basis: (500*25000 + 200*20000 + 1000*15000) / 1700 = 31,500,000 / 1700 = 18,529.41
    assert result.whale.cost_basis == pytest.approx(18529.41, rel=0.01)
    assert result.whale.address_count == 2


# =============================================================================
# T007: test_calculate_mid_tier_cohort_basic
# =============================================================================


def test_calculate_mid_tier_cohort_basic(populated_db_connection):
    """Test mid-tier cohort calculation with sample data.

    Sample data: 2 addresses with 1-100 BTC each
    - addr_mid_1: 15 BTC (10 @ $35,000 + 5 @ $30,000)
      Cost basis: (350000 + 150000) / 15 = $33,333.33
    - addr_mid_2: 50 BTC @ $28,000

    Expected:
    - Total BTC: 65
    - Cost basis: (350000 + 150000 + 1400000) / 65 = $29,230.77
    - Address count: 2
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    assert result.mid_tier.cohort == AddressCohort.MID_TIER
    assert result.mid_tier.supply_btc == pytest.approx(65.0, rel=0.01)
    # Cost basis: (10*35000 + 5*30000 + 50*28000) / 65 = 1,900,000 / 65 = 29,230.77
    assert result.mid_tier.cost_basis == pytest.approx(29230.77, rel=0.01)
    assert result.mid_tier.address_count == 2


# =============================================================================
# T008: test_cohort_mvrv_calculation
# =============================================================================


def test_cohort_mvrv_calculation(populated_db_connection):
    """Test MVRV calculation for each cohort.

    MVRV = current_price / cost_basis

    With current_price = $95,000:
    - Retail MVRV: 95000 / 44000 = 2.159
    - Mid-tier MVRV: 95000 / 29230.77 = 3.250
    - Whale MVRV: 95000 / 18529.41 = 5.127
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    # Retail MVRV: 95000 / 44000 ≈ 2.16
    assert result.retail.mvrv == pytest.approx(2.159, rel=0.05)

    # Mid-tier MVRV: 95000 / 29230.77 ≈ 3.25
    assert result.mid_tier.mvrv == pytest.approx(3.25, rel=0.05)

    # Whale MVRV: 95000 / 18529.41 ≈ 5.13
    assert result.whale.mvrv == pytest.approx(5.13, rel=0.05)


# =============================================================================
# T009: test_whale_retail_spread_calculation
# =============================================================================


def test_whale_retail_spread_calculation(populated_db_connection):
    """Test cross-cohort signal calculations.

    whale_retail_spread = whale_cost_basis - retail_cost_basis
                        = 18529.41 - 44000 = -25,470.59

    Negative spread indicates whales bought at lower prices (conviction).

    whale_retail_mvrv_ratio = whale_mvrv / retail_mvrv
                            = 5.127 / 2.159 = 2.375

    Ratio > 1 indicates whales more profitable than retail.
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    # Spread: whale_cb - retail_cb = 18529.41 - 44000 = -25,470.59
    assert result.whale_retail_spread == pytest.approx(-25470.59, rel=0.02)

    # MVRV ratio: whale_mvrv / retail_mvrv ≈ 5.13 / 2.16 ≈ 2.38
    assert result.whale_retail_mvrv_ratio == pytest.approx(2.38, rel=0.05)


# =============================================================================
# T010: test_empty_cohort_handling
# =============================================================================


def test_empty_cohort_handling(empty_db_connection):
    """Test handling of empty cohorts gracefully.

    When no UTXOs exist, all cohorts should have:
    - supply_btc = 0.0
    - cost_basis = 0.0
    - mvrv = 0.0
    - address_count = 0
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=empty_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    # All cohorts should be empty
    for cohort in [result.retail, result.mid_tier, result.whale]:
        assert cohort.supply_btc == 0.0
        assert cohort.cost_basis == 0.0
        assert cohort.mvrv == 0.0
        assert cohort.address_count == 0

    # Cross-cohort signals with zero cost basis
    assert result.whale_retail_spread == 0.0
    assert result.whale_retail_mvrv_ratio == 0.0

    # Totals
    assert result.total_supply_btc == 0.0
    assert result.total_addresses == 0


# =============================================================================
# T011: test_null_address_excluded
# =============================================================================


def test_null_address_excluded(populated_db_connection):
    """Test that UTXOs with NULL address are excluded.

    The test data includes:
    - tx11: NULL address, 1.0 BTC @ $40,000 (should be EXCLUDED)
    - tx12: NULL creation_price_usd (should be EXCLUDED)

    Total supply should be sum of valid cohorts only.
    """
    from scripts.metrics.address_cohorts import calculate_address_cohorts

    result = calculate_address_cohorts(
        conn=populated_db_connection,
        current_block=875000,
        current_price_usd=95000.0,
    )

    # Total supply = retail (1.0) + mid_tier (65) + whale (1700) = 1766
    # NOT including NULL address (1.0) or NULL price (1.0)
    assert result.total_supply_btc == pytest.approx(1766.0, rel=0.01)

    # Total addresses = 3 (retail) + 2 (mid) + 2 (whale) = 7
    # NOT including NULL address or NULL price
    assert result.total_addresses == 7


# =============================================================================
# T019: test_address_cohorts_api_endpoint_success
# =============================================================================


def test_address_cohorts_api_endpoint_success():
    """Test API endpoint returns valid JSON response.

    GET /api/metrics/address-cohorts?current_price=98500

    Expected response structure matches spec.md API definition.
    """
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)

    # Test with explicit current_price parameter
    response = client.get("/api/metrics/address-cohorts?current_price=98500")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "timestamp" in data
    assert "block_height" in data
    assert "current_price_usd" in data
    assert "cohorts" in data
    assert "retail" in data["cohorts"]
    assert "mid_tier" in data["cohorts"]
    assert "whale" in data["cohorts"]
    assert "analysis" in data
    assert "whale_retail_spread" in data["analysis"]
    assert "whale_retail_mvrv_ratio" in data["analysis"]
    assert "total_supply_btc" in data
    assert "total_addresses" in data


# =============================================================================
# T020: test_address_cohorts_api_endpoint_error_handling
# =============================================================================


def test_address_cohorts_api_endpoint_error_handling():
    """Test API endpoint handles errors gracefully.

    Test cases:
    - Default current_price works (has default value)
    - Invalid current_price (negative) → 422 Validation Error
    - Invalid current_price (zero) → 422 Validation Error
    """
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)

    # Test default current_price works (endpoint has default=100000.0)
    response = client.get("/api/metrics/address-cohorts")
    assert response.status_code == 200  # Default value is valid

    # Test invalid current_price (negative) - FastAPI validation rejects ge=1.0
    response = client.get("/api/metrics/address-cohorts?current_price=-100")
    assert response.status_code == 422  # FastAPI validation error

    # Test invalid current_price (zero) - FastAPI validation rejects ge=1.0
    response = client.get("/api/metrics/address-cohorts?current_price=0")
    assert response.status_code == 422  # FastAPI validation error
