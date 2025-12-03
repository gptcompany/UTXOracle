#!/usr/bin/env python3
"""
Test convergence algorithm: Library vs Reference implementation.

This test creates synthetic transactions and verifies that UTXOracle_library.py
produces the same result as UTXOracle.py reference implementation.
"""

import math
from typing import Dict, List


def build_reference_stencils():
    """Build stencils exactly as reference (UTXOracle.py lines 998-1044)."""
    # Smooth stencil
    num_elements = 803
    mean = 411
    std_dev = 201

    smooth_stencil = []
    for x in range(num_elements):
        exp_part = -((x - mean) ** 2) / (2 * (std_dev**2))
        smooth_stencil.append((0.00150 * 2.718281828459045**exp_part) + (0.0000005 * x))

    # Spike stencil
    spike_stencil = [0.0] * 803
    spike_stencil[40] = 0.001300198324984352  # $1
    spike_stencil[141] = 0.001676746949820743  # $5
    spike_stencil[201] = 0.003468805546942046  # $10
    spike_stencil[202] = 0.001991977522512513
    spike_stencil[236] = 0.001905066647961839  # $15
    spike_stencil[261] = 0.003341772718156079  # $20
    spike_stencil[262] = 0.002588902624584287
    spike_stencil[296] = 0.002577893841190244  # $30
    spike_stencil[297] = 0.002733728814200412
    spike_stencil[340] = 0.003076117748975647  # $50
    spike_stencil[341] = 0.005613067550103145
    spike_stencil[342] = 0.003088253178535568
    spike_stencil[400] = 0.002918457489366139  # $100
    spike_stencil[401] = 0.006174500465286022
    spike_stencil[402] = 0.004417068070043504
    spike_stencil[403] = 0.002628663628020371
    spike_stencil[436] = 0.002858828161543839  # $150
    spike_stencil[461] = 0.004097463611984264  # $200
    spike_stencil[462] = 0.003345917406120509
    spike_stencil[496] = 0.002521467726855856  # $300
    spike_stencil[497] = 0.002784125730361008
    spike_stencil[541] = 0.003792850444811335  # $500
    spike_stencil[601] = 0.003688240815848247  # $1000
    spike_stencil[602] = 0.002392400117402263
    spike_stencil[636] = 0.001280993059008106  # $1500
    spike_stencil[661] = 0.001654665137536031  # $2000
    spike_stencil[662] = 0.001395501347054946
    spike_stencil[741] = 0.001154279140906312  # $5000
    spike_stencil[801] = 0.000832244504868709  # $10000

    return smooth_stencil, spike_stencil


def reference_convergence(histogram_array: List[int]) -> float:
    """
    Reference convergence algorithm (EXACT copy from UTXOracle.py lines 1070-1152).

    Args:
        histogram_array: List of transaction counts per bin (1201 bins)

    Returns:
        Estimated BTC/USD price
    """
    smooth_stencil, spike_stencil = build_reference_stencils()

    # Parameters
    center_p001 = 601
    min_slide = -141
    max_slide = 201

    best_slide = 0
    best_slide_score = 0
    total_score = 0

    left_p001 = center_p001 - int((len(spike_stencil) + 1) / 2)
    right_p001 = center_p001 + int((len(spike_stencil) + 1) / 2)

    # Slide the stencil and calculate slide score
    for slide in range(min_slide, max_slide):
        shifted_curve = histogram_array[left_p001 + slide : right_p001 + slide]

        # Score smooth slide
        slide_score_smooth = 0.0
        for n in range(0, len(smooth_stencil)):
            slide_score_smooth += shifted_curve[n] * smooth_stencil[n]

        # Score spiky slide
        slide_score = 0.0
        for n in range(0, len(spike_stencil)):
            slide_score += shifted_curve[n] * spike_stencil[n]

        # Add spike and smooth scores
        if slide < 150:
            slide_score = slide_score + slide_score_smooth * 0.65

        # Track best slide
        if slide_score > best_slide_score:
            best_slide_score = slide_score
            best_slide = slide

        total_score += slide_score

    # Calculate price from best slide
    # Create bins (log scale, 1201 bins from 1e-8 to 100 BTC)
    bins = []
    for n in range(0, 1201):
        i = n / 100.0
        bins.append(10 ** (-8.0 + i * 0.01))

    best_slide_bin = center_p001 + best_slide
    usd100_in_btc_best = bins[best_slide_bin]
    btc_in_usd_best = 100 / usd100_in_btc_best

    # Neighbor refinement
    neighbor_up = histogram_array[
        left_p001 + best_slide + 1 : right_p001 + best_slide + 1
    ]
    neighbor_up_score = 0.0
    for n in range(0, len(spike_stencil)):
        neighbor_up_score += neighbor_up[n] * spike_stencil[n]

    neighbor_down = histogram_array[
        left_p001 + best_slide - 1 : right_p001 + best_slide - 1
    ]
    neighbor_down_score = 0.0
    for n in range(0, len(spike_stencil)):
        neighbor_down_score += neighbor_down[n] * spike_stencil[n]

    # Get best neighbor
    best_neighbor = +1
    neighbor_score = neighbor_up_score
    if neighbor_down_score > neighbor_up_score:
        best_neighbor = -1
        neighbor_score = neighbor_down_score

    # Get best neighbor price
    usd100_in_btc_2nd = bins[center_p001 + best_slide + best_neighbor]
    btc_in_usd_2nd = 100 / usd100_in_btc_2nd

    # Weight average
    avg_score = total_score / len(range(min_slide, max_slide))
    a1 = best_slide_score - avg_score
    a2 = abs(neighbor_score - avg_score)
    w1 = a1 / (a1 + a2)
    w2 = a2 / (a1 + a2)
    price = w1 * btc_in_usd_best + w2 * btc_in_usd_2nd

    return price


def library_convergence(histogram_dict: Dict[int, int]) -> float:
    """
    Library convergence algorithm (from UTXOracle_library.py).

    Args:
        histogram_dict: Dict mapping bin indices to counts

    Returns:
        Estimated BTC/USD price
    """
    from UTXOracle_library import UTXOracleCalculator

    # Create calculator and build histogram from dict
    calc = UTXOracleCalculator()

    # Call internal _estimate_price method
    result = calc._estimate_price(histogram_dict)

    return result["price_usd"]


def create_synthetic_histogram(price: float = 110000) -> Dict[int, int]:
    """
    Create synthetic histogram centered around a given price.

    Simulates a histogram with peaks at round USD amounts assuming the given BTC/USD price.

    Args:
        price: Assumed BTC/USD price (e.g., 110000)

    Returns:
        Histogram dict mapping bin index to transaction count
    """
    histogram = {}

    # Create bins (log scale, 1201 bins from 1e-8 to 100 BTC)
    bins = []
    for n in range(0, 1201):
        i = n / 100.0
        bins.append(10 ** (-8.0 + i * 0.01))

    # Add peaks at common USD amounts
    usd_amounts = [10, 20, 50, 100, 200, 500, 1000]

    for usd in usd_amounts:
        # Calculate BTC amount for this USD
        btc_amount = usd / price

        # Find closest bin
        closest_bin = None
        min_diff = float("inf")
        for i, bin_val in enumerate(bins):
            diff = abs(bin_val - btc_amount)
            if diff < min_diff:
                min_diff = diff
                closest_bin = i

        # Add transactions around this bin (Gaussian-like distribution)
        if closest_bin:
            # Peak at the center
            histogram[closest_bin] = histogram.get(closest_bin, 0) + 100

            # Add some spread
            for offset in range(-5, 6):
                bin_idx = closest_bin + offset
                if 0 <= bin_idx < 1201:
                    weight = math.exp(-0.5 * (offset / 2.0) ** 2)
                    count = int(50 * weight)
                    histogram[bin_idx] = histogram.get(bin_idx, 0) + count

    return histogram


def main():
    print("=" * 70)
    print("CONVERGENCE ALGORITHM TEST: Reference vs Library")
    print("=" * 70)

    # Test 1: Synthetic histogram at $110k
    print("\n[Test 1] Synthetic histogram centered at $110,000")
    print("-" * 70)

    histogram_dict = create_synthetic_histogram(price=110000)
    print(f"Created histogram with {len(histogram_dict)} non-zero bins")

    # Convert to array for reference algorithm
    histogram_array = [histogram_dict.get(i, 0) for i in range(1201)]

    # Run both algorithms
    print("\nRunning reference convergence algorithm...")
    ref_price = reference_convergence(histogram_array)
    print(f"  Reference price: ${ref_price:,.2f}")

    print("\nRunning library convergence algorithm...")
    lib_price = library_convergence(histogram_dict)
    print(f"  Library price:   ${lib_price:,.2f}")

    # Compare
    diff = abs(ref_price - lib_price)
    diff_pct = (diff / ref_price) * 100

    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    print(f"Reference price:  ${ref_price:,.2f}")
    print(f"Library price:    ${lib_price:,.2f}")
    print(f"Difference:       ${diff:,.2f} ({diff_pct:.3f}%)")

    # Verdict
    TOLERANCE = 0.01  # 0.01% tolerance
    if diff_pct < TOLERANCE:
        print(f"\n✅ PASS: Difference {diff_pct:.3f}% < {TOLERANCE}% tolerance")
        print("   Library convergence matches reference!")
    else:
        print(f"\n❌ FAIL: Difference {diff_pct:.3f}% >= {TOLERANCE}% tolerance")
        print("   Library convergence DOES NOT match reference!")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
