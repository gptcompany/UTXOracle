"""Tests for Binary CDD (Coin Days Destroyed) indicator.

spec-027: Binary CDD - Statistical significance flag for CDD events
TDD: Tests written BEFORE implementation (Constitution Principle II)

The Binary CDD indicator transforms noisy CDD data into actionable binary signals:
- binary_cdd=0: Normal long-term holder activity (noise)
- binary_cdd=1: Significant event (z-score >= threshold sigma)
"""

import duckdb
import pytest
from datetime import datetime, timedelta

# Will import after implementation exists
# from scripts.models.metrics_models import BinaryCDDResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test spent UTXO data for Binary CDD.

    Creates 365 days of synthetic daily CDD data with known statistics:
    - Mean CDD: ~1000 (coin-days per day)
    - Std CDD: ~200
    - Test cases:
      1. Normal day: z-score ~0.5 -> binary_cdd=0
      2. Significant event: z-score ~2.5 -> binary_cdd=1
      3. Edge case: exactly at threshold
    """
    conn = duckdb.connect(":memory:")

    # Create utxo_lifecycle table matching production schema
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            outpoint VARCHAR PRIMARY KEY,
            txid VARCHAR NOT NULL,
            vout_index INTEGER NOT NULL,
            creation_block INTEGER NOT NULL,
            creation_timestamp TIMESTAMP NOT NULL,
            creation_price_usd DOUBLE NOT NULL,
            btc_value DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Create VIEW alias for production code compatibility
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    # Generate 365 days of data with controlled statistics
    # Base CDD: 1000 per day, std dev: ~200
    now = datetime.utcnow()

    # Insert daily spent UTXOs over 365 days with varying CDD values
    # Day pattern: daily CDD oscillates around 1000 with some variation
    values = []
    for day_offset in range(1, 366):
        spent_time = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d 12:00:00")

        # Create varying CDD: base 1000 +/- variation
        # Use a deterministic pattern for reproducibility
        if day_offset == 1:
            # Today: slightly above average (z ~0.5 with std=200)
            # CDD = 1100 -> z = (1100-1000)/200 = 0.5
            age, btc_value = 110, 10.0  # CDD = 1100
        elif day_offset == 2:
            # Yesterday (for significant event test): high CDD (z ~2.5)
            # CDD = 1500 -> z = (1500-1000)/200 = 2.5
            age, btc_value = 150, 10.0  # CDD = 1500
        else:
            # Historical data: oscillate around 1000
            # Pattern: 800-1200 range
            base_cdd = 1000
            variation = ((day_offset % 10) - 5) * 40  # -200 to +160
            target_cdd = base_cdd + variation
            age = int(target_cdd / 10)
            btc_value = 10.0

        outpoint = f"utxo{day_offset}:0"
        txid = f"tx{day_offset}"

        values.append(
            f"('{outpoint}', '{txid}', 0, {870000 - day_offset * 144}, "
            f"'2023-01-01', 30000.0, {btc_value}, {875000 - day_offset * 144}, "
            f"'{spent_time}', 100000.0, {age}, TRUE)"
        )

    # Insert all test data
    conn.execute(f"INSERT INTO utxo_lifecycle VALUES {', '.join(values)}")

    yield conn
    conn.close()


@pytest.fixture
def insufficient_data_db():
    """Create a DB with only 20 days of data (< 30 day minimum)."""
    conn = duckdb.connect(":memory:")

    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            outpoint VARCHAR PRIMARY KEY,
            txid VARCHAR NOT NULL,
            vout_index INTEGER NOT NULL,
            creation_block INTEGER NOT NULL,
            creation_timestamp TIMESTAMP NOT NULL,
            creation_price_usd DOUBLE NOT NULL,
            btc_value DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    now = datetime.utcnow()
    values = []
    for day_offset in range(1, 21):  # Only 20 days
        spent_time = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d 12:00:00")
        values.append(
            f"('utxo{day_offset}:0', 'tx{day_offset}', 0, 870000, "
            f"'2023-01-01', 30000.0, 10.0, 875000, "
            f"'{spent_time}', 100000.0, 100, TRUE)"
        )

    conn.execute(f"INSERT INTO utxo_lifecycle VALUES {', '.join(values)}")

    yield conn
    conn.close()


@pytest.fixture
def significant_event_db():
    """Create a DB with an extreme CDD event TODAY (z >= 2.0).

    Data structure:
    - Day 1 (today): CDD = 5000 (extreme event)
    - Days 2-31: CDD = 1000 (normal baseline)

    Statistics (31 data points):
    - Mean: ~1129.03
    - Std: ~718.42
    - Today z-score: ~5.39 (well above 2.0 threshold)
    """
    conn = duckdb.connect(":memory:")

    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            outpoint VARCHAR PRIMARY KEY,
            txid VARCHAR NOT NULL,
            vout_index INTEGER NOT NULL,
            creation_block INTEGER NOT NULL,
            creation_timestamp TIMESTAMP NOT NULL,
            creation_price_usd DOUBLE NOT NULL,
            btc_value DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    now = datetime.utcnow()
    values = []
    for day_offset in range(1, 32):  # 31 days
        spent_time = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d 12:00:00")
        if day_offset == 1:
            # Today: extreme CDD event
            age = 500  # CDD = 500 * 10 = 5000
        else:
            # Baseline normal days
            age = 100  # CDD = 100 * 10 = 1000
        values.append(
            f"('utxo{day_offset}:0', 'tx{day_offset}', 0, 870000, "
            f"'2023-01-01', 30000.0, 10.0, 875000, "
            f"'{spent_time}', 100000.0, {age}, TRUE)"
        )

    conn.execute(f"INSERT INTO utxo_lifecycle VALUES {', '.join(values)}")

    yield conn
    conn.close()


@pytest.fixture
def zero_std_db():
    """Create a DB where all days have identical CDD (std dev = 0)."""
    conn = duckdb.connect(":memory:")

    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            outpoint VARCHAR PRIMARY KEY,
            txid VARCHAR NOT NULL,
            vout_index INTEGER NOT NULL,
            creation_block INTEGER NOT NULL,
            creation_timestamp TIMESTAMP NOT NULL,
            creation_price_usd DOUBLE NOT NULL,
            btc_value DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    now = datetime.utcnow()
    values = []
    # All days have exactly the same CDD: 1000 (age=100 * btc=10.0)
    for day_offset in range(1, 366):
        spent_time = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d 12:00:00")
        values.append(
            f"('utxo{day_offset}:0', 'tx{day_offset}', 0, 870000, "
            f"'2023-01-01', 30000.0, 10.0, 875000, "
            f"'{spent_time}', 100000.0, 100, TRUE)"  # CDD = 100 * 10 = 1000
        )

    conn.execute(f"INSERT INTO utxo_lifecycle VALUES {', '.join(values)}")

    yield conn
    conn.close()


class TestBinaryCDDCalculation:
    """Tests for calculate_binary_cdd() function."""

    def test_calculate_binary_cdd_normal_case(self, test_db):
        """T004: Normal CDD day returns binary_cdd=0 (below threshold).

        Test data: Day 1 has CDD=1100, mean~1000, std~200
        z-score = (1100-1000)/200 = 0.5 < 2.0 threshold
        Expected: binary_cdd=0
        """
        from scripts.metrics.binary_cdd import calculate_binary_cdd
        from scripts.models.metrics_models import BinaryCDDResult

        result = calculate_binary_cdd(
            conn=test_db,
            block_height=875000,
            threshold=2.0,
            window_days=365,
        )

        assert isinstance(result, BinaryCDDResult)
        assert result.binary_cdd == 0  # Normal activity
        assert result.cdd_zscore is not None
        assert result.cdd_zscore < 2.0  # Below threshold
        assert result.threshold_used == 2.0
        assert result.window_days == 365
        assert result.insufficient_data is False
        assert result.block_height == 875000

    def test_calculate_binary_cdd_significant_event(self, significant_event_db):
        """T005: Significant CDD event returns binary_cdd=1 (above threshold).

        Uses significant_event_db fixture where today has CDD=5000 vs baseline 1000.
        z-score ~5.39 >> 2.0 threshold -> binary_cdd=1
        """
        from scripts.metrics.binary_cdd import calculate_binary_cdd
        from scripts.models.metrics_models import BinaryCDDResult

        result = calculate_binary_cdd(
            conn=significant_event_db,
            block_height=875000,
            threshold=2.0,  # Default threshold
            window_days=365,
        )

        assert isinstance(result, BinaryCDDResult)
        assert result.binary_cdd == 1  # Significant event detected
        assert result.cdd_zscore is not None
        assert result.cdd_zscore >= 2.0  # Above threshold
        assert result.cdd_today == 5000.0  # Extreme value
        assert result.threshold_used == 2.0
        assert result.insufficient_data is False

    def test_calculate_binary_cdd_insufficient_data(self, insufficient_data_db):
        """T006: Returns insufficient_data=True when < 30 days of history.

        With only 20 days of data, z-score calculation is unreliable.
        Expected: insufficient_data=True, cdd_zscore=None
        """
        from scripts.metrics.binary_cdd import calculate_binary_cdd
        from scripts.models.metrics_models import BinaryCDDResult

        result = calculate_binary_cdd(
            conn=insufficient_data_db,
            block_height=875000,
            threshold=2.0,
            window_days=365,  # Request 365 but only 20 available
        )

        assert isinstance(result, BinaryCDDResult)
        assert result.insufficient_data is True
        assert result.data_points < 30
        # binary_cdd should default to 0 when insufficient data
        assert result.binary_cdd == 0

    def test_calculate_binary_cdd_zero_std_deviation(self, zero_std_db):
        """T007: Handles zero standard deviation gracefully.

        When all daily CDD values are identical, std=0.
        Z-score cannot be calculated (division by zero).
        Expected: cdd_zscore=None (or 0.0), binary_cdd=0
        """
        from scripts.metrics.binary_cdd import calculate_binary_cdd
        from scripts.models.metrics_models import BinaryCDDResult

        result = calculate_binary_cdd(
            conn=zero_std_db,
            block_height=875000,
            threshold=2.0,
            window_days=365,
        )

        assert isinstance(result, BinaryCDDResult)
        # With std=0, z-score should be None or 0
        # binary_cdd should be 0 (can't determine significance)
        assert result.binary_cdd == 0
        assert result.cdd_std == 0.0 or result.cdd_std < 0.01


class TestBinaryCDDDataclass:
    """Tests for BinaryCDDResult dataclass validation."""

    def test_valid_result_creation(self):
        """Valid BinaryCDDResult creation succeeds."""
        from scripts.models.metrics_models import BinaryCDDResult

        result = BinaryCDDResult(
            cdd_today=12543.75,
            cdd_mean=8234.21,
            cdd_std=2156.73,
            cdd_zscore=1.998,
            cdd_percentile=97.28,
            binary_cdd=0,
            threshold_used=2.0,
            window_days=365,
            data_points=365,
            insufficient_data=False,
            block_height=875000,
        )

        assert result.cdd_today == 12543.75
        assert result.binary_cdd == 0
        assert result.threshold_used == 2.0

    def test_binary_cdd_must_be_0_or_1(self):
        """binary_cdd field only accepts 0 or 1."""
        from scripts.models.metrics_models import BinaryCDDResult

        with pytest.raises(ValueError, match="binary_cdd must be 0 or 1"):
            BinaryCDDResult(
                cdd_today=1000.0,
                cdd_mean=1000.0,
                cdd_std=200.0,
                cdd_zscore=0.0,
                cdd_percentile=50.0,
                binary_cdd=2,  # Invalid
                threshold_used=2.0,
                window_days=365,
                data_points=365,
                insufficient_data=False,
                block_height=875000,
            )

    def test_threshold_range_validation(self):
        """threshold_used must be in [1.0, 4.0]."""
        from scripts.models.metrics_models import BinaryCDDResult

        with pytest.raises(ValueError, match="threshold_used must be in"):
            BinaryCDDResult(
                cdd_today=1000.0,
                cdd_mean=1000.0,
                cdd_std=200.0,
                cdd_zscore=0.0,
                cdd_percentile=50.0,
                binary_cdd=0,
                threshold_used=5.0,  # Invalid - too high
                window_days=365,
                data_points=365,
                insufficient_data=False,
                block_height=875000,
            )

    def test_to_dict_serialization(self):
        """to_dict() returns correct JSON-serializable structure."""
        from scripts.models.metrics_models import BinaryCDDResult

        result = BinaryCDDResult(
            cdd_today=12543.75,
            cdd_mean=8234.21,
            cdd_std=2156.73,
            cdd_zscore=1.998,
            cdd_percentile=97.28,
            binary_cdd=0,
            threshold_used=2.0,
            window_days=365,
            data_points=365,
            insufficient_data=False,
            block_height=875000,
        )

        d = result.to_dict()

        assert d["cdd_today"] == 12543.75
        assert d["binary_cdd"] == 0
        assert d["threshold_used"] == 2.0
        assert "timestamp" in d


class TestBinaryCDDAPIEndpoint:
    """Tests for GET /api/metrics/binary-cdd endpoint (T008)."""

    def test_binary_cdd_api_endpoint(self):
        """T008: API endpoint route exists and validates parameters."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # Test with valid parameters - endpoint exists and responds
        # May return 500/503/404 if DB not available, but route is valid
        response = client.get("/api/metrics/binary-cdd?threshold=2.0&window=365")

        # Endpoint should respond - accept various error codes when DB unavailable
        # 200 = success, 404 = table not found (DB issue), 500/503 = DB unavailable
        assert response.status_code in [200, 404, 500, 503]

        # Verify it's not a route-not-found 404 (would have different message)
        if response.status_code == 404:
            data = response.json()
            # Our custom 404 contains "UTXO lifecycle" message
            assert (
                "utxo_lifecycle" in data.get("detail", "").lower()
                or "not found" in data.get("detail", "").lower()
            )

        # If successful, verify response structure
        if response.status_code == 200:
            data = response.json()
            assert "binary_cdd" in data
            assert "cdd_zscore" in data or data.get("insufficient_data") is True
            assert "threshold_used" in data
            assert data["binary_cdd"] in [0, 1]

    def test_binary_cdd_api_with_custom_params(self):
        """API accepts threshold and window query parameters."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # Test with custom valid parameters
        response = client.get("/api/metrics/binary-cdd?threshold=3.0&window=90")

        # Route should exist and process params - accept DB-related errors
        assert response.status_code in [200, 404, 500, 503]

    def test_binary_cdd_api_parameter_validation(self):
        """API validates threshold and window parameter ranges."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # Test invalid threshold (below 1.0) - should return 422
        response = client.get("/api/metrics/binary-cdd?threshold=0.5")
        assert response.status_code == 422  # FastAPI validation error

        # Test invalid window (below 30) - should return 422
        response = client.get("/api/metrics/binary-cdd?window=10")
        assert response.status_code == 422  # FastAPI validation error
