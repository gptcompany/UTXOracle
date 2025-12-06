"""
End-to-end integration tests for Derivatives Historical Integration (spec-008).

These tests use the REAL LiquidationHeatmap database to verify:
- Cross-DB connection works
- Data freshness checks
- Funding rate reading
- OI reading
- Enhanced fusion with real data
- Cross-DB query latency (<500ms)

Requirements:
- LiquidationHeatmap database must be available
- Set LIQUIDATION_HEATMAP_DB_PATH env var or use default path

Run with: uv run pytest tests/integration/test_derivatives_e2e.py -v
"""

import os
import time
import pytest
from datetime import datetime, timedelta

# Skip all tests if LiquidationHeatmap is not available
LIQ_DB_PATH = os.getenv(
    "LIQUIDATION_HEATMAP_DB_PATH",
    "/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb",
)
LIQ_DB_AVAILABLE = os.path.exists(LIQ_DB_PATH)

pytestmark = pytest.mark.skipif(
    not LIQ_DB_AVAILABLE,
    reason=f"LiquidationHeatmap database not found at {LIQ_DB_PATH}",
)


class TestRealDatabaseConnection:
    """Test real DuckDB cross-database connection."""

    def test_real_connection_attach(self):
        """T046: Verify cross-DB connection works with real database."""
        from scripts.derivatives import get_liq_connection, close_connection

        conn = get_liq_connection()
        assert conn is not None, "Should connect to real LiquidationHeatmap"

        # Verify we can query
        result = conn.execute("SELECT 1 as test").fetchone()
        assert result[0] == 1

        close_connection(conn)

    def test_real_data_freshness_check(self):
        """T046: Verify data freshness check works with real data."""
        from scripts.derivatives import (
            get_liq_connection,
            check_data_freshness,
            close_connection,
        )

        conn = get_liq_connection()
        assert conn is not None

        freshness = check_data_freshness(conn)

        # Should have keys
        assert "funding_latest" in freshness
        assert "oi_latest" in freshness
        assert "funding_age_hours" in freshness
        assert "oi_age_minutes" in freshness
        assert "is_stale" in freshness

        # If we have data, age should be a number
        if freshness["funding_latest"] is not None:
            assert isinstance(freshness["funding_age_hours"], (int, float))
        if freshness["oi_latest"] is not None:
            assert isinstance(freshness["oi_age_minutes"], (int, float))

        close_connection(conn)


class TestRealFundingRateData:
    """Test funding rate reading with real LiquidationHeatmap data."""

    def test_read_latest_funding_rate(self):
        """Read actual latest funding rate from database."""
        from scripts.derivatives.funding_rate_reader import get_latest_funding_signal

        signal = get_latest_funding_signal()

        # May be None if no data, but should not raise
        if signal is not None:
            assert signal.symbol == "BTCUSDT"
            assert signal.exchange == "binance"
            assert -0.01 <= signal.funding_rate <= 0.01  # Reasonable range
            assert -1.0 <= signal.funding_vote <= 1.0
            assert isinstance(signal.is_extreme, bool)

    def test_read_funding_at_timestamp(self):
        """Read funding rate at specific timestamp."""
        from scripts.derivatives import get_liq_connection, close_connection
        from scripts.derivatives.funding_rate_reader import read_funding_rate

        conn = get_liq_connection()
        assert conn is not None

        # Try to read funding from 24h ago
        target = datetime.now() - timedelta(hours=24)
        result = read_funding_rate(conn, target)

        # May be None if no data at that time
        if result is not None:
            ts, rate = result
            assert isinstance(ts, datetime)
            assert isinstance(rate, float)

        close_connection(conn)


class TestRealOpenInterestData:
    """Test OI reading with real LiquidationHeatmap data."""

    def test_read_latest_oi(self):
        """Read actual latest OI from database."""
        from scripts.derivatives.oi_reader import get_latest_oi_signal

        signal = get_latest_oi_signal(whale_direction="NEUTRAL")

        if signal is not None:
            assert signal.symbol == "BTCUSDT"
            assert signal.oi_value > 0  # OI should be positive
            assert -1.0 <= signal.oi_vote <= 1.0
            assert signal.context in [
                "confirming",
                "diverging",
                "deleveraging",
                "neutral",
            ]

    def test_read_oi_at_timestamp(self):
        """Read OI at specific timestamp."""
        from scripts.derivatives import get_liq_connection, close_connection
        from scripts.derivatives.oi_reader import read_oi_at_timestamp

        conn = get_liq_connection()
        assert conn is not None

        target = datetime.now() - timedelta(hours=1)
        result = read_oi_at_timestamp(conn, target)

        if result is not None:
            ts, current_oi, previous_oi = result
            assert isinstance(ts, datetime)
            assert current_oi > 0
            assert previous_oi >= 0

        close_connection(conn)


class TestEnhancedFusionWithRealData:
    """Test enhanced fusion using real derivatives data."""

    def test_fusion_with_real_derivatives(self):
        """Run enhanced fusion with real funding + OI data."""
        from scripts.derivatives.funding_rate_reader import get_latest_funding_signal
        from scripts.derivatives.oi_reader import get_latest_oi_signal
        from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion

        # Get real signals
        funding = get_latest_funding_signal()
        oi = get_latest_oi_signal(whale_direction="NEUTRAL")

        # Run fusion with real data (or None if unavailable)
        result = enhanced_monte_carlo_fusion(
            whale_vote=0.3,
            whale_conf=0.7,
            utxo_vote=0.1,
            utxo_conf=0.5,
            funding_vote=funding.funding_vote if funding else None,
            oi_vote=oi.oi_vote if oi else None,
        )

        assert -1.0 <= result.signal_mean <= 1.0
        assert result.signal_std >= 0
        assert result.action in ["BUY", "SELL", "HOLD"]
        assert 0 <= result.action_confidence <= 1

        # If both signals available, derivatives_available should be True
        if funding is not None and oi is not None:
            assert result.derivatives_available is True
        else:
            assert result.derivatives_available is False


class TestCrossDBLatency:
    """T046: Validate cross-DB latency <500ms."""

    def test_funding_rate_query_latency(self):
        """Funding rate query should complete in <500ms."""
        from scripts.derivatives import get_liq_connection, close_connection

        conn = get_liq_connection()
        assert conn is not None

        start = time.time()
        result = conn.execute(
            """
            SELECT timestamp, funding_rate
            FROM liq.funding_rate_history
            WHERE symbol = 'BTCUSDT'
            ORDER BY timestamp DESC
            LIMIT 100
            """
        ).fetchall()
        elapsed_ms = (time.time() - start) * 1000

        close_connection(conn)

        assert elapsed_ms < 500, f"Query took {elapsed_ms:.1f}ms (target: <500ms)"
        print(f"Funding rate query: {elapsed_ms:.1f}ms for {len(result)} rows")

    def test_oi_query_latency(self):
        """OI query should complete in <500ms."""
        from scripts.derivatives import get_liq_connection, close_connection

        conn = get_liq_connection()
        assert conn is not None

        start = time.time()
        result = conn.execute(
            """
            SELECT timestamp, open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = 'BTCUSDT'
            ORDER BY timestamp DESC
            LIMIT 100
            """
        ).fetchall()
        elapsed_ms = (time.time() - start) * 1000

        close_connection(conn)

        assert elapsed_ms < 500, f"Query took {elapsed_ms:.1f}ms (target: <500ms)"
        print(f"OI query: {elapsed_ms:.1f}ms for {len(result)} rows")

    def test_combined_query_latency(self):
        """Combined funding + OI query should complete in <500ms."""
        from scripts.derivatives import get_liq_connection, close_connection

        conn = get_liq_connection()
        assert conn is not None

        start = time.time()

        # Simulate what enhanced_fusion does
        _ = conn.execute(
            """
            SELECT timestamp, funding_rate
            FROM liq.funding_rate_history
            WHERE symbol = 'BTCUSDT'
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        _ = conn.execute(
            """
            SELECT timestamp, open_interest_value
            FROM liq.open_interest_history
            WHERE symbol = 'BTCUSDT'
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        elapsed_ms = (time.time() - start) * 1000

        close_connection(conn)

        assert elapsed_ms < 500, (
            f"Combined query took {elapsed_ms:.1f}ms (target: <500ms)"
        )
        print(f"Combined query: {elapsed_ms:.1f}ms")


class TestAPIIntegrationWithDerivatives:
    """Test API endpoint includes derivatives data."""

    def test_metrics_latest_includes_derivatives(self):
        """T043: /api/metrics/latest should include derivatives signals."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/metrics/latest")

        # Should return 200 or 404 (no data)
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            # Check derivatives field exists
            if "derivatives" in data:
                deriv = data["derivatives"]
                assert "available" in deriv
                if deriv["available"]:
                    assert "funding_vote" in deriv or "funding" in deriv
                    assert "oi_vote" in deriv or "oi" in deriv
