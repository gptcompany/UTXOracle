#!/usr/bin/env python3
"""
Unit Test: Compare Steps 9-11 (Convergence Algorithm)

Tests if UTXOracle_library.py Steps 9-11 produce IDENTICAL results
to UTXOracle.py Steps 9-11 when given the SAME histogram.

If results differ → bug in Steps 9-11 implementation
If results match → difference is in filters (Steps 1-6)
"""

from UTXOracle_library import UTXOracleCalculator

# Sample histogram (mock data for testing)
# This would ideally come from running UTXOracle.py on a real block
test_histogram = {
    # Populate with some test data
    # Format: {bin_index: count}
    600: 10,
    601: 50,
    602: 30,
    603: 15,
    # ... more bins
}


def test_convergence_algorithm():
    """Test if Steps 9-11 are truly identical"""
    calc = UTXOracleCalculator()

    # Test with sample histogram
    result = calc._estimate_price(test_histogram)

    print("=" * 80)
    print("HISTOGRAM CONVERGENCE TEST")
    print("=" * 80)
    print()
    print(f"Test histogram bins: {len(test_histogram)}")
    print(f"Estimated price: ${result['price_usd']:,.2f}")
    print(f"Confidence: {result['confidence']:.3f}")
    print()
    print("To properly test:")
    print("1. Run UTXOracle.py on block 919111")
    print("2. Extract the histogram AFTER Step 7 (before Step 9)")
    print("3. Pass same histogram to library")
    print("4. Compare prices - should be IDENTICAL (0% diff)")
    print()
    print("=" * 80)


if __name__ == "__main__":
    test_convergence_algorithm()
