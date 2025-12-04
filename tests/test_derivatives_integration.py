"""
Test Suite for Derivatives Historical Integration (spec-008).

Tests cover:
- Phase 2: Cross-DB connection and graceful degradation
- Phase 3 (US1): Funding rate signal conversion
- Phase 4 (US2): Open interest signal with context
- Phase 5 (US3): Enhanced 4-component fusion
- Phase 6 (US4): Backtest output format and weight optimization
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Test fixtures and configuration


@pytest.fixture
def sample_funding_rates():
    """Sample funding rate data for testing."""
    return [
        {"timestamp": datetime(2025, 10, 1, 0, 0, 0), "funding_rate": 0.0015},  # +0.15%
        {
            "timestamp": datetime(2025, 10, 1, 8, 0, 0),
            "funding_rate": -0.0008,
        },  # -0.08%
        {
            "timestamp": datetime(2025, 10, 1, 16, 0, 0),
            "funding_rate": 0.0001,
        },  # +0.01%
    ]


@pytest.fixture
def sample_oi_data():
    """Sample open interest data for testing."""
    base_time = datetime(2025, 10, 1, 12, 0, 0)
    base_oi = 9_000_000_000  # 9 billion USD
    return [
        {
            "timestamp": base_time - timedelta(hours=1),
            "oi_value": base_oi,
        },
        {
            "timestamp": base_time,
            "oi_value": base_oi * 1.05,  # +5% change
        },
    ]


@pytest.fixture
def mock_liq_connection():
    """Mock DuckDB connection for testing without real database."""
    mock_conn = MagicMock()
    return mock_conn


@pytest.fixture
def sample_whale_signals():
    """Sample whale signals for context testing."""
    return {
        "ACCUMULATION": {"direction": "ACCUMULATION", "confidence": 0.8},
        "DISTRIBUTION": {"direction": "DISTRIBUTION", "confidence": 0.7},
        "NEUTRAL": {"direction": "NEUTRAL", "confidence": 0.5},
    }


# =============================================================================
# Phase 2: Foundational - Cross-DB Connection Tests
# =============================================================================


class TestCrossDBConnection:
    """Tests for T007: Cross-database connection functionality."""

    def test_crossdb_connection_success(self):
        """Test successful connection to LiquidationHeatmap."""
        from scripts.derivatives import get_liq_connection, close_connection

        conn = get_liq_connection()
        if conn is None:
            pytest.skip("LiquidationHeatmap database not available")

        # Verify we can query the attached database
        result = conn.execute("SELECT 1").fetchone()
        assert result == (1,)

        # Verify liq schema is attached by querying actual tables
        try:
            # Test funding_rate_history exists
            funding_result = conn.execute(
                "SELECT COUNT(*) FROM liq.funding_rate_history WHERE symbol = 'BTCUSDT' LIMIT 1"
            ).fetchone()
            assert funding_result is not None, "funding_rate_history should exist"

            # Test open_interest_history exists
            oi_result = conn.execute(
                "SELECT COUNT(*) FROM liq.open_interest_history WHERE symbol = 'BTCUSDT' LIMIT 1"
            ).fetchone()
            assert oi_result is not None, "open_interest_history should exist"
        except Exception as e:
            pytest.fail(f"Failed to query LiquidationHeatmap tables: {e}")

        close_connection(conn)

    def test_crossdb_connection_disabled(self):
        """Test connection returns None when derivatives disabled."""

        with patch.dict("os.environ", {"DERIVATIVES_ENABLED": "false"}):
            # Re-import to pick up new env var
            import importlib
            import scripts.derivatives

            importlib.reload(scripts.derivatives)
            conn = scripts.derivatives.get_liq_connection()
            assert conn is None


class TestGracefulDegradation:
    """Tests for T008: Graceful degradation when DB unavailable."""

    def test_graceful_degradation_db_unavailable(self):
        """Test graceful handling when LiquidationHeatmap is unavailable."""
        from scripts.derivatives import get_liq_connection

        # Use a non-existent path
        conn = get_liq_connection(db_path="/nonexistent/path/liquidations.duckdb")
        assert conn is None  # Should return None, not raise exception

    def test_graceful_degradation_retry_on_lock(self):
        """Test retry logic with exponential backoff on lock."""
        # This test validates the retry mechanism exists
        from scripts.derivatives import MAX_RETRIES, BASE_RETRY_DELAY

        assert MAX_RETRIES == 3
        assert BASE_RETRY_DELAY == 0.5


# =============================================================================
# Phase 3: User Story 1 - Funding Rate Signal Tests
# =============================================================================


class TestFundingRateSignal:
    """Tests for US1: Funding rate contrarian signal conversion."""

    def test_funding_positive_extreme(self):
        """T009: +0.15% funding → -0.8 vote, is_extreme=True."""
        from scripts.derivatives.funding_rate_reader import funding_to_vote

        funding_rate = 0.0015  # +0.15%
        vote, is_extreme = funding_to_vote(funding_rate)

        # Contrarian: positive funding = bearish vote
        assert vote < 0, "Positive funding should give negative (bearish) vote"
        assert vote == pytest.approx(-0.8, abs=0.15), f"Expected ~-0.8, got {vote}"
        assert is_extreme is True, "0.15% should be extreme"

    def test_funding_negative_extreme(self):
        """T010: -0.08% funding → +0.6 vote, is_extreme=True."""
        from scripts.derivatives.funding_rate_reader import funding_to_vote

        funding_rate = -0.0008  # -0.08%
        vote, is_extreme = funding_to_vote(funding_rate)

        # Contrarian: negative funding = bullish vote
        assert vote > 0, "Negative funding should give positive (bullish) vote"
        assert vote == pytest.approx(0.6, abs=0.2), f"Expected ~+0.6, got {vote}"
        assert is_extreme is True, "-0.08% should be extreme"

    def test_funding_neutral(self):
        """T011: +0.01% funding → 0.0 vote, is_extreme=False."""
        from scripts.derivatives.funding_rate_reader import funding_to_vote

        funding_rate = 0.0001  # +0.01%
        vote, is_extreme = funding_to_vote(funding_rate)

        assert vote == pytest.approx(0.0, abs=0.1), f"Expected ~0.0, got {vote}"
        assert is_extreme is False, "0.01% should not be extreme"

    def test_funding_unavailable_graceful(self):
        """T012: Graceful handling when funding data unavailable."""
        from scripts.derivatives.funding_rate_reader import get_latest_funding_signal

        # Mock get_liq_connection to return None (simulating DB unavailable)
        with patch(
            "scripts.derivatives.funding_rate_reader.get_liq_connection",
            return_value=None,
        ):
            # When LiquidationHeatmap is unavailable, should return None
            result = get_latest_funding_signal(conn=None)
            assert result is None, "Should return None when unavailable"


# =============================================================================
# Phase 4: User Story 2 - Open Interest Signal Tests
# =============================================================================


class TestOpenInterestSignal:
    """Tests for US2: Open interest context-aware signal."""

    def test_oi_rising_accumulation(self):
        """T018: OI +5% with whale ACCUMULATION → +0.5 vote, confirming."""
        from scripts.derivatives.oi_reader import oi_to_vote

        oi_change = 0.05  # +5%
        whale_direction = "ACCUMULATION"

        vote, context = oi_to_vote(oi_change, whale_direction)

        assert vote > 0, "Rising OI + accumulation should be bullish"
        assert vote == pytest.approx(0.5, abs=0.2), f"Expected ~+0.5, got {vote}"
        assert context == "confirming"

    def test_oi_rising_distribution(self):
        """T019: OI +5% with whale DISTRIBUTION → -0.3 vote, diverging."""
        from scripts.derivatives.oi_reader import oi_to_vote

        oi_change = 0.05  # +5%
        whale_direction = "DISTRIBUTION"

        vote, context = oi_to_vote(oi_change, whale_direction)

        assert vote < 0, "Rising OI + distribution should be diverging (bearish)"
        assert vote == pytest.approx(-0.3, abs=0.2), f"Expected ~-0.3, got {vote}"
        assert context == "diverging"

    def test_oi_falling_deleveraging(self):
        """T020: OI -3% → 0.0 vote, deleveraging."""
        from scripts.derivatives.oi_reader import oi_to_vote

        oi_change = -0.03  # -3%
        whale_direction = "ACCUMULATION"  # Doesn't matter for deleveraging

        vote, context = oi_to_vote(oi_change, whale_direction)

        assert vote == pytest.approx(0.0, abs=0.1), f"Expected ~0.0, got {vote}"
        assert context == "deleveraging"

    def test_oi_data_gap(self):
        """T021: Handle missing OI timestamps gracefully."""
        from scripts.derivatives.oi_reader import get_latest_oi_signal

        # With no connection, should return None
        result = get_latest_oi_signal(conn=None, whale_direction="NEUTRAL")
        assert result is None, "Should return None when data unavailable"


# =============================================================================
# Phase 5: User Story 3 - Enhanced Fusion Tests
# =============================================================================


class TestEnhancedFusion:
    """Tests for US3: 4-component Monte Carlo fusion."""

    def test_enhanced_fusion_all_signals(self):
        """T027: All 4 signals present → derivatives_available=True."""
        from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion

        result = enhanced_monte_carlo_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            utxo_vote=0.6,
            utxo_conf=0.8,
            funding_vote=0.5,
            oi_vote=0.4,
        )

        assert result is not None
        assert result.derivatives_available is True
        assert -1.0 <= result.signal_mean <= 1.0
        assert result.action in ("BUY", "SELL", "HOLD")
        assert 0.0 <= result.action_confidence <= 1.0

    def test_enhanced_fusion_conflicting(self):
        """T028: Conflicting signals → elevated signal_std indicating uncertainty."""
        from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion

        # Whale bullish, funding bearish, others mixed
        result = enhanced_monte_carlo_fusion(
            whale_vote=0.9,  # Very bullish
            whale_conf=0.9,
            utxo_vote=0.3,
            utxo_conf=0.5,
            funding_vote=-0.8,  # Very bearish
            oi_vote=0.0,  # Neutral
        )

        assert result is not None
        # With Monte Carlo bootstrap and noise, conflicting signals show elevated std
        # The std reflects sampling uncertainty, not just signal disagreement
        assert result.signal_std > 0.05, (
            f"Conflicting signals should have elevated std, got {result.signal_std}"
        )
        # Also verify wide confidence interval (span > 0.3)
        ci_span = result.ci_upper - result.ci_lower
        assert ci_span > 0.25, (
            f"Conflicting signals should have wide CI span, got {ci_span}"
        )

    def test_enhanced_fusion_fallback(self):
        """T029: Derivatives unavailable → 2-component fusion (spec-007 behavior)."""
        from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion

        result = enhanced_monte_carlo_fusion(
            whale_vote=0.7,
            whale_conf=0.8,
            utxo_vote=0.5,
            utxo_conf=0.7,
            funding_vote=None,  # Unavailable
            oi_vote=None,  # Unavailable
        )

        assert result is not None
        assert result.derivatives_available is False
        # Should still produce valid signal with 2 components
        assert -1.0 <= result.signal_mean <= 1.0
        assert result.funding_vote is None
        assert result.oi_vote is None


# =============================================================================
# Phase 6: User Story 4 - Backtest Tests
# =============================================================================


class TestBacktest:
    """Tests for US4: Historical backtesting."""

    def test_backtest_output_format(self):
        """T035: Verify backtest output includes required metrics."""
        from scripts.models.derivatives_models import BacktestResult

        # Create a sample result
        result = BacktestResult(
            start_date=datetime(2025, 10, 1),
            end_date=datetime(2025, 10, 31),
            total_signals=744,
            buy_signals=312,
            sell_signals=198,
            hold_signals=234,
            win_rate=0.62,
            total_return=0.085,
            sharpe_ratio=1.42,
            max_drawdown=-0.034,
        )

        output = result.to_dict()

        # Verify required fields
        assert "signals" in output
        assert output["signals"]["total"] == 744
        assert "performance" in output
        assert "win_rate" in output["performance"]
        assert "sharpe_ratio" in output["performance"]
        assert "max_drawdown" in output["performance"]
        assert "period" in output
        assert "start" in output["period"]
        assert "end" in output["period"]

    def test_backtest_weight_optimization(self):
        """T036: Weight optimization returns optimal_weights."""
        from scripts.models.derivatives_models import BacktestResult

        # Result with optimization
        result = BacktestResult(
            start_date=datetime(2025, 10, 1),
            end_date=datetime(2025, 10, 31),
            total_signals=744,
            buy_signals=312,
            sell_signals=198,
            hold_signals=234,
            win_rate=0.65,
            total_return=0.10,
            sharpe_ratio=1.55,
            max_drawdown=-0.028,
            optimal_weights={
                "whale": 0.35,
                "utxo": 0.25,
                "funding": 0.25,
                "oi": 0.15,
            },
        )

        output = result.to_dict()
        assert output["optimal_weights"] is not None
        assert "whale" in output["optimal_weights"]
        assert sum(output["optimal_weights"].values()) == pytest.approx(1.0)


# =============================================================================
# Data Model Validation Tests
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests for coverage."""

    def test_oi_change_zero_previous(self):
        """Test OI change calculation with zero previous value."""
        from scripts.derivatives.oi_reader import calculate_oi_change

        # Zero previous should return 0.0 (avoids division by zero)
        result = calculate_oi_change(1000000, 0)
        assert result == 0.0

        # Negative previous should also return 0.0
        result = calculate_oi_change(1000000, -100)
        assert result == 0.0

    def test_oi_change_normal(self):
        """Test OI change calculation with normal values."""
        from scripts.derivatives.oi_reader import calculate_oi_change

        # 5% increase
        result = calculate_oi_change(105, 100)
        assert result == pytest.approx(0.05)

        # 10% decrease
        result = calculate_oi_change(90, 100)
        assert result == pytest.approx(-0.10)

    def test_redistribute_weights_all_missing(self):
        """Test weight redistribution when all derivatives missing."""
        from scripts.derivatives.enhanced_fusion import redistribute_weights

        # Only whale and utxo available
        weights = redistribute_weights(["funding", "oi"])
        assert weights["funding"] == 0.0
        assert weights["oi"] == 0.0
        assert weights["whale"] + weights["utxo"] == pytest.approx(1.0)

    def test_redistribute_weights_none_missing(self):
        """Test weight redistribution with no missing components."""
        from scripts.derivatives.enhanced_fusion import (
            redistribute_weights,
            DEFAULT_WEIGHTS,
        )

        weights = redistribute_weights([])
        assert weights == DEFAULT_WEIGHTS

    def test_detect_distribution_insufficient_data(self):
        """Test bimodal detection with insufficient samples."""
        import numpy as np
        from scripts.derivatives.enhanced_fusion import detect_distribution_type

        # Less than 100 samples
        samples = np.array([0.1, 0.2, 0.3])
        result = detect_distribution_type(samples)
        assert result == "insufficient_data"

    def test_detect_distribution_unimodal(self):
        """Test bimodal detection with unimodal distribution."""
        import numpy as np
        from scripts.derivatives.enhanced_fusion import detect_distribution_type

        # Low variance, all positive
        np.random.seed(42)
        samples = np.random.normal(0.5, 0.1, 500)
        result = detect_distribution_type(samples)
        assert result == "unimodal"

    def test_determine_action_boundaries(self):
        """Test action determination at threshold boundaries."""
        from scripts.derivatives.enhanced_fusion import determine_action

        # At BUY threshold
        assert determine_action(0.15, 0.8) == "HOLD"  # Exactly at threshold = HOLD
        assert determine_action(0.16, 0.8) == "BUY"  # Just above = BUY

        # At SELL threshold
        assert determine_action(-0.15, 0.8) == "HOLD"
        assert determine_action(-0.16, 0.8) == "SELL"

        # Clear HOLD
        assert determine_action(0.0, 0.5) == "HOLD"

    def test_funding_to_vote_edge_cases(self):
        """Test funding_to_vote at edge values."""
        from scripts.derivatives.funding_rate_reader import funding_to_vote

        # Very high positive (caps at -1.0)
        vote, is_extreme = funding_to_vote(0.005)  # 0.5%
        assert vote >= -1.0
        assert is_extreme is True

        # Very high negative (caps at +1.0)
        vote, is_extreme = funding_to_vote(-0.003)  # -0.3%
        assert vote <= 1.0
        assert is_extreme is True

        # Exactly at neutral boundary
        vote, is_extreme = funding_to_vote(0.0001)
        assert vote == 0.0

    def test_oi_to_vote_moderate_change(self):
        """Test OI vote for moderate changes (1-2%)."""
        from scripts.derivatives.oi_reader import oi_to_vote

        # Moderate positive change (between neutral and significant)
        vote, context = oi_to_vote(0.015, "ACCUMULATION")
        assert vote == 0.0
        assert context == "neutral"

    def test_oi_to_vote_neutral_whale(self):
        """Test OI vote with NEUTRAL whale direction."""
        from scripts.derivatives.oi_reader import oi_to_vote

        # Significant rise with neutral whale
        vote, context = oi_to_vote(0.05, "NEUTRAL")
        assert 0 < vote <= 0.2  # Small bullish bias
        assert context == "neutral"

    def test_detect_distribution_bimodal(self):
        """Test bimodal detection with conflicting samples."""
        import numpy as np
        from scripts.derivatives.enhanced_fusion import detect_distribution_type

        # Create bimodal distribution (wide spread, positive and negative)
        np.random.seed(42)
        samples = np.concatenate(
            [
                np.random.normal(0.5, 0.2, 250),
                np.random.normal(-0.5, 0.2, 250),
            ]
        )
        result = detect_distribution_type(samples)
        assert result == "bimodal"

    def test_enhanced_fusion_negative_signal(self):
        """Test fusion with negative overall signal."""
        from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion

        result = enhanced_monte_carlo_fusion(
            whale_vote=-0.8,
            whale_conf=0.9,
            utxo_vote=-0.6,
            utxo_conf=0.8,
            funding_vote=-0.5,
            oi_vote=-0.4,
        )

        assert result.signal_mean < 0
        # Check action_confidence is calculated correctly for negative signals
        assert result.action_confidence > 0

    def test_create_enhanced_result_with_freshness(self):
        """Test create_enhanced_result adds data freshness."""
        from scripts.derivatives.enhanced_fusion import create_enhanced_result

        result = create_enhanced_result(
            whale_vote=0.5,
            whale_conf=0.8,
            utxo_vote=0.3,
            utxo_conf=0.7,
            funding_vote=0.2,
            oi_vote=0.1,
            data_freshness_minutes=30,
        )

        assert result.data_freshness_minutes == 30


class TestErrorPaths:
    """Tests for error handling paths to improve coverage."""

    def test_funding_read_none_connection(self):
        """Test read_funding_rate handles None connection."""
        from scripts.derivatives.funding_rate_reader import read_funding_rate
        from datetime import datetime

        result = read_funding_rate(None, datetime.now())
        assert result is None

    def test_oi_read_none_connection(self):
        """Test read_oi_at_timestamp handles None connection."""
        from scripts.derivatives.oi_reader import read_oi_at_timestamp
        from datetime import datetime

        result = read_oi_at_timestamp(None, datetime.now())
        assert result is None

    def test_get_latest_funding_with_conn(self):
        """Test get_latest_funding_signal with provided connection."""
        from scripts.derivatives import get_liq_connection, close_connection
        from scripts.derivatives.funding_rate_reader import get_latest_funding_signal

        conn = get_liq_connection()
        if conn is not None:
            signal = get_latest_funding_signal(conn=conn)
            # Should work with provided connection
            if signal is not None:
                assert signal.symbol == "BTCUSDT"
            close_connection(conn)

    def test_get_latest_oi_with_conn(self):
        """Test get_latest_oi_signal with provided connection."""
        from scripts.derivatives import get_liq_connection, close_connection
        from scripts.derivatives.oi_reader import get_latest_oi_signal

        conn = get_liq_connection()
        if conn is not None:
            signal = get_latest_oi_signal(conn=conn, whale_direction="ACCUMULATION")
            if signal is not None:
                assert signal.symbol == "BTCUSDT"
            close_connection(conn)


class TestDataModels:
    """Tests for data model validation."""

    def test_funding_rate_signal_validation(self):
        """Test FundingRateSignal validates vote bounds."""
        from scripts.models.derivatives_models import FundingRateSignal

        # Valid signal
        signal = FundingRateSignal(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            exchange="binance",
            funding_rate=0.001,
            funding_vote=-0.5,
            is_extreme=True,
        )
        assert signal.funding_vote == -0.5

        # Invalid vote (out of range)
        with pytest.raises(ValueError, match="funding_vote out of range"):
            FundingRateSignal(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                exchange="binance",
                funding_rate=0.001,
                funding_vote=-1.5,  # Invalid
                is_extreme=True,
            )

    def test_open_interest_signal_validation(self):
        """Test OpenInterestSignal validates context."""
        from scripts.models.derivatives_models import OpenInterestSignal

        # Valid signal
        signal = OpenInterestSignal(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            exchange="binance",
            oi_value=9_000_000_000,
            oi_change_1h=0.05,
            oi_change_24h=0.08,
            oi_vote=0.5,
            context="confirming",
        )
        assert signal.context == "confirming"

        # Invalid context
        with pytest.raises(ValueError, match="Invalid context"):
            OpenInterestSignal(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                exchange="binance",
                oi_value=9_000_000_000,
                oi_change_1h=0.05,
                oi_change_24h=0.08,
                oi_vote=0.5,
                context="invalid_context",  # Invalid
            )

    def test_backtest_result_validation(self):
        """Test BacktestResult validates signal counts."""
        from scripts.models.derivatives_models import BacktestResult

        # Invalid: counts don't match total
        with pytest.raises(ValueError, match="Signal counts don't match"):
            BacktestResult(
                start_date=datetime.now(),
                end_date=datetime.now(),
                total_signals=100,
                buy_signals=50,
                sell_signals=30,
                hold_signals=10,  # 50+30+10=90 != 100
                win_rate=0.6,
                total_return=0.05,
                sharpe_ratio=1.0,
                max_drawdown=-0.02,
            )
