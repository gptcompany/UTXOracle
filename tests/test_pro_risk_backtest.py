"""
Tests for PRO Risk backtest integration (spec-033, T037-T038).

Tests:
- Signal generation from price data
- Validation pipeline integration
- Cycle marker analysis
"""

from datetime import date, timedelta

from scripts.backtest.run_pro_risk_validation import (
    generate_pro_risk_signals,
    analyze_cycle_markers,
    run_pro_risk_validation,
)


class TestProRiskSignalGeneration:
    """Tests for PRO Risk signal generation."""

    def test_generate_signals_returns_correct_length(self):
        """Signals list should match prices length."""
        prices = [100.0, 105.0, 103.0, 108.0, 110.0] * 20  # 100 prices
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]

        signals = generate_pro_risk_signals(prices, dates, window=30, seed=42)

        assert len(signals) == len(prices)

    def test_generate_signals_in_valid_range(self):
        """All signals should be in [0, 1] range."""
        prices = [100.0, 105.0, 103.0, 108.0, 110.0] * 20
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]

        signals = generate_pro_risk_signals(prices, dates, window=30, seed=42)

        for signal in signals:
            assert 0.0 <= signal <= 1.0, f"Signal {signal} out of range"

    def test_generate_signals_deterministic(self):
        """Same inputs and seed should produce same signals."""
        prices = [100.0, 105.0, 103.0, 108.0, 110.0] * 20
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]

        signals1 = generate_pro_risk_signals(prices, dates, window=30, seed=42)
        signals2 = generate_pro_risk_signals(prices, dates, window=30, seed=42)

        assert signals1 == signals2

    def test_generate_signals_window_smaller_than_data(self):
        """Should handle case where window is smaller than data."""
        prices = [100.0, 105.0, 103.0, 108.0, 110.0]
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]

        signals = generate_pro_risk_signals(prices, dates, window=10, seed=42)

        # First few signals should be neutral (0.5) due to insufficient window
        assert signals[0] == 0.5

    def test_generate_signals_reacts_to_price_changes(self):
        """Signals should change when prices change significantly."""
        # Create trending price series
        up_trend = [100.0 + i * 10 for i in range(50)]  # Strong uptrend
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(50)]

        signals = generate_pro_risk_signals(up_trend, dates, window=30, seed=42)

        # Later signals should be higher (greed) due to uptrend
        # Skip first 30 (window size)
        later_signals = signals[35:]
        assert any(s > 0.6 for s in later_signals), "Should show greed in uptrend"


class TestCycleMarkerAnalysis:
    """Tests for cycle marker analysis."""

    def test_analyze_cycle_markers_empty_data(self):
        """Should handle empty data gracefully."""
        signals = []
        dates = []
        prices = []

        result = analyze_cycle_markers(signals, dates, prices)

        # Should return results dict but no matches found
        assert isinstance(result, dict)

    def test_analyze_cycle_markers_2017_top(self):
        """Should analyze 2017 cycle top if data available."""
        # Create data around 2017 top
        target_date = date(2017, 12, 17)
        dates = [target_date + timedelta(days=i - 5) for i in range(10)]
        prices = [19000.0 + i * 100 for i in range(10)]
        signals = [0.85] * 10  # High signals (should be greed)

        result = analyze_cycle_markers(signals, dates, prices)

        if "2017_top" in result:
            assert result["2017_top"]["expected_zone"] == "extreme_greed"
            assert result["2017_top"]["signal_value"] >= 0.8

    def test_analyze_cycle_markers_2022_bottom(self):
        """Should analyze 2022 cycle bottom if data available."""
        # Create data around 2022 bottom
        target_date = date(2022, 11, 21)
        dates = [target_date + timedelta(days=i - 5) for i in range(10)]
        prices = [15500.0 + i * 100 for i in range(10)]
        signals = [0.15] * 10  # Low signals (should be fear)

        result = analyze_cycle_markers(signals, dates, prices)

        if "2022_bottom" in result:
            assert result["2022_bottom"]["expected_zone"] == "extreme_fear"
            assert result["2022_bottom"]["signal_value"] <= 0.2

    def test_analyze_cycle_markers_outside_tolerance(self):
        """Should not match dates outside 7-day tolerance."""
        # Create data far from any cycle marker
        dates = [date(2020, 6, 1) + timedelta(days=i) for i in range(10)]
        prices = [10000.0] * 10
        signals = [0.5] * 10

        result = analyze_cycle_markers(signals, dates, prices)

        # No markers should be matched
        assert len(result) == 0 or all(
            data["days_offset"] > 7 for data in result.values()
        )


class TestProRiskValidation:
    """Tests for full PRO Risk validation pipeline."""

    def test_run_pro_risk_validation_insufficient_data(self):
        """Should handle insufficient data gracefully."""
        # This will fail to load enough data but should not crash
        result = run_pro_risk_validation(
            min_days=9999999,  # Impossibly high requirement
            random_trials=10,  # Small for speed
            output_dir="reports/validation/test",
        )

        # Should return empty dict or handle gracefully
        assert isinstance(result, dict)

    def test_run_pro_risk_validation_minimal_data(self):
        """Should run with minimal data for testing."""
        # Use small requirements for fast test
        result = run_pro_risk_validation(
            min_days=20,
            cv_folds=2,
            random_trials=10,
            seed=42,
            output_dir="reports/validation/test",
        )

        # If data available, should return results
        if result:
            assert "result" in result or "prices" in result


class TestProRiskBacktestIntegration:
    """Integration tests for PRO Risk in backtest system."""

    def test_signal_generation_integrates_with_validator(self):
        """Generated signals should be compatible with MetricValidator."""
        from scripts.backtest.metric_validator import MetricValidator

        # Generate test data
        prices = [100.0 + i * 5 for i in range(200)]
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]

        signals = generate_pro_risk_signals(prices, dates, window=30, seed=42)

        # Should be able to create validator and run
        validator = MetricValidator(
            min_days=100,
            cv_folds=2,
            random_trials=10,
            seed=42,
        )

        # This should not raise
        result = validator.validate(
            metric_name="pro_risk",
            signals=signals,
            prices=prices,
            start_date=dates[0],
            end_date=dates[-1],
        )

        assert result.metric_name == "pro_risk"
        assert result.total_signals > 0

    def test_pro_risk_in_comparative_validation(self):
        """PRO Risk should work in comparative validation."""
        from scripts.backtest.metric_validator import MetricValidator, compare_metrics

        # Generate test data
        prices = [100.0 + i * 5 for i in range(200)]
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]

        pro_risk_signals = generate_pro_risk_signals(prices, dates, seed=42)

        # Compare with itself (simple test)
        validator = MetricValidator(
            min_days=100,
            cv_folds=2,
            random_trials=10,
            seed=42,
        )

        metrics_data = {
            "pro_risk": (pro_risk_signals, prices),
        }

        report = compare_metrics(
            validator=validator,
            metrics=metrics_data,
            start_date=dates[0],
            end_date=dates[-1],
        )

        assert "pro_risk" in report.metrics_tested
        assert "pro_risk" in report.results
