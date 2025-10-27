"""
UTXOracle Library - Refactored Algorithm

Extracts Steps 5-11 from UTXOracle.py into a reusable Python library.
This enables:
- Importable by other Python code (no subprocess needed)
- Clean API for future Rust migration (PyO3 drop-in replacement)
- Backward compatibility with existing UTXOracle.py CLI

Spec: 003-mempool-integration-refactor
Phase: 2 - Algorithm Refactor
Tasks: T019-T029 (implementation)

Algorithm Overview:
    1. Build logarithmically-spaced histogram bins (Step 5)
    2. Count transaction outputs into bins (Step 6 - caller provides data)
    3. Remove round BTC amounts (Step 7)
    4. Build smooth/spike stencils (Step 8)
    5. Estimate price using stencil convolution (Steps 9-11)
"""

import bisect
from typing import Dict, List, Optional


class UTXOracleCalculator:
    """
    Bitcoin on-chain price calculator using statistical clustering.

    Uses histogram analysis and stencil convolution to detect round fiat amounts
    in on-chain transaction data, enabling exchange-free price discovery.

    Example:
        >>> calc = UTXOracleCalculator()
        >>> transactions = fetch_transactions_from_bitcoin_core()
        >>> result = calc.calculate_price_for_transactions(transactions)
        >>> print(f"Price: ${result['price_usd']:,.2f} (confidence: {result['confidence']:.2f})")
    """

    def __init__(self):
        """Initialize calculator with default parameters."""
        # Histogram configuration (from Step 5)
        self.first_bin_value = -6  # 10^-6 BTC minimum
        self.last_bin_value = 6  # 10^6 BTC maximum
        self.bins_per_decade = 200  # 200 bins per 10x range

        # Build bins once during initialization
        self.bins = self._build_histogram_bins()

    def _build_histogram_bins(self) -> List[float]:
        """
        T020: Create logarithmically-spaced histogram bins (Step 5).

        Generates 2401 bins covering BTC range from 0 to 10^6.
        - Bin 0: 0.0 BTC (zero sats)
        - Bins 1-2400: Log-spaced from 10^-6 to 10^6 BTC (200 bins per decade)

        Returns:
            list[float]: Bin edges in BTC

        Extracted from UTXOracle.py lines 620-635
        """
        bins = [0.0]  # First bin is zero sats

        # Calculate BTC amounts of 200 samples in every 10x from 1e-6 to 1e6 BTC
        for exponent in range(self.first_bin_value, self.last_bin_value):
            for b in range(0, self.bins_per_decade):
                bin_value = 10 ** (exponent + b / self.bins_per_decade)
                bins.append(bin_value)

        return bins

    def _get_bin_index(self, amount_btc: float) -> Optional[int]:
        """
        T021: Find histogram bin index for a given BTC amount.

        Uses binary search to find the appropriate bin for the transaction amount.

        Args:
            amount_btc: Transaction output amount in BTC

        Returns:
            int or None: Bin index, or None if out of range

        Extracted from UTXOracle.py histogram insertion logic
        """
        if amount_btc <= 0:
            return 0

        # Out of range check
        if amount_btc < self.bins[1]:  # Smaller than minimum
            return None
        if amount_btc > self.bins[-1]:  # Larger than maximum
            return None

        # Binary search using bisect (O(log n) instead of O(n))
        # bisect_left returns index where amount_btc would be inserted
        idx = bisect.bisect_left(self.bins, amount_btc)

        # If exact match, return that bin
        if idx < len(self.bins) and self.bins[idx] == amount_btc:
            return idx

        # Otherwise return previous bin (amount falls between bins[idx-1] and bins[idx])
        return idx - 1 if idx > 0 else 0

    def _remove_round_amounts(self, histogram: Dict[float, int]) -> Dict[float, int]:
        """
        T022: Filter out round Bitcoin amounts from histogram (Step 7).

        Round BTC amounts (1.0, 5.0, 10.0, etc.) are likely test transactions
        or non-market activity and should be excluded from price analysis.

        Args:
            histogram: Dict mapping amounts (BTC) to counts

        Returns:
            dict: Filtered histogram

        Extracted from UTXOracle.py lines 889-970 (Step 7)
        """
        filtered = {}

        for amount, count in histogram.items():
            # Check if amount is "round" (ends in .0, .00, .000, etc.)
            # Round integers: 1.0, 2.0, 5.0, 10.0, 100.0
            # Allow: 0.5, 1.5, 1.23456, etc.
            if isinstance(amount, float):
                # Check if it's a whole number
                if amount == int(amount) and amount >= 1.0:
                    continue  # Skip round amounts

            filtered[amount] = count

        return filtered

    def _build_smooth_stencil(self) -> Dict[int, float]:
        """
        T023: Create smooth detection stencil (Step 8).

        A wider Gaussian-like stencil for detecting broad peaks in the histogram.
        This represents the expected distribution of round fiat amounts.

        Returns:
            dict: Stencil weights by bin offset

        Extracted from UTXOracle.py lines 971-1048 (Step 8 - smooth stencil)
        """
        stencil = {}

        # Create Gaussian-like weights centered at 0
        # Width of ~40 bins (covers ~1% price range on log scale)
        sigma = 15  # Standard deviation in bins
        center = 0

        for offset in range(-40, 41):
            # Gaussian weight
            weight = (1.0 / (sigma * (2 * 3.14159) ** 0.5)) * 2.71828 ** (
                -0.5 * ((offset - center) / sigma) ** 2
            )
            stencil[offset] = weight

        # Normalize so weights sum to 1
        total_weight = sum(stencil.values())
        for offset in stencil:
            stencil[offset] /= total_weight

        return stencil

    def _build_spike_stencil(self) -> Dict[int, float]:
        """
        T024: Create spike detection stencil (Step 8).

        A narrower stencil for detecting sharp peaks in the histogram.
        This helps identify strong price signals.

        Returns:
            dict: Stencil weights by bin offset

        Extracted from UTXOracle.py lines 971-1048 (Step 8 - spike stencil)
        """
        stencil = {}

        # Create narrower Gaussian weights
        sigma = 5  # Smaller standard deviation = sharper peak
        center = 0

        for offset in range(-15, 16):
            weight = (1.0 / (sigma * (2 * 3.14159) ** 0.5)) * 2.71828 ** (
                -0.5 * ((offset - center) / sigma) ** 2
            )
            stencil[offset] = weight

        # Normalize
        total_weight = sum(stencil.values())
        for offset in stencil:
            stencil[offset] /= total_weight

        return stencil

    def _estimate_price(self, histogram: Dict[int, int]) -> Dict:
        """
        T025: Estimate BTC/USD price from histogram (Steps 9-11).

        Uses stencil convolution and convergence algorithm to find the most
        likely round fiat amount, then calculates the implied BTC/USD price.

        Args:
            histogram: Dict mapping bin indices to transaction counts

        Returns:
            dict: {
                'price_usd': float,
                'confidence': float (0-1),
                'peak_bin': int,
                'peak_btc': float
            }

        Extracted from UTXOracle.py lines 1049-1259 (Steps 9-11)
        """
        if not histogram:
            return {
                "price_usd": None,
                "confidence": 0.0,
                "peak_bin": None,
                "peak_btc": None,
            }

        # Build stencils
        smooth_stencil = self._build_smooth_stencil()
        spike_stencil = self._build_spike_stencil()

        # Convolve histogram with stencils to find peaks
        convolved = {}
        for bin_idx in range(len(self.bins)):
            smooth_sum = 0
            spike_sum = 0

            # Apply smooth stencil
            for offset, weight in smooth_stencil.items():
                target_bin = bin_idx + offset
                if 0 <= target_bin < len(self.bins):
                    smooth_sum += histogram.get(target_bin, 0) * weight

            # Apply spike stencil
            for offset, weight in spike_stencil.items():
                target_bin = bin_idx + offset
                if 0 <= target_bin < len(self.bins):
                    spike_sum += histogram.get(target_bin, 0) * weight

            # Combined score (favor bins with both smooth and spike signals)
            convolved[bin_idx] = smooth_sum * spike_sum

        # Find peak bin
        peak_bin = max(convolved, key=convolved.get)
        peak_value = convolved[peak_bin]

        # Calculate confidence (ratio of peak to average)
        avg_value = sum(convolved.values()) / len(convolved)
        confidence = min(1.0, peak_value / (avg_value * 10)) if avg_value > 0 else 0.0

        # Get BTC amount at peak
        peak_btc = self.bins[peak_bin]

        # Convergence algorithm (Step 9 from UTXOracle.py lines 1070-1152)
        # Find best price by sliding stencils and scoring each position

        # Convert histogram dict to array for sliding window
        histogram_array = [histogram.get(i, 0) for i in range(len(self.bins))]

        # Stencil configurations (from Step 8)
        smooth_stencil_list = [smooth_stencil[k] for k in sorted(smooth_stencil.keys())]
        spike_stencil_list = [spike_stencil[k] for k in sorted(spike_stencil.keys())]
        spike_len = len(spike_stencil_list)

        # Establish center position: 0.001 BTC at $100 = $100k price
        # Find bin index for 0.001 BTC
        center_p001 = self._get_bin_index(0.001)
        if center_p001 is None:
            center_p001 = len(self.bins) // 2  # Fallback to middle

        # Slide range (from UTXOracle.py lines 1085-1086)
        # min_slide = -141 allows up to ~$500k, max_slide = 201 allows down to ~$5k
        min_slide = -141
        max_slide = 201

        # Weights for smooth vs spike (from line 1076-1077)
        smooth_weight = 0.65
        spike_weight = 1.0

        # Slide stencils and find best position
        best_slide = 0
        best_slide_score = 0
        total_score = 0

        left_offset = center_p001 - spike_len // 2
        right_offset = center_p001 + spike_len // 2

        for slide in range(min_slide, max_slide):
            # Extract histogram window at this slide position
            start = left_offset + slide
            end = right_offset + slide

            # Bounds check
            if start < 0 or end >= len(histogram_array):
                continue

            shifted_curve = histogram_array[start:end]
            if len(shifted_curve) != spike_len:
                continue

            # Score with spike stencil
            slide_score = sum(
                shifted_curve[n] * spike_stencil_list[n] for n in range(spike_len)
            )

            # Add smooth stencil contribution (only for slide < 150, line 1104)
            if slide < 150 and len(shifted_curve) == len(smooth_stencil_list):
                slide_score_smooth = sum(
                    shifted_curve[n] * smooth_stencil_list[n]
                    for n in range(len(smooth_stencil_list))
                )
                slide_score += slide_score_smooth * smooth_weight

            # Track best slide
            if slide_score > best_slide_score:
                best_slide_score = slide_score
                best_slide = slide

            total_score += slide_score

        # Calculate price from best slide position
        # Best slide bin index
        best_slide_bin = center_p001 + best_slide
        if best_slide_bin < 0 or best_slide_bin >= len(self.bins):
            price_usd = None
        else:
            # BTC amount at best slide position
            usd100_in_btc_best = self.bins[best_slide_bin]
            # Implied price: $100 / BTC_amount = $/BTC
            btc_in_usd_best = (
                100.0 / usd100_in_btc_best if usd100_in_btc_best > 0 else None
            )

            # Neighbor refinement (lines 1119-1152)
            # Check neighbor bins up and down
            neighbor_up_bin = best_slide_bin + 1
            neighbor_down_bin = best_slide_bin - 1

            neighbor_up_score = 0
            neighbor_down_score = 0

            # Score neighbor up
            if neighbor_up_bin < len(self.bins):
                start = left_offset + best_slide + 1
                end = right_offset + best_slide + 1
                if 0 <= start < len(histogram_array) and end <= len(histogram_array):
                    neighbor_up_curve = histogram_array[start:end]
                    if len(neighbor_up_curve) == spike_len:
                        neighbor_up_score = sum(
                            neighbor_up_curve[n] * spike_stencil_list[n]
                            for n in range(spike_len)
                        )

            # Score neighbor down
            if neighbor_down_bin >= 0:
                start = left_offset + best_slide - 1
                end = right_offset + best_slide - 1
                if 0 <= start < len(histogram_array) and end <= len(histogram_array):
                    neighbor_down_curve = histogram_array[start:end]
                    if len(neighbor_down_curve) == spike_len:
                        neighbor_down_score = sum(
                            neighbor_down_curve[n] * spike_stencil_list[n]
                            for n in range(spike_len)
                        )

            # Get best neighbor and its price
            if neighbor_up_score > neighbor_down_score:
                best_neighbor_bin = neighbor_up_bin
                neighbor_score = neighbor_up_score
            else:
                best_neighbor_bin = neighbor_down_bin
                neighbor_score = neighbor_down_score

            # Weighted average of best and neighbor prices
            if best_neighbor_bin >= 0 and best_neighbor_bin < len(self.bins):
                usd100_in_btc_2nd = self.bins[best_neighbor_bin]
                btc_in_usd_2nd = (
                    100.0 / usd100_in_btc_2nd
                    if usd100_in_btc_2nd > 0
                    else btc_in_usd_best
                )

                # Weighting based on score difference from average
                avg_score = (
                    total_score / (max_slide - min_slide)
                    if max_slide > min_slide
                    else 1
                )
                a1 = best_slide_score - avg_score
                a2 = abs(neighbor_score - avg_score)

                if a1 + a2 > 0:
                    w1 = a1 / (a1 + a2)
                    w2 = a2 / (a1 + a2)
                    price_usd = w1 * btc_in_usd_best + w2 * btc_in_usd_2nd
                else:
                    price_usd = btc_in_usd_best
            else:
                price_usd = btc_in_usd_best

        return {
            "price_usd": price_usd,
            "confidence": confidence,
            "peak_bin": peak_bin,
            "peak_btc": peak_btc,
        }

    def calculate_price_for_transactions(self, transactions: List[dict]) -> Dict:
        """
        T026: Public API - Calculate price from transaction list.

        This is the main entry point for price calculation. Takes raw transaction
        data and returns the estimated BTC/USD price with confidence score.

        Args:
            transactions: List of Bitcoin transaction dicts (from RPC or mempool)
                Each transaction should have:
                - 'vout': List of outputs with 'value' (BTC)
                - 'vin': List of inputs

        Returns:
            dict: {
                'price_usd': float or None,
                'confidence': float (0-1),
                'tx_count': int,
                'output_count': int,
                'histogram': dict
            }

        T026: Orchestrates all steps (Step 6 + existing methods)
        """
        if not transactions:
            return {
                "price_usd": None,
                "confidence": 0.0,
                "tx_count": 0,
                "output_count": 0,
                "histogram": {},
            }

        # Step 6: Build histogram from transactions
        histogram = {}
        tx_count = 0
        output_count = 0

        for tx in transactions:
            # Basic filtering (from UTXOracle.py Step 6 filters)
            vouts = tx.get("vout", [])
            vins = tx.get("vin", [])

            # Filter: Skip transactions with too many inputs (likely consolidations)
            if len(vins) > 5:
                continue

            # Filter: Skip transactions with too many outputs (likely batch payments)
            if len(vouts) > 2:
                continue

            tx_count += 1

            # Count outputs into histogram
            for vout in vouts:
                value_btc = vout.get("value", 0)
                if value_btc <= 0:
                    continue

                bin_idx = self._get_bin_index(value_btc)
                if bin_idx is not None:
                    histogram[bin_idx] = histogram.get(bin_idx, 0) + 1
                    output_count += 1

        # Step 7: Smooth round BTC amounts and normalize (lines 889-965)
        # Remove extreme bins
        for n in range(0, 201):  # Below 10k sats
            histogram[n] = 0
        for n in range(1601, len(self.bins)):  # Above 10 BTC
            histogram[n] = 0

        # Smooth round BTC bin amounts (don't remove - average with neighbors)
        round_btc_bins = [
            201,  # 1k sats
            401,  # 10k
            461,  # 20k
            496,  # 30k
            540,  # 50k
            601,  # 100k
            661,  # 200k
            696,  # 300k
            740,  # 500k
            801,  # 0.01 btc
            861,  # 0.02
            896,  # 0.03
            940,  # 0.04
            1001,  # 0.1
            1061,  # 0.2
            1096,  # 0.3
            1140,  # 0.5
            1201,  # 1 btc
        ]

        for r in round_btc_bins:
            if r > 0 and r < len(self.bins) - 1:
                amount_above = histogram.get(r + 1, 0)
                amount_below = histogram.get(r - 1, 0)
                histogram[r] = 0.5 * (amount_above + amount_below)

        # Normalize histogram (percentages)
        curve_sum = sum(histogram.get(n, 0) for n in range(201, 1601))
        if curve_sum > 0:
            for n in range(201, 1601):
                if n in histogram:
                    histogram[n] /= curve_sum
                    # Cap extremes (from historical testing)
                    if histogram[n] > 0.008:
                        histogram[n] = 0.008

        # Steps 9-11: Estimate price from histogram
        result = self._estimate_price(histogram)

        # Add transaction statistics
        result["tx_count"] = tx_count
        result["output_count"] = output_count
        result["histogram"] = histogram

        return result
