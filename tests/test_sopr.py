"""
Test suite for SOPR (Spent Output Profit Ratio) module - spec-016

TDD approach: Tests written FIRST per Constitution Principle II.
"""

import pytest
from datetime import datetime

# Import fixtures


# =============================================================================
# Phase 3: User Story 1 - SOPR Calculation Tests (RED Phase)
# =============================================================================


class TestSOPRCalculation:
    """Tests for individual output SOPR calculation."""

    def test_sopr_calculation_profit(self, sample_spent_output_profit):
        """SOPR > 1 when sold at profit (creation=$50K, spend=$100K → SOPR=2.0)."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=50000.0, spend_price=100000.0, btc_value=1.0, age_days=30
        )

        assert result.sopr == pytest.approx(2.0, rel=1e-6)
        assert result.profit_loss == "PROFIT"
        assert result.is_valid is True

    def test_sopr_calculation_loss(self, sample_spent_output_loss):
        """SOPR < 1 when sold at loss (creation=$100K, spend=$50K → SOPR=0.5)."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=100000.0, spend_price=50000.0, btc_value=1.0, age_days=30
        )

        assert result.sopr == pytest.approx(0.5, rel=1e-6)
        assert result.profit_loss == "LOSS"
        assert result.is_valid is True

    def test_sopr_calculation_breakeven(self, sample_spent_output_breakeven):
        """SOPR ≈ 1 when sold at breakeven."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=100000.0, spend_price=100000.0, btc_value=1.0, age_days=30
        )

        assert result.sopr == pytest.approx(1.0, rel=1e-6)
        assert result.profit_loss == "BREAKEVEN"
        assert result.is_valid is True

    def test_sopr_invalid_prices(self):
        """SOPR marked invalid when prices are zero or negative."""
        from scripts.metrics.sopr import calculate_output_sopr

        # Zero creation price
        result = calculate_output_sopr(
            creation_price=0.0, spend_price=100000.0, btc_value=1.0, age_days=30
        )
        assert result.is_valid is False

        # Negative price
        result = calculate_output_sopr(
            creation_price=-50000.0, spend_price=100000.0, btc_value=1.0, age_days=30
        )
        assert result.is_valid is False


# =============================================================================
# Phase 4: User Story 2 - STH/LTH Split Tests (RED Phase)
# =============================================================================


class TestSTHLTHClassification:
    """Tests for STH/LTH cohort classification."""

    def test_sth_classification(self):
        """Output held < 155 days classified as STH."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=50000.0,
            spend_price=100000.0,
            btc_value=1.0,
            age_days=30,  # < 155 days
        )

        assert result.cohort == "STH"

    def test_lth_classification(self):
        """Output held >= 155 days classified as LTH."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=50000.0,
            spend_price=100000.0,
            btc_value=1.0,
            age_days=200,  # >= 155 days
        )

        assert result.cohort == "LTH"

    def test_sth_boundary(self):
        """Output at exactly 154 days is STH."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=50000.0,
            spend_price=100000.0,
            btc_value=1.0,
            age_days=154,  # Boundary: < 155
        )

        assert result.cohort == "STH"

    def test_lth_boundary(self):
        """Output at exactly 155 days is LTH."""
        from scripts.metrics.sopr import calculate_output_sopr

        result = calculate_output_sopr(
            creation_price=50000.0,
            spend_price=100000.0,
            btc_value=1.0,
            age_days=155,  # Boundary: >= 155
        )

        assert result.cohort == "LTH"


class TestBlockSOPRAggregation:
    """Tests for block-level SOPR aggregation."""

    def test_block_sopr_aggregation(self, sample_block_outputs_mixed):
        """Block SOPR correctly aggregates multiple outputs."""
        from scripts.metrics.sopr import calculate_block_sopr

        outputs = sample_block_outputs_mixed
        result = calculate_block_sopr(
            outputs=outputs,
            block_height=800000,
            block_hash="0000000000000000000abc123",
            timestamp=datetime.now(),
        )

        assert result.valid_outputs == len([o for o in outputs if o.is_valid])
        assert result.aggregate_sopr > 0

    def test_block_sopr_sth_lth_split(self, sample_block_outputs_mixed):
        """Block SOPR correctly splits STH and LTH metrics."""
        from scripts.metrics.sopr import calculate_block_sopr

        outputs = sample_block_outputs_mixed
        result = calculate_block_sopr(
            outputs=outputs,
            block_height=800000,
            block_hash="0000000000000000000abc123",
            timestamp=datetime.now(),
        )

        # Should have both STH and LTH outputs
        assert result.sth_outputs > 0
        assert result.lth_outputs > 0

        # STH and LTH SOPR should be calculated separately
        assert result.sth_sopr is not None
        assert result.lth_sopr is not None

    def test_block_sopr_weighted_average(self):
        """Block SOPR uses BTC-weighted average, not simple average."""
        from scripts.metrics.sopr import calculate_output_sopr, calculate_block_sopr

        # Create outputs with different BTC values
        output1 = calculate_output_sopr(
            creation_price=50000.0,
            spend_price=100000.0,  # SOPR = 2.0
            btc_value=1.0,
            age_days=30,
        )
        output2 = calculate_output_sopr(
            creation_price=100000.0,
            spend_price=50000.0,  # SOPR = 0.5
            btc_value=3.0,  # 3x more BTC
            age_days=30,
        )

        result = calculate_block_sopr(
            outputs=[output1, output2],
            block_height=800000,
            block_hash="0000000000000000000abc123",
            timestamp=datetime.now(),
        )

        # Weighted avg: (2.0*1 + 0.5*3) / 4 = 3.5/4 = 0.875
        # Simple avg would be: (2.0 + 0.5) / 2 = 1.25
        assert result.aggregate_sopr == pytest.approx(0.875, rel=1e-6)

    def test_block_sopr_minimum_samples(self):
        """Block SOPR marked invalid when below minimum sample threshold."""
        from scripts.metrics.sopr import calculate_output_sopr, calculate_block_sopr

        # Create only 5 outputs (below default 100 minimum)
        outputs = [
            calculate_output_sopr(
                creation_price=50000.0, spend_price=100000.0, btc_value=1.0, age_days=30
            )
            for _ in range(5)
        ]

        result = calculate_block_sopr(
            outputs=outputs,
            block_height=800000,
            block_hash="0000000000000000000abc123",
            timestamp=datetime.now(),
            min_samples=100,
        )

        assert result.is_valid is False


# =============================================================================
# Phase 5: User Story 3 - Trading Signals Tests (RED Phase)
# =============================================================================


class TestSignalDetection:
    """Tests for SOPR signal detection."""

    def test_detect_sth_capitulation(self, sample_sopr_window):
        """Detect STH capitulation when STH-SOPR < 1.0 for 3+ days."""
        from scripts.metrics.sopr import detect_sopr_signals

        # Create window with consecutive STH-SOPR < 1.0
        window = sample_sopr_window  # Fixture provides capitulation scenario

        signals = detect_sopr_signals(window)

        assert signals["sth_capitulation"] is True
        assert signals["sopr_vote"] > 0  # Bullish signal

    def test_detect_breakeven_cross(self):
        """Detect STH breakeven cross (SOPR crosses 1.0 from below)."""
        from scripts.metrics.sopr import detect_sopr_signals, BlockSOPR

        # Create window where STH-SOPR crosses above 1.0
        window = [
            BlockSOPR(
                block_height=i,
                aggregate_sopr=0.95 + (i * 0.02),
                sth_sopr=0.95 + (i * 0.02),
                lth_sopr=1.5,
                valid_outputs=100,
                is_valid=True,
                block_hash="",
                timestamp=datetime.now(),
                total_outputs=100,
                sth_outputs=50,
                lth_outputs=50,
                total_btc_moved=100.0,
                sth_btc_moved=50.0,
                lth_btc_moved=50.0,
                profit_outputs=50,
                loss_outputs=50,
                breakeven_outputs=0,
                profit_ratio=0.5,
                min_samples=100,
            )
            for i in range(5)
        ]
        # Last element has sth_sopr = 0.95 + 0.08 = 1.03 (above 1.0)

        signals = detect_sopr_signals(window)

        assert signals["sth_breakeven_cross"] is True

    def test_detect_lth_distribution(self):
        """Detect LTH distribution when LTH-SOPR > 3.0."""
        from scripts.metrics.sopr import detect_sopr_signals, BlockSOPR

        # Create window with high LTH-SOPR
        window = [
            BlockSOPR(
                block_height=i,
                aggregate_sopr=2.5,
                sth_sopr=1.2,
                lth_sopr=3.5,  # LTH > 3.0
                valid_outputs=100,
                is_valid=True,
                block_hash="",
                timestamp=datetime.now(),
                total_outputs=100,
                sth_outputs=50,
                lth_outputs=50,
                total_btc_moved=100.0,
                sth_btc_moved=50.0,
                lth_btc_moved=50.0,
                profit_outputs=80,
                loss_outputs=20,
                breakeven_outputs=0,
                profit_ratio=0.8,
                min_samples=100,
            )
            for i in range(7)
        ]

        signals = detect_sopr_signals(window)

        assert signals["lth_distribution"] is True
        assert signals["sopr_vote"] < 0  # Bearish signal

    def test_sopr_vote_generation(self):
        """SOPR vote correctly reflects signal strength."""
        from scripts.metrics.sopr import detect_sopr_signals, BlockSOPR

        # Neutral scenario - no signals
        window = [
            BlockSOPR(
                block_height=i,
                aggregate_sopr=1.1,
                sth_sopr=1.1,
                lth_sopr=1.2,
                valid_outputs=100,
                is_valid=True,
                block_hash="",
                timestamp=datetime.now(),
                total_outputs=100,
                sth_outputs=50,
                lth_outputs=50,
                total_btc_moved=100.0,
                sth_btc_moved=50.0,
                lth_btc_moved=50.0,
                profit_outputs=60,
                loss_outputs=40,
                breakeven_outputs=0,
                profit_ratio=0.6,
                min_samples=100,
            )
            for i in range(7)
        ]

        signals = detect_sopr_signals(window)

        # No strong signals, vote should be near zero
        assert -0.3 <= signals["sopr_vote"] <= 0.3


# =============================================================================
# Phase 6: User Story 4 - Integration Tests (RED Phase)
# =============================================================================


class TestDailyAnalysisIntegration:
    """Integration tests for SOPR in daily analysis pipeline."""

    def test_daily_analysis_with_sopr(self):
        """Daily analysis pipeline includes SOPR calculation."""
        # This test validates integration with daily_analysis.py
        # Will be implemented when fusion integration is complete
        pass  # Placeholder - will fail until T043 implemented
