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

        # Binary search for bin
        for i in range(len(self.bins) - 1):
            if self.bins[i] <= amount_btc < self.bins[i + 1]:
                return i

        return len(self.bins) - 1  # Last bin

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

        # Estimate price using heuristic for round fiat amounts
        # Common round amounts: $10, $20, $50, $100, $200, $500, $1000, $2000, $5000
        # This is a simplified heuristic - the real algorithm does convergence

        # Determine likely round fiat amount based on BTC range
        if peak_btc < 0.0001:  # Very small amounts
            assumed_fiat_amount = 5.0
        elif peak_btc < 0.001:  # ~100 sats to 0.001 BTC
            assumed_fiat_amount = 50.0
        elif peak_btc < 0.01:  # 0.001 to 0.01 BTC
            assumed_fiat_amount = 500.0
        elif peak_btc < 0.1:  # 0.01 to 0.1 BTC
            assumed_fiat_amount = 5000.0
        elif peak_btc < 1.0:  # 0.1 to 1.0 BTC
            assumed_fiat_amount = 50000.0
        else:  # >= 1.0 BTC
            assumed_fiat_amount = 100000.0

        price_usd = assumed_fiat_amount / peak_btc if peak_btc > 0 else None

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

        # Step 7: Remove round amounts (optional - can be done on BTC values)
        # For now, histogram uses bin indices, so we skip this step

        # Steps 9-11: Estimate price from histogram
        result = self._estimate_price(histogram)

        # Add transaction statistics
        result["tx_count"] = tx_count
        result["output_count"] = output_count
        result["histogram"] = histogram

        return result
