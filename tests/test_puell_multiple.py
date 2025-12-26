#!/usr/bin/env python3
"""
Tests for Puell Multiple Module (spec-033, T003)

Basic test coverage for puell_multiple.py functions:
- get_block_subsidy: Test halving boundaries
- calculate_puell_multiple: Test division by zero and normal case
- classify_puell_zone: Test zone boundaries
"""

import pytest
from scripts.metrics.puell_multiple import (
    get_block_subsidy,
    calculate_puell_multiple,
    classify_puell_zone,
    PuellZone,
)


# =============================================================================
# Tests for get_block_subsidy
# =============================================================================


class TestGetBlockSubsidy:
    """Tests for the get_block_subsidy function."""

    def test_halving_boundary_0(self):
        """Test block subsidy at genesis (block 0)."""
        subsidy = get_block_subsidy(0)
        assert subsidy == 50.0, f"Expected 50.0 BTC at genesis, got {subsidy}"

    def test_halving_boundary_first(self):
        """Test block subsidy at first halving boundary (block 210000)."""
        # Last block before halving
        subsidy_before = get_block_subsidy(209_999)
        assert subsidy_before == 50.0, (
            f"Expected 50.0 BTC before halving, got {subsidy_before}"
        )

        # First block after halving
        subsidy_after = get_block_subsidy(210_000)
        assert subsidy_after == 25.0, (
            f"Expected 25.0 BTC after halving, got {subsidy_after}"
        )

    def test_halving_boundary_second(self):
        """Test block subsidy at second halving boundary (block 420000)."""
        # Last block before halving
        subsidy_before = get_block_subsidy(419_999)
        assert subsidy_before == 25.0, (
            f"Expected 25.0 BTC before halving, got {subsidy_before}"
        )

        # First block after halving
        subsidy_after = get_block_subsidy(420_000)
        assert subsidy_after == 12.5, (
            f"Expected 12.5 BTC after halving, got {subsidy_after}"
        )

    def test_halving_boundary_third(self):
        """Test block subsidy at third halving boundary (block 630000)."""
        # Last block before halving
        subsidy_before = get_block_subsidy(629_999)
        assert subsidy_before == 12.5, (
            f"Expected 12.5 BTC before halving, got {subsidy_before}"
        )

        # First block after halving
        subsidy_after = get_block_subsidy(630_000)
        assert subsidy_after == 6.25, (
            f"Expected 6.25 BTC after halving, got {subsidy_after}"
        )

    def test_halving_boundary_fourth(self):
        """Test block subsidy at fourth halving boundary (block 840000)."""
        # Last block before halving
        subsidy_before = get_block_subsidy(839_999)
        assert subsidy_before == 6.25, (
            f"Expected 6.25 BTC before halving, got {subsidy_before}"
        )

        # First block after halving (April 2024)
        subsidy_after = get_block_subsidy(840_000)
        assert subsidy_after == 3.125, (
            f"Expected 3.125 BTC after halving, got {subsidy_after}"
        )

    def test_negative_block_height_raises_error(self):
        """Test that negative block height raises ValueError."""
        with pytest.raises(ValueError, match="block_height must be non-negative"):
            get_block_subsidy(-1)

    def test_returns_float(self):
        """Test that function always returns float."""
        subsidy = get_block_subsidy(100_000)
        assert isinstance(subsidy, float), f"Expected float, got {type(subsidy)}"


# =============================================================================
# Tests for calculate_puell_multiple
# =============================================================================


class TestCalculatePuellMultiple:
    """Tests for the calculate_puell_multiple function."""

    def test_division_by_zero_returns_zero(self):
        """Test that division by zero returns 0.0."""
        result = calculate_puell_multiple(
            daily_revenue_usd=1000.0, ma_365d_revenue_usd=0.0
        )
        assert result == 0.0, f"Expected 0.0 for division by zero, got {result}"

    def test_negative_ma_returns_zero(self):
        """Test that negative MA returns 0.0."""
        result = calculate_puell_multiple(
            daily_revenue_usd=1000.0, ma_365d_revenue_usd=-100.0
        )
        assert result == 0.0, f"Expected 0.0 for negative MA, got {result}"

    def test_negative_daily_revenue_returns_zero(self):
        """Test that negative daily revenue returns 0.0."""
        result = calculate_puell_multiple(
            daily_revenue_usd=-1000.0, ma_365d_revenue_usd=500.0
        )
        assert result == 0.0, f"Expected 0.0 for negative daily revenue, got {result}"

    def test_normal_case_above_average(self):
        """Test normal calculation with daily revenue above average."""
        result = calculate_puell_multiple(
            daily_revenue_usd=2000.0, ma_365d_revenue_usd=1000.0
        )
        assert result == 2.0, f"Expected 2.0, got {result}"

    def test_normal_case_below_average(self):
        """Test normal calculation with daily revenue below average."""
        result = calculate_puell_multiple(
            daily_revenue_usd=500.0, ma_365d_revenue_usd=1000.0
        )
        assert result == 0.5, f"Expected 0.5, got {result}"

    def test_normal_case_equal_to_average(self):
        """Test normal calculation with daily revenue equal to average."""
        result = calculate_puell_multiple(
            daily_revenue_usd=1000.0, ma_365d_revenue_usd=1000.0
        )
        assert result == 1.0, f"Expected 1.0, got {result}"

    def test_returns_float(self):
        """Test that function always returns float."""
        result = calculate_puell_multiple(
            daily_revenue_usd=1500.0, ma_365d_revenue_usd=1000.0
        )
        assert isinstance(result, float), f"Expected float, got {type(result)}"


# =============================================================================
# Tests for classify_puell_zone
# =============================================================================


class TestClassifyPuellZone:
    """Tests for the classify_puell_zone function."""

    def test_capitulation_zone_boundary(self):
        """Test values at capitulation zone boundary (< 0.5)."""
        assert classify_puell_zone(0.0) == PuellZone.CAPITULATION
        assert classify_puell_zone(0.25) == PuellZone.CAPITULATION
        assert classify_puell_zone(0.49) == PuellZone.CAPITULATION

    def test_fair_value_zone_lower_boundary(self):
        """Test fair value zone at lower boundary (>= 0.5)."""
        assert classify_puell_zone(0.5) == PuellZone.FAIR_VALUE
        assert classify_puell_zone(1.0) == PuellZone.FAIR_VALUE
        assert classify_puell_zone(2.0) == PuellZone.FAIR_VALUE

    def test_fair_value_zone_upper_boundary(self):
        """Test fair value zone at upper boundary (<= 3.5)."""
        assert classify_puell_zone(3.0) == PuellZone.FAIR_VALUE
        assert classify_puell_zone(3.5) == PuellZone.FAIR_VALUE

    def test_overheated_zone_boundary(self):
        """Test overheated zone boundary (> 3.5)."""
        assert classify_puell_zone(3.51) == PuellZone.OVERHEATED
        assert classify_puell_zone(4.0) == PuellZone.OVERHEATED
        assert classify_puell_zone(10.0) == PuellZone.OVERHEATED

    def test_exact_boundary_values(self):
        """Test exact boundary transitions."""
        # 0.5 is the start of FAIR_VALUE
        assert classify_puell_zone(0.499999) == PuellZone.CAPITULATION
        assert classify_puell_zone(0.5) == PuellZone.FAIR_VALUE

        # 3.5 is still FAIR_VALUE, 3.50001 is OVERHEATED
        assert classify_puell_zone(3.5) == PuellZone.FAIR_VALUE
        assert classify_puell_zone(3.500001) == PuellZone.OVERHEATED

    def test_returns_puell_zone_enum(self):
        """Test that function returns PuellZone enum."""
        result = classify_puell_zone(1.5)
        assert isinstance(result, PuellZone), (
            f"Expected PuellZone enum, got {type(result)}"
        )

    def test_negative_values(self):
        """Test handling of negative values (edge case)."""
        # Negative values should be classified as CAPITULATION
        assert classify_puell_zone(-1.0) == PuellZone.CAPITULATION
