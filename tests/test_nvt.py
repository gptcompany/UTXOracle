"""Tests for NVT ratio calculation."""

import pytest
from datetime import date

from scripts.metrics.nvt import calculate_nvt


class TestCalculateNVT:
    """Tests for calculate_nvt function."""

    def test_basic_calculation(self):
        """Test basic NVT calculation."""
        result = calculate_nvt(
            market_cap_usd=1_000_000_000_000,  # $1T
            tx_volume_usd=20_000_000_000,  # $20B
        )
        assert result.nvt_ratio == 50.0
        assert result.signal == "fair"

    def test_undervalued_signal(self):
        """Test NVT < 30 returns undervalued signal."""
        result = calculate_nvt(
            market_cap_usd=100_000_000_000,  # $100B
            tx_volume_usd=10_000_000_000,  # $10B
        )
        assert result.nvt_ratio == 10.0
        assert result.signal == "undervalued"
        assert result.is_undervalued is True

    def test_overvalued_signal(self):
        """Test NVT > 90 returns overvalued signal."""
        result = calculate_nvt(
            market_cap_usd=1_000_000_000_000,  # $1T
            tx_volume_usd=5_000_000_000,  # $5B
        )
        assert result.nvt_ratio == 200.0
        assert result.signal == "overvalued"
        assert result.is_overvalued is True

    def test_zero_volume_raises(self):
        """Test zero TX volume raises ValueError."""
        with pytest.raises(ValueError, match="tx_volume_usd must be positive"):
            calculate_nvt(market_cap_usd=1_000_000, tx_volume_usd=0)

    def test_negative_volume_raises(self):
        """Test negative TX volume raises ValueError."""
        with pytest.raises(ValueError, match="tx_volume_usd must be positive"):
            calculate_nvt(market_cap_usd=1_000_000, tx_volume_usd=-100)

    def test_negative_market_cap_raises(self):
        """Test negative market cap raises ValueError."""
        with pytest.raises(ValueError, match="market_cap_usd must be non-negative"):
            calculate_nvt(market_cap_usd=-1_000_000, tx_volume_usd=100)

    def test_result_contains_inputs(self):
        """Test result contains input values."""
        result = calculate_nvt(
            market_cap_usd=500_000_000_000,
            tx_volume_usd=10_000_000_000,
        )
        assert result.market_cap_usd == 500_000_000_000
        assert result.tx_volume_usd == 10_000_000_000

    def test_custom_date(self):
        """Test custom date is preserved."""
        target = date(2025, 1, 1)
        result = calculate_nvt(
            market_cap_usd=1_000_000_000,
            tx_volume_usd=100_000_000,
            target_date=target,
        )
        assert result.date == target
