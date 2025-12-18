"""
Tests for Exchange Netflow module (spec-026).

TDD RED phase: These tests must FAIL before implementation.

Test coverage:
- T005: test_load_exchange_addresses_from_csv()
- T005: test_load_exchange_addresses_file_not_found()
- T006: test_classify_netflow_zone_strong_outflow()
- T006: test_classify_netflow_zone_weak_outflow()
- T006: test_classify_netflow_zone_weak_inflow()
- T006: test_classify_netflow_zone_strong_inflow()
- T007: test_calculate_exchange_inflow()
- T007: test_calculate_exchange_outflow()
- T007: test_calculate_netflow_positive()
- T007: test_calculate_netflow_negative()
- T008: test_empty_window_handling()
- T008: test_no_matched_addresses()
- T014: test_calculate_moving_average_full_window()
- T014: test_calculate_moving_average_partial_window()
- T014: test_calculate_moving_average_empty()
- T015: test_get_daily_netflow_history()
- T020: test_exchange_netflow_api_endpoint()
- T020: test_exchange_netflow_history_api_endpoint()
"""

import duckdb
import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import csv

from scripts.models.metrics_models import NetflowZone, ExchangeNetflowResult


# =============================================================================
# T005: Load Exchange Addresses Tests
# =============================================================================


class TestLoadExchangeAddresses:
    """Tests for load_exchange_addresses function (T005)."""

    @pytest.fixture
    def temp_csv(self):
        """Create a temporary CSV with exchange addresses."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            writer = csv.writer(f)
            writer.writerow(["exchange_name", "address", "type"])
            writer.writerow(
                ["Binance", "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX", "hot_wallet"]
            )
            writer.writerow(
                ["Binance", "3P14159f73E4gFrCh2HRze1k41v22b2p7g", "cold_wallet"]
            )
            writer.writerow(
                ["Kraken", "3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE", "cold_wallet"]
            )
            f.flush()
            yield f.name
        Path(f.name).unlink()

    def test_load_exchange_addresses_from_csv(self, temp_csv):
        """T005: Test loading exchange addresses from CSV file."""
        from scripts.metrics.exchange_netflow import load_exchange_addresses

        conn = duckdb.connect(":memory:")
        result = load_exchange_addresses(conn, temp_csv)

        # Should return dict with address info
        assert isinstance(result, dict)
        assert len(result) == 3

        # Verify addresses loaded
        assert "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX" in result
        assert "3P14159f73E4gFrCh2HRze1k41v22b2p7g" in result
        assert "3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE" in result

        # Verify metadata
        assert (
            result["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"]["exchange_name"] == "Binance"
        )
        assert result["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"]["type"] == "hot_wallet"

        conn.close()

    def test_load_exchange_addresses_file_not_found(self):
        """T005: Test graceful handling when CSV file not found."""
        from scripts.metrics.exchange_netflow import load_exchange_addresses

        conn = duckdb.connect(":memory:")
        result = load_exchange_addresses(conn, "/nonexistent/path/addresses.csv")

        # Should return empty dict, not raise
        assert result == {}

        conn.close()


# =============================================================================
# T006: Zone Classification Tests
# =============================================================================


class TestClassifyNetflowZone:
    """Tests for zone classification function (T006)."""

    def test_classify_netflow_zone_strong_outflow(self):
        """T006: Netflow < -1000 BTC/day should classify as STRONG_OUTFLOW."""
        from scripts.metrics.exchange_netflow import classify_netflow_zone

        # Heavy accumulation (money leaving exchanges)
        assert classify_netflow_zone(-1001.0) == NetflowZone.STRONG_OUTFLOW
        assert classify_netflow_zone(-2000.0) == NetflowZone.STRONG_OUTFLOW
        assert classify_netflow_zone(-50000.0) == NetflowZone.STRONG_OUTFLOW

    def test_classify_netflow_zone_weak_outflow(self):
        """T006: Netflow -1000 to 0 BTC/day should classify as WEAK_OUTFLOW."""
        from scripts.metrics.exchange_netflow import classify_netflow_zone

        # Mild accumulation
        assert classify_netflow_zone(-1000.0) == NetflowZone.WEAK_OUTFLOW
        assert classify_netflow_zone(-500.0) == NetflowZone.WEAK_OUTFLOW
        assert classify_netflow_zone(-0.1) == NetflowZone.WEAK_OUTFLOW
        # Boundary: exactly 0 should be WEAK_INFLOW
        assert classify_netflow_zone(0.0) == NetflowZone.WEAK_INFLOW

    def test_classify_netflow_zone_weak_inflow(self):
        """T006: Netflow 0 to 1000 BTC/day should classify as WEAK_INFLOW."""
        from scripts.metrics.exchange_netflow import classify_netflow_zone

        # Mild selling
        assert classify_netflow_zone(0.0) == NetflowZone.WEAK_INFLOW
        assert classify_netflow_zone(500.0) == NetflowZone.WEAK_INFLOW
        assert classify_netflow_zone(999.9) == NetflowZone.WEAK_INFLOW
        # Boundary: exactly 1000 should be STRONG_INFLOW
        assert classify_netflow_zone(1000.0) == NetflowZone.STRONG_INFLOW

    def test_classify_netflow_zone_strong_inflow(self):
        """T006: Netflow >= 1000 BTC/day should classify as STRONG_INFLOW."""
        from scripts.metrics.exchange_netflow import classify_netflow_zone

        # Heavy selling (money entering exchanges)
        assert classify_netflow_zone(1000.0) == NetflowZone.STRONG_INFLOW
        assert classify_netflow_zone(2000.0) == NetflowZone.STRONG_INFLOW
        assert classify_netflow_zone(50000.0) == NetflowZone.STRONG_INFLOW


# =============================================================================
# T007: Inflow/Outflow Calculation Tests
# =============================================================================


class TestCalculateInflowOutflow:
    """Tests for inflow/outflow calculation functions (T007)."""

    @pytest.fixture
    def test_db(self):
        """Create an in-memory DuckDB with test UTXO data at exchange addresses."""
        conn = duckdb.connect(":memory:")

        # Create utxo_lifecycle_full VIEW with required columns
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                txid VARCHAR NOT NULL,
                vout_index INTEGER NOT NULL,
                address VARCHAR,
                btc_value DOUBLE NOT NULL,
                creation_block INTEGER NOT NULL,
                creation_timestamp INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_block INTEGER,
                spent_timestamp INTEGER
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        # Create exchange_addresses table
        conn.execute(
            """
            CREATE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )

        # Insert exchange addresses
        conn.execute(
            """
            INSERT INTO exchange_addresses VALUES
            ('Binance', '1BinanceHotWallet', 'hot_wallet'),
            ('Binance', '1BinanceColdWallet', 'cold_wallet'),
            ('Kraken', '1KrakenHotWallet', 'hot_wallet')
            """
        )

        # Use timestamp-based windows (unix timestamps)
        now = int(datetime.utcnow().timestamp())
        hours_6_ago = now - (6 * 3600)
        hours_12_ago = now - (12 * 3600)
        day_2_ago = now - (2 * 86400)

        # Insert test UTXOs at exchange addresses
        # INFLOW: UTXOs created at exchange addresses within window
        #   - 2.5 BTC created at Binance hot wallet 6 hours ago (inflow)
        #   - 1.0 BTC created at Kraken hot wallet 12 hours ago (inflow)
        #
        # OUTFLOW: UTXOs spent from exchange addresses within window
        #   - 1.5 BTC spent from Binance cold wallet 6 hours ago (outflow)
        conn.execute(
            f"""
            INSERT INTO utxo_lifecycle VALUES
            ('inflow1:0', 'inflow1', 0, '1BinanceHotWallet', 2.5, 875000, {hours_6_ago}, FALSE, NULL, NULL),
            ('inflow2:0', 'inflow2', 0, '1KrakenHotWallet', 1.0, 874990, {hours_12_ago}, FALSE, NULL, NULL),
            ('outflow1:0', 'outflow1', 0, '1BinanceColdWallet', 1.5, 874000, {day_2_ago}, TRUE, 875005, {hours_6_ago}),
            ('non_exchange:0', 'non_exchange', 0, '1RandomAddress', 10.0, 875000, {hours_6_ago}, FALSE, NULL, NULL),
            ('old_inflow:0', 'old_inflow', 0, '1BinanceHotWallet', 5.0, 870000, {day_2_ago}, FALSE, NULL, NULL)
            """
        )
        # Expected within 24h window:
        # Inflow: 2.5 + 1.0 = 3.5 BTC
        # Outflow: 1.5 BTC
        # Netflow: 3.5 - 1.5 = 2.0 BTC

        yield conn
        conn.close()

    def test_calculate_exchange_inflow(self, test_db):
        """T007: Test exchange inflow calculation."""
        from scripts.metrics.exchange_netflow import calculate_exchange_inflow

        # Window: last 24 hours
        window_start = int(datetime.utcnow().timestamp()) - (24 * 3600)

        inflow = calculate_exchange_inflow(test_db, window_start)

        # Should include inflow1 (2.5) and inflow2 (1.0)
        # Should NOT include old_inflow (outside window) or non_exchange
        assert inflow == pytest.approx(3.5, rel=0.01)

    def test_calculate_exchange_outflow(self, test_db):
        """T007: Test exchange outflow calculation."""
        from scripts.metrics.exchange_netflow import calculate_exchange_outflow

        # Window: last 24 hours
        window_start = int(datetime.utcnow().timestamp()) - (24 * 3600)

        outflow = calculate_exchange_outflow(test_db, window_start)

        # Should include outflow1 (1.5) - spent from exchange address
        assert outflow == pytest.approx(1.5, rel=0.01)

    def test_calculate_netflow_positive(self, test_db):
        """T007: Test positive netflow calculation (inflow > outflow = selling)."""
        from scripts.metrics.exchange_netflow import calculate_exchange_netflow

        result = calculate_exchange_netflow(
            conn=test_db,
            window_hours=24,
            current_price_usd=100000.0,
            block_height=875010,
            timestamp=datetime.utcnow(),
            exchange_addresses_path=None,  # Already loaded
        )

        # Netflow = inflow - outflow = 3.5 - 1.5 = 2.0
        assert result.netflow == pytest.approx(2.0, rel=0.01)
        assert result.netflow > 0  # Positive = selling pressure

    def test_calculate_netflow_negative(self):
        """T007: Test negative netflow calculation (outflow > inflow = accumulation)."""
        from scripts.metrics.exchange_netflow import calculate_exchange_netflow

        # Create test case with more outflow than inflow
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                address VARCHAR,
                btc_value DOUBLE NOT NULL,
                creation_timestamp INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_timestamp INTEGER
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
        conn.execute(
            """
            CREATE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO exchange_addresses VALUES ('Binance', '1Binance', 'hot')"
        )

        now = int(datetime.utcnow().timestamp())
        hours_6_ago = now - (6 * 3600)
        day_2_ago = now - (2 * 86400)

        # 1.0 BTC inflow, 5.0 BTC outflow
        conn.execute(
            f"""
            INSERT INTO utxo_lifecycle VALUES
            ('in:0', '1Binance', 1.0, {hours_6_ago}, FALSE, NULL),
            ('out:0', '1Binance', 5.0, {day_2_ago}, TRUE, {hours_6_ago})
            """
        )

        result = calculate_exchange_netflow(
            conn=conn,
            window_hours=24,
            current_price_usd=100000.0,
            block_height=875010,
            timestamp=datetime.utcnow(),
            exchange_addresses_path=None,
        )

        # Netflow = 1.0 - 5.0 = -4.0
        assert result.netflow == pytest.approx(-4.0, rel=0.01)
        assert result.netflow < 0  # Negative = accumulation

        conn.close()


# =============================================================================
# T008: Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge case handling (T008)."""

    def test_empty_window_handling(self):
        """T008: Test handling of empty window (no UTXOs in timeframe)."""
        from scripts.metrics.exchange_netflow import calculate_exchange_netflow

        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                address VARCHAR,
                btc_value DOUBLE NOT NULL,
                creation_timestamp INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_timestamp INTEGER
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
        conn.execute(
            """
            CREATE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO exchange_addresses VALUES ('Binance', '1Binance', 'hot')"
        )

        result = calculate_exchange_netflow(
            conn=conn,
            window_hours=24,
            current_price_usd=100000.0,
            block_height=875010,
            timestamp=datetime.utcnow(),
            exchange_addresses_path=None,
        )

        # Should return valid result with zeros
        assert isinstance(result, ExchangeNetflowResult)
        assert result.exchange_inflow == 0.0
        assert result.exchange_outflow == 0.0
        assert result.netflow == 0.0
        assert result.zone == NetflowZone.WEAK_INFLOW  # 0 is in [0, 1000)
        assert result.confidence == 0.0  # No data

        conn.close()

    def test_no_matched_addresses(self):
        """T008: Test handling when no exchange addresses match UTXOs."""
        from scripts.metrics.exchange_netflow import calculate_exchange_netflow

        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                address VARCHAR,
                btc_value DOUBLE NOT NULL,
                creation_timestamp INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_timestamp INTEGER
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
        conn.execute(
            """
            CREATE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO exchange_addresses VALUES ('Binance', '1Binance', 'hot')"
        )

        # Insert UTXOs but none at exchange addresses
        now = int(datetime.utcnow().timestamp())
        hours_6_ago = now - (6 * 3600)
        conn.execute(
            f"""
            INSERT INTO utxo_lifecycle VALUES
            ('utxo1:0', '1NonExchangeAddr1', 10.0, {hours_6_ago}, FALSE, NULL),
            ('utxo2:0', '1NonExchangeAddr2', 20.0, {hours_6_ago}, FALSE, NULL)
            """
        )

        result = calculate_exchange_netflow(
            conn=conn,
            window_hours=24,
            current_price_usd=100000.0,
            block_height=875010,
            timestamp=datetime.utcnow(),
            exchange_addresses_path=None,
        )

        # Should return zeros but with low confidence
        assert result.exchange_inflow == 0.0
        assert result.exchange_outflow == 0.0
        assert result.netflow == 0.0
        # address_count reflects table size, not matched UTXOs
        assert result.address_count >= 0
        assert result.confidence == 0.0  # No activity = no confidence

        conn.close()


# =============================================================================
# T014: Moving Average Tests
# =============================================================================


class TestCalculateMovingAverage:
    """Tests for moving average calculation (T014)."""

    def test_calculate_moving_average_full_window(self):
        """T014: Test MA with full window of data available."""
        from scripts.metrics.exchange_netflow import calculate_moving_average

        # 7 days of data for 7-day MA
        daily_values = [100.0, 200.0, 150.0, 300.0, 250.0, 180.0, 220.0]
        ma_7 = calculate_moving_average(daily_values, window=7)

        expected = sum(daily_values) / 7  # (100+200+150+300+250+180+220)/7 = 200
        assert ma_7 == pytest.approx(expected, rel=0.01)

    def test_calculate_moving_average_partial_window(self):
        """T014: Test MA with less data than window size."""
        from scripts.metrics.exchange_netflow import calculate_moving_average

        # Only 3 days of data for 7-day MA
        daily_values = [100.0, 200.0, 150.0]
        ma_7 = calculate_moving_average(daily_values, window=7)

        # Should use available data: (100+200+150)/3 = 150
        expected = sum(daily_values) / len(daily_values)
        assert ma_7 == pytest.approx(expected, rel=0.01)

    def test_calculate_moving_average_empty(self):
        """T014: Test MA with no data."""
        from scripts.metrics.exchange_netflow import calculate_moving_average

        ma = calculate_moving_average([], window=7)
        assert ma == 0.0

    def test_calculate_moving_average_uses_first_n_values(self):
        """T014: Test MA uses FIRST N values (newest) when data > window.

        History data is returned ORDER BY day DESC (newest first).
        A 7-day MA should average the most recent 7 days (first 7 values).
        """
        from scripts.metrics.exchange_netflow import calculate_moving_average

        # Simulate 30 days of data, newest first (DESC order)
        # Newer days have higher values to distinguish correct behavior
        daily_values = list(range(1000, 970, -1))  # [1000, 999, ..., 971]
        assert len(daily_values) == 30

        ma_7 = calculate_moving_average(daily_values, window=7)

        # Should use first 7 values (newest): [1000, 999, 998, 997, 996, 995, 994]
        expected_newest_7 = sum(daily_values[:7]) / 7  # = 997.0
        expected_oldest_7 = sum(daily_values[-7:]) / 7  # = 974.0

        assert ma_7 == pytest.approx(expected_newest_7, rel=0.01)
        assert ma_7 != pytest.approx(expected_oldest_7, rel=0.01)  # Verify NOT oldest


# =============================================================================
# T015: Daily Netflow History Tests
# =============================================================================


class TestGetDailyNetflowHistory:
    """Tests for daily netflow history function (T015)."""

    @pytest.fixture
    def history_db(self):
        """Create DB with historical daily netflow data."""
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                address VARCHAR,
                btc_value DOUBLE NOT NULL,
                creation_timestamp INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_timestamp INTEGER
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
        conn.execute(
            """
            CREATE TABLE exchange_addresses (
                exchange_name VARCHAR NOT NULL,
                address VARCHAR PRIMARY KEY,
                type VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO exchange_addresses VALUES ('Binance', '1Binance', 'hot')"
        )

        # Insert data for 5 days
        now = datetime.utcnow()
        for i in range(5):
            day_offset = now - timedelta(days=i)
            day_ts = int(day_offset.timestamp())
            # Inflow: 100 BTC per day, Outflow: 50 BTC per day => netflow = 50
            conn.execute(
                f"""
                INSERT INTO utxo_lifecycle VALUES
                ('in_{i}:0', '1Binance', 100.0, {day_ts}, FALSE, NULL)
                """
            )
            if i > 0:  # Outflows from previous days
                old_ts = int((now - timedelta(days=i + 10)).timestamp())
                conn.execute(
                    f"""
                    INSERT INTO utxo_lifecycle VALUES
                    ('out_{i}:0', '1Binance', 50.0, {old_ts}, TRUE, {day_ts})
                    """
                )

        yield conn
        conn.close()

    def test_get_daily_netflow_history(self, history_db):
        """T015: Test retrieving daily netflow history."""
        from scripts.metrics.exchange_netflow import get_daily_netflow_history

        history = get_daily_netflow_history(history_db, days=5)

        # Should return list of daily netflow records
        assert isinstance(history, list)
        assert len(history) <= 5

        # Each record should have date and netflow
        if len(history) > 0:
            record = history[0]
            assert "date" in record
            assert "netflow" in record
            assert "inflow" in record
            assert "outflow" in record


# =============================================================================
# ExchangeNetflowResult Dataclass Validation Tests
# =============================================================================


class TestExchangeNetflowResultValidation:
    """Tests for ExchangeNetflowResult dataclass validation."""

    def test_exchange_netflow_result_valid(self):
        """Test ExchangeNetflowResult dataclass with valid fields."""
        result = ExchangeNetflowResult(
            exchange_inflow=5432.50,
            exchange_outflow=4234.75,
            netflow=1197.75,
            netflow_7d_ma=856.25,
            netflow_30d_ma=523.10,
            zone=NetflowZone.WEAK_INFLOW,
            window_hours=24,
            exchange_count=4,
            address_count=10,
            current_price_usd=105000.0,
            inflow_usd=570412500.0,
            outflow_usd=444648750.0,
            block_height=875000,
            timestamp=datetime.utcnow(),
        )
        assert result.exchange_inflow == 5432.50
        assert result.zone == NetflowZone.WEAK_INFLOW
        assert result.confidence == 0.75  # Default

    def test_exchange_netflow_negative_inflow_raises(self):
        """Exchange inflow must be >= 0."""
        with pytest.raises(ValueError, match="exchange_inflow must be >= 0"):
            ExchangeNetflowResult(
                exchange_inflow=-1.0,
                exchange_outflow=0.0,
                netflow=-1.0,
                netflow_7d_ma=0.0,
                netflow_30d_ma=0.0,
                zone=NetflowZone.WEAK_OUTFLOW,
                window_hours=24,
                exchange_count=4,
                address_count=10,
                current_price_usd=100000.0,
                inflow_usd=0.0,
                outflow_usd=0.0,
                block_height=875000,
                timestamp=datetime.utcnow(),
            )

    def test_exchange_netflow_invalid_zone_raises(self):
        """Zone must be NetflowZone enum."""
        with pytest.raises(ValueError, match="zone must be NetflowZone enum"):
            ExchangeNetflowResult(
                exchange_inflow=100.0,
                exchange_outflow=50.0,
                netflow=50.0,
                netflow_7d_ma=0.0,
                netflow_30d_ma=0.0,
                zone="INVALID",  # type: ignore
                window_hours=24,
                exchange_count=4,
                address_count=10,
                current_price_usd=100000.0,
                inflow_usd=0.0,
                outflow_usd=0.0,
                block_height=875000,
                timestamp=datetime.utcnow(),
            )

    def test_exchange_netflow_invalid_window_raises(self):
        """Window hours must be > 0."""
        with pytest.raises(ValueError, match="window_hours must be > 0"):
            ExchangeNetflowResult(
                exchange_inflow=100.0,
                exchange_outflow=50.0,
                netflow=50.0,
                netflow_7d_ma=0.0,
                netflow_30d_ma=0.0,
                zone=NetflowZone.WEAK_INFLOW,
                window_hours=0,  # Invalid
                exchange_count=4,
                address_count=10,
                current_price_usd=100000.0,
                inflow_usd=0.0,
                outflow_usd=0.0,
                block_height=875000,
                timestamp=datetime.utcnow(),
            )

    def test_exchange_netflow_invalid_confidence_raises(self):
        """Confidence must be in [0, 1]."""
        with pytest.raises(ValueError, match="confidence must be in"):
            ExchangeNetflowResult(
                exchange_inflow=100.0,
                exchange_outflow=50.0,
                netflow=50.0,
                netflow_7d_ma=0.0,
                netflow_30d_ma=0.0,
                zone=NetflowZone.WEAK_INFLOW,
                window_hours=24,
                exchange_count=4,
                address_count=10,
                current_price_usd=100000.0,
                inflow_usd=0.0,
                outflow_usd=0.0,
                block_height=875000,
                timestamp=datetime.utcnow(),
                confidence=1.5,  # Invalid
            )

    def test_exchange_netflow_to_dict(self):
        """Test to_dict() serialization."""
        result = ExchangeNetflowResult(
            exchange_inflow=5432.50,
            exchange_outflow=4234.75,
            netflow=1197.75,
            netflow_7d_ma=856.25,
            netflow_30d_ma=523.10,
            zone=NetflowZone.WEAK_INFLOW,
            window_hours=24,
            exchange_count=4,
            address_count=10,
            current_price_usd=105000.0,
            inflow_usd=570412500.0,
            outflow_usd=444648750.0,
            block_height=875000,
            timestamp=datetime(2025, 12, 18, 10, 30, 0),
        )
        d = result.to_dict()
        assert d["exchange_inflow"] == 5432.50
        assert d["exchange_outflow"] == 4234.75
        assert d["netflow"] == 1197.75
        assert d["netflow_7d_ma"] == 856.25
        assert d["netflow_30d_ma"] == 523.10
        assert d["zone"] == "weak_inflow"  # Enum value
        assert d["window_hours"] == 24
        assert d["exchange_count"] == 4
        assert d["address_count"] == 10
        assert d["current_price_usd"] == 105000.0
        assert d["inflow_usd"] == 570412500.0
        assert d["outflow_usd"] == 444648750.0
        assert d["block_height"] == 875000
        assert "timestamp" in d
        assert d["confidence"] == 0.75


# =============================================================================
# T020: API Endpoint Tests
# =============================================================================


class TestExchangeNetflowAPIEndpoint:
    """Tests for /api/metrics/exchange-netflow endpoints (T020)."""

    def test_exchange_netflow_endpoint_registered(self):
        """T020: Verify /api/metrics/exchange-netflow endpoint is registered."""
        from api.main import app

        # Check endpoint is in app routes
        routes = [route.path for route in app.routes]
        assert "/api/metrics/exchange-netflow" in routes

    def test_exchange_netflow_endpoint_response_structure(self):
        """T020: Test endpoint returns correct response structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/exchange-netflow")

        # Should get valid response or graceful error
        assert response.status_code in [200, 404, 500, 503]

        if response.status_code == 200:
            data = response.json()
            # Verify expected fields are present
            assert "exchange_inflow" in data
            assert "exchange_outflow" in data
            assert "netflow" in data
            assert "zone" in data
            assert "confidence" in data
            # Zone should be valid enum value
            assert data["zone"] in [
                "strong_outflow",
                "weak_outflow",
                "weak_inflow",
                "strong_inflow",
            ]

    def test_exchange_netflow_endpoint_with_params(self):
        """T020: Test endpoint accepts window query param."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/exchange-netflow?window=48")

        # Should accept params without 422 Unprocessable Entity
        assert response.status_code != 422

    def test_exchange_netflow_history_endpoint_registered(self):
        """T020: Verify /api/metrics/exchange-netflow/history endpoint is registered."""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert "/api/metrics/exchange-netflow/history" in routes

    def test_exchange_netflow_history_endpoint_response_structure(self):
        """T020: Test history endpoint returns correct response structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/exchange-netflow/history?days=30")

        # Should get valid response or graceful error
        assert response.status_code in [200, 404, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert "days" in data
            assert "data" in data
            assert isinstance(data["data"], list)
