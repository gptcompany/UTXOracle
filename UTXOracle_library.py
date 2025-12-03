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
from typing import Dict, List, Optional, Union

# T120: Pydantic models for type safety (v2)
try:
    from models import (
        BitcoinTransaction,
        DiagnosticsInfo,
        PriceResult,
        IntradayPriceResult,
    )

    PYDANTIC_AVAILABLE = True
except ImportError:
    # Graceful degradation if models.py not available
    PYDANTIC_AVAILABLE = False
    BitcoinTransaction = None
    DiagnosticsInfo = None
    PriceResult = None
    IntradayPriceResult = None


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

        EXACT MATCH to UTXOracle.py lines 998-1007.

        Returns:
            dict: Stencil weights (803 elements)
        """
        # Parameters (EXACT MATCH to lines 998-1001)
        num_elements = 803
        mean = 411  # (num_elements - 1) / 2  # Center of the array
        std_dev = 201

        # Construct the smooth stencil (EXACT MATCH to lines 1003-1007)
        smooth_stencil = []
        for x in range(num_elements):
            exp_part = -((x - mean) ** 2) / (2 * (std_dev**2))
            smooth_stencil.append(
                (0.00150 * 2.718281828459045**exp_part) + (0.0000005 * x)
            )

        # Convert list to dict for consistency with library API
        return {i: smooth_stencil[i] for i in range(len(smooth_stencil))}

    def _build_spike_stencil(self) -> Dict[int, float]:
        """
        T024: Create spike detection stencil (Step 8).

        EXACT MATCH to UTXOracle.py lines 1010-1044.

        Returns:
            dict: Stencil weights (803 elements with hardcoded USD amounts)
        """
        # Load the spike stencil that fine tunes the alignment on popular usd amounts
        # EXACT MATCH to lines 1011-1044
        spike_stencil = []
        for n in range(0, 803):
            spike_stencil.append(0.0)

        # round usd bin location   #popularity    #usd amount
        spike_stencil[40] = 0.001300198324984352  # $1
        spike_stencil[141] = 0.001676746949820743  # $5
        spike_stencil[201] = 0.003468805546942046  # $10
        spike_stencil[202] = 0.001991977522512513  #
        spike_stencil[236] = 0.001905066647961839  # $15
        spike_stencil[261] = 0.003341772718156079  # $20
        spike_stencil[262] = 0.002588902624584287  #
        spike_stencil[296] = 0.002577893841190244  # $30
        spike_stencil[297] = 0.002733728814200412  #
        spike_stencil[340] = 0.003076117748975647  # $50
        spike_stencil[341] = 0.005613067550103145  #
        spike_stencil[342] = 0.003088253178535568  #
        spike_stencil[400] = 0.002918457489366139  # $100
        spike_stencil[401] = 0.006174500465286022  #
        spike_stencil[402] = 0.004417068070043504  #
        spike_stencil[403] = 0.002628663628020371  #
        spike_stencil[436] = 0.002858828161543839  # $150
        spike_stencil[461] = 0.004097463611984264  # $200
        spike_stencil[462] = 0.003345917406120509  #
        spike_stencil[496] = 0.002521467726855856  # $300
        spike_stencil[497] = 0.002784125730361008  #
        spike_stencil[541] = 0.003792850444811335  # $500
        spike_stencil[601] = 0.003688240815848247  # $1000
        spike_stencil[602] = 0.002392400117402263  #
        spike_stencil[636] = 0.001280993059008106  # $1500
        spike_stencil[661] = 0.001654665137536031  # $2000
        spike_stencil[662] = 0.001395501347054946  #
        spike_stencil[741] = 0.001154279140906312  # $5000
        spike_stencil[801] = 0.000832244504868709  # $10000

        # Convert list to dict for consistency with library API
        return {i: spike_stencil[i] for i in range(len(spike_stencil))}

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
        # EXACT MATCH to UTXOracle.py line 1080
        center_p001 = 601  # 601 is where 0.001 btc is in the output bell curve

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

        # EXACT MATCH to UTXOracle.py lines 1081-1082
        left_p001 = center_p001 - int((spike_len + 1) / 2)
        right_p001 = center_p001 + int((spike_len + 1) / 2)

        # EXACT MATCH to UTXOracle.py lines 1089-1113
        for slide in range(min_slide, max_slide):
            # shift the bell curve by the slide
            shifted_curve = histogram_array[left_p001 + slide : right_p001 + slide]

            # score the smooth slide by multiplying the curve by the stencil
            slide_score_smooth = 0.0
            for n in range(0, len(smooth_stencil_list)):
                slide_score_smooth += shifted_curve[n] * smooth_stencil_list[n]

            # score the spiky slide by multiplying the curve by the stencil
            slide_score = 0.0
            for n in range(0, len(spike_stencil_list)):
                slide_score += shifted_curve[n] * spike_stencil_list[n]

            # add the spike and smooth slide scores, neglect smooth slide over wrong regions
            if slide < 150:
                slide_score = slide_score + slide_score_smooth * 0.65

            # see if this score is the best so far
            if slide_score > best_slide_score:
                best_slide_score = slide_score
                best_slide = slide

            # increment the total score
            total_score += slide_score

        # Calculate price from best slide position (EXACT MATCH to lines 1115-1117)
        best_slide_bin = center_p001 + best_slide

        if best_slide_bin < 0 or best_slide_bin >= len(self.bins):
            price_usd = None
        else:
            # estimate the usd price of the best slide
            usd100_in_btc_best = self.bins[best_slide_bin]
            btc_in_usd_best = 100 / (usd100_in_btc_best)

            # Neighbor refinement (EXACT MATCH to lines 1119-1133)
            # find best slide neighbor up
            neighbor_up = histogram_array[
                left_p001 + best_slide + 1 : right_p001 + best_slide + 1
            ]
            neighbor_up_score = 0.0
            for n in range(0, spike_len):
                neighbor_up_score += neighbor_up[n] * spike_stencil_list[n]

            # find best slide neighbor down
            neighbor_down = histogram_array[
                left_p001 + best_slide - 1 : right_p001 + best_slide - 1
            ]
            neighbor_down_score = 0.0
            for n in range(0, spike_len):
                neighbor_down_score += neighbor_down[n] * spike_stencil_list[n]

            # get best neighbor (EXACT MATCH to lines 1136-1140)
            best_neighbor = +1
            neighbor_score = neighbor_up_score
            if neighbor_down_score > neighbor_up_score:
                best_neighbor = -1
                neighbor_score = neighbor_down_score

            # get best neighbor usd price (EXACT MATCH to lines 1143-1144)
            usd100_in_btc_2nd = self.bins[center_p001 + best_slide + best_neighbor]
            btc_in_usd_2nd = 100 / (usd100_in_btc_2nd)

            # weight average the two usd price estimates (EXACT MATCH to lines 1147-1152)
            avg_score = total_score / len(range(min_slide, max_slide))
            a1 = best_slide_score - avg_score
            a2 = abs(neighbor_score - avg_score)

            # BUGFIX: Handle edge case when a1 + a2 == 0 (uniform scores)
            # This happens with very small datasets or uniform histograms
            if a1 + a2 == 0:
                # Use simple average when scores are identical
                price_usd = (btc_in_usd_best + btc_in_usd_2nd) / 2
            else:
                w1 = a1 / (a1 + a2)
                w2 = a2 / (a1 + a2)
                price_usd = w1 * btc_in_usd_best + w2 * btc_in_usd_2nd

        return {
            "price_usd": price_usd,
            "confidence": confidence,
            "peak_bin": peak_bin,
            "peak_btc": peak_btc,
        }

    def _find_central_output(
        self, prices: List[float], price_min: float, price_max: float
    ) -> tuple:
        """
        T112: Find the most central price point using center-of-mass algorithm.

        This is the core of Step 11 (Find Exact Average Price). Uses geometric median
        to find the price that minimizes total distance to all other prices.

        Args:
            prices: List of price points (USD/BTC)
            price_min: Lower bound for filtering
            price_max: Upper bound for filtering

        Returns:
            (central_price, median_absolute_deviation)

        Extracted from UTXOracle.py lines 1274-1314
        """
        # Filter prices within range
        outputs = sorted([p for p in prices if price_min < p < price_max])
        n = len(outputs)

        if n == 0:
            return None, None

        # Prefix sums for efficient distance calculation
        prefix_sum = []
        total = 0
        for x in outputs:
            total += x
            prefix_sum.append(total)

        # Count points left and right of each position
        left_counts = list(range(n))
        right_counts = [n - i - 1 for i in left_counts]
        left_sums = [0] + prefix_sum[:-1]
        right_sums = [total - x for x in prefix_sum]

        # Find total distance to other points for each position
        total_dists = []
        for i in range(n):
            dist = (outputs[i] * left_counts[i] - left_sums[i]) + (
                right_sums[i] - outputs[i] * right_counts[i]
            )
            total_dists.append(dist)

        # Find the most central output (minimum total distance)
        min_index, _ = min(enumerate(total_dists), key=lambda x: x[1])
        best_output = outputs[min_index]

        # Calculate median absolute deviation
        deviations = [abs(x - best_output) for x in outputs]
        deviations.sort()
        m = len(deviations)
        if m % 2 == 0:
            mad = (deviations[m // 2 - 1] + deviations[m // 2]) / 2
        else:
            mad = deviations[m // 2]

        return best_output, mad

    def _create_intraday_price_points(
        self, raw_outputs: List[float], rough_price: float
    ) -> List[float]:
        """
        T111: Create intraday price points from raw outputs (Step 10).

        For each output, calculates the implied USD/BTC price based on common
        round USD amounts ($5, $10, $20, $50, $100, etc.). Filters out round
        BTC amounts to avoid false signals.

        Args:
            raw_outputs: List of BTC output amounts
            rough_price: Rough price estimate from Step 9

        Returns:
            List of intraday price points (USD/BTC)

        Extracted from UTXOracle.py lines 1183-1249
        """
        # Common round USD amounts
        usds = [5, 10, 15, 20, 25, 30, 40, 50, 100, 150, 200, 300, 500, 1000]

        # Price range: ±25% of rough estimate
        pct_range_wide = 0.25

        # Build micro round satoshi amounts list (to filter out)
        micro_remove_list = []
        i = 0.00005000
        while i < 0.0001:
            micro_remove_list.append(i)
            i += 0.00001
        i = 0.0001
        while i < 0.001:
            micro_remove_list.append(i)
            i += 0.00001
        i = 0.001
        while i < 0.01:
            micro_remove_list.append(i)
            i += 0.0001
        i = 0.01
        while i < 0.1:
            micro_remove_list.append(i)
            i += 0.001
        i = 0.1
        while i < 1:
            micro_remove_list.append(i)
            i += 0.01
        pct_micro_remove = 0.0001

        # Create price points
        output_prices = []

        for btc_amount in raw_outputs:
            # Try each USD amount
            for usd in usds:
                # Calculate BTC range for this USD amount
                avg_btc = usd / rough_price
                btc_up = avg_btc + pct_range_wide * avg_btc
                btc_dn = avg_btc - pct_range_wide * avg_btc

                # Check if output is within range
                if btc_dn < btc_amount < btc_up:
                    append = True

                    # Filter out round BTC amounts
                    for round_btc in micro_remove_list:
                        rm_dn = round_btc - pct_micro_remove * round_btc
                        rm_up = round_btc + pct_micro_remove * round_btc
                        if rm_dn < btc_amount < rm_up:
                            append = False

                    # Add price point if not round BTC
                    if append:
                        output_prices.append(usd / btc_amount)

        return output_prices

    def _iterate_convergence(
        self, output_prices: List[float], rough_price: float
    ) -> tuple:
        """
        T113: Find exact average price using single central output calculation (Step 11).

        ⚠️  CRITICAL VALIDATION NOTE (Nov 2, 2025):

        The reference implementation (UTXOracle.py lines 1328-1330) has a logic bug where
        the convergence loop NEVER executes:

            avs = set()
            avs.add(central_price)           # Adds central_price to set
            while central_price not in avs:  # ← Condition is FALSE immediately!
                avs.add(central_price)
                central_price, av_dev = find_central_output(...)

        This library correctly implements what the reference ACTUALLY does (single call),
        not what it appears it should do (iterative convergence).

        ✅ VALIDATED: Library matches reference exactly across multiple dates:
           - Oct 15, 2025: Library $111,652 vs Reference $111,652 (0.00% diff)
           - 5 random October dates: All perfect matches (<$1 difference)
           - See: test_october_validation.py, test_library_direct_comparison.py

        ⚠️  DO NOT "fix" this to add iteration - that would break compatibility!
            If you want to improve the algorithm, create a new version instead.

        Uses _find_central_output() to locate the geometric median of price points
        within ±5% of the rough estimate.

        Args:
            output_prices: List of intraday price points from Step 10
            rough_price: Initial rough estimate from Step 9

        Returns:
            (central_price, deviation_percentage)

        Extracted from UTXOracle.py lines 1317-1347
        """
        if not output_prices:
            return None, None

        # Use tight range: ±5% of rough estimate (reference line 1318)
        pct_range_tight = 0.05
        price_up = rough_price + pct_range_tight * rough_price
        price_dn = rough_price - pct_range_tight * rough_price

        # Find central price ONCE (reference lines 1321, 1328-1330 loop never executes!)
        central_price, av_dev = self._find_central_output(
            output_prices, price_dn, price_up
        )

        if central_price is None:
            return None, None

        # Calculate deviation using wider range ±10% (reference lines 1342-1347)
        pct_range_med = 0.1
        price_up = central_price + pct_range_med * central_price
        price_dn = central_price - pct_range_med * central_price
        price_range = price_up - price_dn
        _, av_dev = self._find_central_output(output_prices, price_dn, price_up)

        dev_pct = av_dev / price_range if av_dev and price_range > 0 else 0.0

        return central_price, dev_pct

    def calculate_price_for_transactions(
        self, transactions: List[dict], return_diagnostics: bool = True
    ) -> Dict:
        """
        T026: Public API - Calculate price from transaction list.

        This is the main entry point for price calculation. Takes raw transaction
        data and returns the estimated BTC/USD price with confidence score.

        Args:
            transactions: List of Bitcoin transaction dicts (from RPC or mempool)
                Each transaction should have:
                - 'vout': List of outputs with 'value' (BTC)
                - 'vin': List of inputs
            return_diagnostics: If True, include filtering diagnostics in result
                (default: True for v2)

        Returns:
            dict: {
                'price_usd': float or None,
                'confidence': float (0-1),
                'tx_count': int,
                'output_count': int,
                'histogram': dict,
                'diagnostics': dict (if return_diagnostics=True) {
                    'total_txs': int,
                    'filtered_inputs': int,
                    'filtered_outputs': int,
                    'filtered_coinbase': int,
                    'filtered_op_return': int,
                    'filtered_witness': int,
                    'filtered_same_day': int,
                    'total_filtered': int,
                    'passed_filter': int
                }
            }

        T026: Orchestrates all steps (Step 6 + existing methods)
        T122: Added return_diagnostics parameter for monitoring and debugging
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
        raw_outputs = []  # NEW: Save raw outputs for Step 10
        tx_count = 0
        output_count = 0

        # Diagnostic counters
        filtered_inputs = 0
        filtered_outputs = 0
        filtered_coinbase = 0
        filtered_op_return = 0
        filtered_witness = 0
        filtered_same_day = 0

        # Build set of TXIDs for same-day check dynamically to match reference script
        todays_txids = set()

        for tx in transactions:
            # Basic filtering (from UTXOracle.py Step 6 filters)
            vouts = tx.get("vout", [])
            vins = tx.get("vin", [])

            # Filter: Skip transactions with too many inputs (likely consolidations)
            # Reference: input_count <= 5
            if len(vins) > 5:
                filtered_inputs += 1
                continue

            # Filter: EXACTLY 2 outputs (not 1, not 3+)
            # Reference: output_count == 2 (line 861 in UTXOracle.py)
            # ✓ FIX: Changed from "> 2" to "!= 2" for exact match
            if len(vouts) != 2:
                filtered_outputs += 1
                continue

            # Filter: Skip coinbase transactions
            # Reference: not is_coinbase (line 862)
            if any("coinbase" in vin for vin in vins):
                filtered_coinbase += 1
                continue

            # Filter: Skip OP_RETURN outputs
            # Reference: not has_op_return (line 863)
            has_op_return = False
            for vout in vouts:
                script = vout.get("scriptPubKey", {})
                asm = script.get("asm", "")
                if asm and asm.startswith("OP_RETURN"):
                    has_op_return = True
                    break
            if has_op_return:
                filtered_op_return += 1
                continue

            # Filter: Skip transactions with excessive witness data
            # Reference: witness_exceeds check (line 836-845)
            witness_exceeds = False
            for vin in vins:
                # Check if tx has witness data (SegWit)
                txinwitness = vin.get("txinwitness", [])
                if txinwitness:
                    total_witness_len = 0
                    for witness_item in txinwitness:
                        # witness_item is hex string, length in bytes = len(hex)/2
                        item_len = len(witness_item) // 2
                        total_witness_len += item_len
                        if item_len > 500 or total_witness_len > 500:
                            witness_exceeds = True
                            break
                if witness_exceeds:
                    break

            if witness_exceeds:
                filtered_witness += 1
                continue

            # Filter: Skip same-day transactions (Corrected Logic)
            # A transaction is "same-day" if any of its inputs spend outputs
            # from a transaction *already processed* in this batch.
            is_same_day_tx = False
            for vin in vins:
                input_txid = vin.get("txid", "")
                if input_txid in todays_txids:
                    is_same_day_tx = True
                    break

            # Add the current transaction's ID to the set *after* checking its inputs.
            # This correctly mimics the behavior of the original script.
            todays_txids.add(tx.get("txid", ""))

            if is_same_day_tx:
                filtered_same_day += 1
                continue

            tx_count += 1

            # Count outputs into histogram + save raw outputs
            # IMPORTANT: Only save outputs that get binned (reference lines 867-884)
            for vout in vouts:
                value_btc = vout.get("value", 0)

                # CRITICAL FIX: This filter exists in the reference script (line 817)
                # but was missing from the library implementation.
                if not (1e-5 < value_btc < 1e5):
                    continue

                # Try to bin the output
                bin_idx = self._get_bin_index(value_btc)
                if bin_idx is not None:
                    # Add to histogram
                    histogram[bin_idx] = histogram.get(bin_idx, 0) + 1
                    output_count += 1

                    # Save for Step 10 (intraday price points)
                    # Only binned outputs go to raw_outputs (reference line 875, 882)
                    raw_outputs.append(value_btc)

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

        # Step 9: Get rough price estimate from histogram
        rough_result = self._estimate_price(histogram)
        rough_price = rough_result.get("price_usd")

        # Steps 10-11: Create intraday price points and converge to exact price
        if rough_price and len(raw_outputs) > 0:
            # Step 10: Create intraday price points
            intraday_prices = self._create_intraday_price_points(
                raw_outputs, rough_price
            )

            # Step 11: Iterative convergence to find exact average price
            if len(intraday_prices) > 0:
                final_price, dev_pct = self._iterate_convergence(
                    intraday_prices, rough_price
                )

                if final_price:
                    # Use converged price as final result
                    result = {
                        "price_usd": final_price,
                        "confidence": rough_result.get("confidence", 0.0),
                        "peak_bin": rough_result.get("peak_bin"),
                        "peak_btc": rough_result.get("peak_btc"),
                    }
                else:
                    # Convergence failed, fall back to rough estimate
                    result = rough_result
            else:
                # No intraday prices generated, use rough estimate
                result = rough_result
        else:
            # No rough price or no outputs, return rough result
            result = rough_result

        # Add transaction statistics
        result["tx_count"] = tx_count
        result["output_count"] = output_count
        result["histogram"] = histogram

        # T122: Diagnostic logging (conditionally included)
        if return_diagnostics:
            total_filtered = (
                filtered_inputs
                + filtered_outputs
                + filtered_coinbase
                + filtered_op_return
                + filtered_witness
                + filtered_same_day
            )
            result["diagnostics"] = {
                "total_txs": len(transactions),
                "filtered_inputs": filtered_inputs,
                "filtered_outputs": filtered_outputs,
                "filtered_coinbase": filtered_coinbase,
                "filtered_op_return": filtered_op_return,
                "filtered_witness": filtered_witness,
                "filtered_same_day": filtered_same_day,
                "total_filtered": total_filtered,
                "passed_filter": tx_count,
            }

        return result

    # T120: Pydantic conversion helpers (v2 API)
    def to_pydantic(self, result: Dict) -> Union["PriceResult", Dict]:
        """
        Convert dict result to Pydantic PriceResult model.

        This provides type-safe access with IDE autocomplete and validation.
        Falls back to dict if Pydantic is not available.

        Args:
            result: Dict result from calculate_price_for_transactions()

        Returns:
            PriceResult model (if Pydantic available) or dict (fallback)

        Example:
            >>> calc = UTXOracleCalculator()
            >>> result_dict = calc.calculate_price_for_transactions(txs)
            >>> result_typed = calc.to_pydantic(result_dict)
            >>> print(result_typed.price_usd)  # IDE autocomplete works!
            110537.54
        """
        if not PYDANTIC_AVAILABLE:
            return result  # Graceful degradation

        # Convert diagnostics if present
        diagnostics = None
        if "diagnostics" in result:
            diagnostics = DiagnosticsInfo(**result["diagnostics"])

        # Create PriceResult
        return PriceResult(
            price_usd=result.get("price_usd"),
            confidence=result.get("confidence", 0.0),
            tx_count=result.get("tx_count", 0),
            output_count=result.get("output_count", 0),
            histogram=result.get("histogram", {}),
            diagnostics=diagnostics,
        )
