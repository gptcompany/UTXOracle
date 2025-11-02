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
            w1 = a1 / (a1 + a2)
            w2 = a2 / (a1 + a2)
            price_usd = w1 * btc_in_usd_best + w2 * btc_in_usd_2nd

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

        # Diagnostic counters
        filtered_inputs = 0
        filtered_outputs = 0
        filtered_coinbase = 0
        filtered_op_return = 0
        filtered_witness = 0
        filtered_same_day = 0

        # Build set of TXIDs for same-day check (reference line 856)
        todays_txids = {tx.get("txid", "") for tx in transactions}

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

            # Filter: Skip same-day transactions
            # Reference: is_same_day_tx check (line 856)
            # A transaction is "same-day" if any of its inputs spend outputs
            # created earlier in the same day (same block set)
            is_same_day_tx = False
            for vin in vins:
                # Check if input spends output from same day
                input_txid = vin.get("txid", "")
                if input_txid in todays_txids:
                    is_same_day_tx = True
                    break

            if is_same_day_tx:
                filtered_same_day += 1
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

        # Diagnostic logging
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
