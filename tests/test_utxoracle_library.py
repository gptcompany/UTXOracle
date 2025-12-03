"""
Test suite for UTXOracle_library.py

Tests for refactored UTXOracle algorithm (Steps 5-11)
TDD guard disabled for this refactor (extracting existing working code).

Spec: 003-mempool-integration-refactor
Phase: 2 - Algorithm Refactor
Tasks: T013-T018 (all tests)
"""

import pytest
from UTXOracle_library import UTXOracleCalculator


class TestHistogramBins:
    """T013: Test histogram bins generation (Step 5)"""

    def test_histogram_bins_count_is_2400(self):
        """Histogram should have 2400 bins (200 per decade × 12 decades)"""
        calc = UTXOracleCalculator()
        bins = calc._build_histogram_bins()

        # 200 bins per 10x range, from 10^-6 to 10^6 = 12 decades = 2400 bins
        # Plus bin 0 (zero sats) = 2401 total
        assert len(bins) == 2401, f"Expected 2401 bins, got {len(bins)}"

    def test_histogram_bins_logarithmic_spacing(self):
        """Bins should be logarithmically spaced"""
        calc = UTXOracleCalculator()
        bins = calc._build_histogram_bins()

        # Check first few bins after zero
        assert bins[0] == 0.0, "First bin should be 0.0"
        assert bins[1] == pytest.approx(10**-6, rel=1e-9), (
            "Second bin should be ~1e-6 BTC"
        )

        # Check bin at exponent boundary (after 200 bins, should be 10x larger)
        assert bins[201] == pytest.approx(10**-5, rel=1e-6), (
            "Bin 201 should be ~1e-5 BTC"
        )


class TestBinIndexCalculation:
    """T014: Test bin index calculation for transaction amounts"""

    def test_get_bin_index_for_various_amounts(self):
        """Should correctly map BTC amounts to histogram bin indices"""
        calc = UTXOracleCalculator()

        # Test zero amount
        assert calc._get_bin_index(0.0) == 0, "Zero BTC should map to bin 0"

        # Test small amount (1e-6 BTC = 100 sats)
        bin_idx = calc._get_bin_index(1e-6)
        assert 0 < bin_idx < 201, f"1e-6 BTC should map to bin 1-200, got {bin_idx}"

        # Test medium amount (0.01 BTC)
        bin_idx = calc._get_bin_index(0.01)
        assert 800 < bin_idx < 1001, (
            f"0.01 BTC should map to bin ~800-1000, got {bin_idx}"
        )

        # Test large amount (1.0 BTC)
        bin_idx = calc._get_bin_index(1.0)
        assert 1200 < bin_idx < 1401, (
            f"1.0 BTC should map to bin ~1200-1400, got {bin_idx}"
        )

    def test_get_bin_index_out_of_range(self):
        """Amounts outside histogram range should return None or boundary index"""
        calc = UTXOracleCalculator()

        # Amount smaller than minimum
        result = calc._get_bin_index(1e-10)
        assert result is None or result == 0, (
            "Very small amounts should return None or 0"
        )

        # Amount larger than maximum
        result = calc._get_bin_index(1e10)
        assert result is None or result == 2400, (
            "Very large amounts should return None or max"
        )


class TestRoundAmountFiltering:
    """T015: Test removal of round Bitcoin amounts (Step 7)"""

    def test_remove_round_amounts(self):
        """Should filter out round BTC amounts (1.0, 5.0, 10.0, etc.)"""
        calc = UTXOracleCalculator()

        # Create histogram with round and non-round amounts
        histogram = {
            0.5: 10,  # Keep - not round
            1.0: 100,  # Remove - round
            1.23456: 50,  # Keep - not round
            5.0: 200,  # Remove - round
            10.0: 150,  # Remove - round
            12.34567: 30,  # Keep - not round
        }

        filtered = calc._remove_round_amounts(histogram)

        # Check round amounts removed
        assert 1.0 not in filtered, "1.0 BTC should be removed"
        assert 5.0 not in filtered, "5.0 BTC should be removed"
        assert 10.0 not in filtered, "10.0 BTC should be removed"

        # Check non-round amounts kept
        assert 0.5 in filtered, "0.5 BTC should be kept"
        assert 1.23456 in filtered, "1.23456 BTC should be kept"
        assert 12.34567 in filtered, "12.34567 BTC should be kept"

        # Check counts preserved
        assert filtered[0.5] == 10
        assert filtered[1.23456] == 50


class TestStencilConstruction:
    """T016: Test price-finding stencil construction (Step 8)"""

    def test_build_stencils(self):
        """Should build smooth and spike detection stencils"""
        calc = UTXOracleCalculator()

        smooth_stencil = calc._build_smooth_stencil()
        spike_stencil = calc._build_spike_stencil()

        # Smooth stencil should be wider (more bins)
        assert len(smooth_stencil) > 0, "Smooth stencil should have bins"
        assert len(smooth_stencil) > len(spike_stencil), (
            "Smooth stencil should be wider than spike"
        )

        # Stencils should have weights that sum to reasonable values
        assert sum(smooth_stencil.values()) > 0, (
            "Smooth stencil weights should be positive"
        )
        assert sum(spike_stencil.values()) > 0, (
            "Spike stencil weights should be positive"
        )


class TestPriceEstimation:
    """T017: Test price estimation from histogram (Steps 9-11)"""

    def test_estimate_price_from_histogram(self):
        """Should estimate price from histogram data"""
        calc = UTXOracleCalculator()

        # Create mock histogram with peak around bin 1200 (0.001 BTC range)
        # If price is $60,000, then $60 = 0.001 BTC is a common round amount
        histogram = {}
        for i in range(2401):
            if 1150 < i < 1250:
                histogram[i] = 100  # High count near peak
            elif 1100 < i < 1300:
                histogram[i] = 50  # Medium count nearby
            else:
                histogram[i] = 1  # Low count elsewhere

        result = calc._estimate_price(histogram)

        # Should return dict with price_usd, confidence, etc.
        assert "price_usd" in result, "Result should contain price_usd"
        assert "confidence" in result, "Result should contain confidence"

        # Price should be reasonable (between $10k and $500k)
        assert 10000 < result["price_usd"] < 500000, (
            f"Price ${result['price_usd']} out of range"
        )

        # Confidence should be between 0 and 1
        assert 0 <= result["confidence"] <= 1, (
            f"Confidence {result['confidence']} out of range"
        )


class TestFullCalculation:
    """T018: Test full price calculation pipeline"""

    def test_calculate_price_for_transactions(self):
        """Should calculate price from transaction list"""
        calc = UTXOracleCalculator()

        # Mock transaction data (simplified format)
        transactions = [
            {"vout": [{"value": 0.001}, {"value": 0.05}], "vin": [{}]},
            {"vout": [{"value": 0.0009}], "vin": [{}]},
            {"vout": [{"value": 0.0011}], "vin": [{}]},
        ]

        result = calc.calculate_price_for_transactions(transactions)

        # Should return complete result dict
        assert isinstance(result, dict), "Result should be a dictionary"
        assert "price_usd" in result, "Result should contain price_usd"
        assert "confidence" in result, "Result should contain confidence"
        assert "tx_count" in result, "Result should contain tx_count"

    def test_calculate_price_empty_transactions(self):
        """Should handle empty transaction list gracefully"""
        calc = UTXOracleCalculator()

        result = calc.calculate_price_for_transactions([])

        # Should return result with None/zero price
        assert result["price_usd"] is None or result["price_usd"] == 0
        assert result["tx_count"] == 0
