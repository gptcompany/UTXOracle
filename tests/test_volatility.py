"""Tests for Volatility calculation."""

import math
import pytest
from datetime import date

from scripts.metrics.volatility import calculate_volatility


class TestCalculateVolatility:
    """Tests for calculate_volatility function."""

    def test_basic_calculation(self):
        """Test basic volatility calculation."""
        # Prices with some variation
        prices = [100, 102, 99, 103, 101, 104, 100, 105]
        result = calculate_volatility(prices)

        assert result.daily_volatility > 0
        assert result.annualized_pct > 0
        assert result.window_days == len(prices)

    def test_constant_prices_zero_volatility(self):
        """Test constant prices produce near-zero volatility."""
        prices = [100, 100, 100, 100, 100]
        result = calculate_volatility(prices)

        assert result.daily_volatility == pytest.approx(0.0, abs=1e-10)
        assert result.annualized_pct == pytest.approx(0.0, abs=1e-10)

    def test_high_volatility_regime(self):
        """Test high volatility is correctly classified."""
        # Large daily swings (~10%)
        prices = [100, 110, 99, 112, 98, 115, 95]
        result = calculate_volatility(prices)

        assert result.regime in ["high", "extreme"]
        assert result.annualized_pct > 60

    def test_low_volatility_regime(self):
        """Test low volatility is correctly classified."""
        # Small daily changes (~0.1%)
        prices = [100.0, 100.1, 100.0, 100.1, 100.2, 100.1, 100.0]
        result = calculate_volatility(prices)

        assert result.regime == "low"
        assert result.annualized_pct < 30

    def test_single_price_raises(self):
        """Test single price raises ValueError."""
        with pytest.raises(ValueError, match="At least 2 prices required"):
            calculate_volatility([100])

    def test_empty_prices_raises(self):
        """Test empty prices raises ValueError."""
        with pytest.raises(ValueError, match="At least 2 prices required"):
            calculate_volatility([])

    def test_window_days_limits_data(self):
        """Test window_days parameter limits calculation."""
        prices = [100, 102, 99, 103, 101, 104, 100, 105, 102, 106]
        result = calculate_volatility(prices, window_days=5)

        assert result.window_days == 5

    def test_annualization_formula(self):
        """Test annualization uses sqrt(365) multiplier."""
        # Create returns with known daily volatility
        # If daily vol is 1%, annualized should be ~19.1% (sqrt(365) ≈ 19.1)
        prices = [100, 101, 100, 101, 100]  # ~1% daily moves
        result = calculate_volatility(prices)

        # Annualized should be roughly daily * sqrt(365)
        expected_annualized = result.daily_volatility * math.sqrt(365)
        assert result.annualized_pct == pytest.approx(
            expected_annualized * 100, rel=0.01
        )

    def test_custom_date(self):
        """Test custom date is preserved."""
        target = date(2025, 1, 1)
        result = calculate_volatility([100, 105, 102], target_date=target)

        assert result.date == target

    def test_extreme_regime_flag(self):
        """Test is_extreme property works correctly."""
        # Very high volatility prices
        prices = [100, 150, 80, 160, 70]
        result = calculate_volatility(prices)

        if result.annualized_pct > 100:
            assert result.is_extreme is True
            assert result.regime == "extreme"
