"""
Baseline Price Calculator (T095-T097)

Copies UTXOracle.py Steps 5,7-11 for 24h baseline calculation.
Algorithm from UTXOracle.py v9.1 - DO NOT MODIFY without verifying against reference.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple, Optional
import time
import os
import math
import platform

from .bitcoin_rpc import BitcoinRPC

logger = logging.getLogger("live.baseline")


@dataclass
class BaselineResult:
    price: float
    price_min: float
    price_max: float
    confidence: float
    timestamp: float
    block_height: Optional[int] = None
    num_transactions: int = 0
    transactions: List[Tuple[float, float]] = None  # [(amount_btc, timestamp), ...]
    intraday_points: List[Tuple[float, float, float]] = (
        None  # [(price, block_height, timestamp), ...] from Step 10
    )


class BaselineCalculator:
    def __init__(self, window_blocks: int = 144, bitcoin_datadir: str = None):
        self.window_blocks = window_blocks
        self.blocks = deque(maxlen=window_blocks)
        self.last_updated = 0.0
        self.last_block_height = None
        self.histogram_bins = self._initialize_histogram_bins()
        self.smooth_stencil = self._create_smooth_stencil()
        self.spike_stencil = self._create_spike_stencil()

        # T112 & T115: RPC initialization
        self.bitcoin_datadir = bitcoin_datadir or self._get_default_datadir()
        try:
            self.rpc = BitcoinRPC(datadir=self.bitcoin_datadir)
            # Load historical blocks at startup
            logger.info("Loading last 144 blocks from blockchain for baseline...")
            self._load_historical_blocks()
            logger.info(
                f"Baseline initialized with {len(self.blocks)} blocks and "
                f"{sum(len(b['transactions']) for b in self.blocks)} transactions."
            )

            # Calculate baseline immediately after loading blocks
            if len(self.blocks) >= 10:
                baseline_result = self.calculate_baseline()
                if baseline_result:
                    logger.info(
                        f"Initial baseline calculated: ${baseline_result.price:,.0f}"
                    )

        except Exception as e:
            logger.error(
                f"Failed to initialize BaselineCalculator RPC: {e}", exc_info=True
            )
            # Allow startup without baseline if node is offline
            self.rpc = None

    def _get_default_datadir(self):
        """Helper to find default Bitcoin data directory."""
        system = os.name
        if system == "nt":  # Windows
            return os.path.join(os.environ.get("APPDATA", ""), "Bitcoin")

        if platform.system() == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Bitcoin")

        return os.path.expanduser("~/.bitcoin")  # Linux

    def _initialize_histogram_bins(self) -> List[float]:
        """Initialize histogram bins (same as UTXOracle.py)."""
        bins = [0.0]
        for exponent in range(-6, 6):
            for b in range(0, 200):
                bins.append(10 ** (exponent + b / 200))
        return bins

    def _create_smooth_stencil(self) -> List[float]:
        """Create smooth stencil for Step 9 (UTXOracle.py lines 1006-1009)."""
        stencil = []
        for x in range(803):
            exp_part = -((x - 411) ** 2) / (2 * (201**2))
            stencil.append((0.00150 * 2.718281828459045**exp_part) + (0.0000005 * x))
        return stencil

    def _create_spike_stencil(self) -> List[float]:
        """Create spike stencil for Step 9 (UTXOracle.py lines 1012-1046)."""
        s = [0.0] * 803
        s[40] = 0.001300198324984352
        s[141] = 0.001676746949820743
        s[201] = 0.003468805546942046
        s[202] = 0.001991977522512513
        s[236] = 0.001905066647961839
        s[261] = 0.003341772718156079
        s[262] = 0.002588902624584287
        s[296] = 0.002577893841190244
        s[297] = 0.002733728814200412
        s[340] = 0.003076117748975647
        s[341] = 0.005613067550103145
        s[342] = 0.003088253178535568
        s[400] = 0.002918457489366139
        s[401] = 0.006174500465286022
        s[402] = 0.004417068070043504
        s[403] = 0.002628663628020371
        s[436] = 0.002858828161543839
        s[461] = 0.004097463611984264
        s[462] = 0.003345917406120509
        s[496] = 0.002521467726855856
        s[497] = 0.002784125730361008
        s[541] = 0.003792850444811335
        s[601] = 0.003688240815848247
        s[602] = 0.002392400117402263
        return s

    def _load_historical_blocks(self):
        """
        T113 & T114: Load the last 144 blocks from the node to establish a baseline.
        Uses RPC `getblock` with verbosity=2.
        """
        if not self.rpc:
            logger.warning("RPC not available, skipping historical block load.")
            return

        current_height = self.rpc.ask_node("getblockcount")
        start_height = current_height - self.window_blocks + 1

        logger.info(f"Fetching blocks from {start_height} to {current_height}...")

        for height in range(start_height, current_height + 1):
            try:
                block_hash = self.rpc.ask_node("getblockhash", [height])
                # Verbosity=2 gives parsed transaction data
                block_data = self.rpc.ask_node("getblock", [block_hash, 2])
                self._process_block_transactions(block_data)
            except Exception as e:
                logger.error(f"Failed to fetch or process block {height}: {e}")
                # Continue to next block if one fails
                continue

        self.last_block_height = current_height

    def _process_block_transactions(self, block: dict):
        """
        Extracts, filters, and adds transactions from a block to the baseline.
        Filter logic from UTXOracle.py Step 6.
        """
        transactions = []
        block_time = block["time"]
        block_height = block["height"]

        for tx in block["tx"]:
            # Filter 1: Not coinbase
            is_coinbase = len(tx["vin"]) == 1 and "coinbase" in tx["vin"][0]
            if is_coinbase:
                continue

            # Filter 2: <= 5 inputs and exactly 2 outputs
            if not (len(tx["vin"]) <= 5 and len(tx["vout"]) == 2):
                continue

            # Filter 3: No OP_RETURN outputs
            has_op_return = any(
                "OP_RETURN" in vout["scriptPubKey"].get("asm", "")
                for vout in tx["vout"]
            )
            if has_op_return:
                continue

            # If filters pass, add both outputs to transactions list
            for vout in tx["vout"]:
                amount_btc = vout["value"]
                # Add transaction tuple (amount, timestamp)
                transactions.append((amount_btc, block_time))

        if transactions:
            self.add_block(transactions, block_height)
            logger.debug(
                f"Added {len(transactions)} transactions from block {block_height}"
            )

    def add_block(self, transactions: List[Tuple[float, float]], height: int):
        """Add a block with transactions to the rolling window."""
        self.blocks.append({"height": height, "transactions": transactions})
        self.last_block_height = height

    def _get_bin_index(self, amount_btc: float) -> int:
        """Find histogram bin index for given BTC amount."""
        if amount_btc <= 0:
            return 0
        # Optimized search using log10, derived from binning logic
        # bin_value = 10 ** (exponent + b/200)
        # log10(bin_value) = exponent + b/200
        # (log10(bin_value) - exponent) * 200 = b
        log_amount = math.log10(amount_btc)
        exponent = math.floor(log_amount)
        if exponent < -6:
            return 0
        if exponent >= 6:
            return len(self.histogram_bins) - 1

        b = (log_amount - exponent) * 200

        # Bin index = (exponent - (-6)) * 200 + b
        index = int((exponent + 6) * 200 + b) + 1

        return min(index, len(self.histogram_bins) - 1)

    def _apply_step7_normalize(self, histogram: List[float]) -> List[float]:
        """
        Step 7: Remove round BTC amounts and normalize histogram.
        From UTXOracle.py lines 917-965.
        """
        # Remove outputs below 10k sat (bin 0-200)
        for n in range(0, 201):
            histogram[n] = 0.0

        # Remove outputs above 10 BTC (bin 1601+)
        for n in range(1601, len(histogram)):
            histogram[n] = 0.0

        # Round BTC bin locations
        round_btc_bins = [
            201,
            401,
            461,
            496,
            540,
            601,
            661,
            696,
            740,
            801,
            861,
            896,
            940,
            1001,
            1061,
            1096,
            1140,
            1201,
        ]

        # Smooth over round BTC amounts
        for r in round_btc_bins:
            if r > 0 and r < len(histogram) - 1:
                amount_above = histogram[r + 1]
                amount_below = histogram[r - 1]
                histogram[r] = 0.5 * (amount_above + amount_below)

        # Normalize (sum bins 201-1601)
        curve_sum = sum(histogram[201:1601])
        if curve_sum == 0:
            logger.warning("Histogram sum is zero, cannot normalize")
            return histogram

        for n in range(201, 1601):
            histogram[n] /= curve_sum
            # Cap extremes at 0.008
            if histogram[n] > 0.008:
                histogram[n] = 0.008

        return histogram

    def _apply_step9_stencil_slide(
        self, histogram: List[float]
    ) -> Tuple[Optional[float], float]:
        """
        Step 9: Estimate rough price via stencil sliding.
        From UTXOracle.py lines 1073-1154.
        Returns (rough_price, confidence) or (None, 0.0) on failure.
        """
        best_slide = 0
        best_slide_score = 0.0
        total_score = 0.0

        # Stencil weighting
        smooth_weight = 0.65
        spike_weight = 1.0

        # Center slide: if zero slide, 0.001 BTC = $100 (price $100k)
        center_p001 = 601
        left_p001 = center_p001 - len(self.spike_stencil) // 2
        right_p001 = left_p001 + len(self.spike_stencil)

        # Slide range: -141 ($500k) to +201 ($5k)
        min_slide = -141
        max_slide = 201

        # Slide the stencil
        for slide in range(min_slide, max_slide):
            # Bounds check
            if left_p001 + slide < 0 or right_p001 + slide > len(histogram):
                continue

            # Extract shifted curve
            shifted_curve = histogram[left_p001 + slide : right_p001 + slide]

            if len(shifted_curve) != len(self.smooth_stencil):
                continue

            # Score smooth slide
            slide_score_smooth = sum(
                shifted_curve[n] * self.smooth_stencil[n]
                for n in range(len(self.smooth_stencil))
            )

            # Score spike slide
            slide_score = sum(
                shifted_curve[n] * self.spike_stencil[n]
                for n in range(len(self.spike_stencil))
            )

            # Add smooth score for low slides
            if slide < 150:
                slide_score += slide_score_smooth * smooth_weight

            # Track best slide
            if slide_score > best_slide_score:
                best_slide_score = slide_score
                best_slide = slide

            total_score += slide_score

        # Check if best slide found
        if total_score == 0 or best_slide_score == 0:
            logger.warning("Stencil slide failed: total_score=0")
            return None, 0.0

        # Calculate rough price from best slide
        bin_index = center_p001 + best_slide
        if bin_index < 0 or bin_index >= len(self.histogram_bins):
            logger.warning(f"Best slide bin {bin_index} out of range")
            return None, 0.0

        usd100_in_btc_best = self.histogram_bins[bin_index]
        if usd100_in_btc_best == 0:
            logger.warning("Best slide bin has zero value")
            return None, 0.0

        rough_price = 100.0 / usd100_in_btc_best

        # Calculate confidence based on score quality
        avg_score = total_score / len(range(min_slide, max_slide))
        confidence = min(1.0, (best_slide_score / avg_score - 1.0) / 2.0)
        confidence = max(0.0, confidence)

        logger.info(f"Rough price: ${rough_price:,.0f}, confidence: {confidence:.2f}")
        return rough_price, confidence

    def _generate_intraday_points(
        self, all_transactions: List[Tuple[float, float]], rough_price: float
    ) -> List[Tuple[float, float, float]]:
        """
        Generate intraday price points from raw transactions (UTXOracle Step 10).

        For each transaction, if amount matches expected BTC for common USD values
        ($5, $10, $20, $50, $100, etc.), calculate implied price = usd/btc.

        Args:
            all_transactions: List of (amount_btc, timestamp) tuples
            rough_price: Rough price estimate from Step 9

        Returns:
            List of (price, block_height, timestamp) tuples (500-2000 points expected)
        """
        # Common USD amounts (from UTXOracle.py line 1188)
        USD_AMOUNTS = [5, 10, 15, 20, 25, 30, 40, 50, 100, 150, 200, 300, 500, 1000]

        # ±25% price range for matching (line 1191)
        PCT_RANGE = 0.25

        # Generate micro-round satoshi exclusion list (lines 1194-1214)
        micro_remove_list = []

        # 5000-10000 sats range (0.00005-0.0001 BTC)
        i = 0.00005000
        while i < 0.0001:
            micro_remove_list.append(i)
            i += 0.00001

        # 10k-100k sats range (0.0001-0.001 BTC)
        i = 0.0001
        while i < 0.001:
            micro_remove_list.append(i)
            i += 0.00001

        # 100k-1M sats range (0.001-0.01 BTC)
        i = 0.001
        while i < 0.01:
            micro_remove_list.append(i)
            i += 0.0001

        # 1M-10M sats range (0.01-0.1 BTC)
        i = 0.01
        while i < 0.1:
            micro_remove_list.append(i)
            i += 0.001

        # 10M-100M sats range (0.1-1.0 BTC)
        i = 0.1
        while i < 1.0:
            micro_remove_list.append(i)
            i += 0.01

        PCT_MICRO_REMOVE = 0.0001

        output_points = []

        # Create timestamp to block height mapping
        # Sort transactions by timestamp to estimate block progression
        sorted_txs = sorted(all_transactions, key=lambda x: x[1])
        if not sorted_txs:
            return output_points

        # Estimate block heights from timestamps
        # Assuming ~10 minutes per block
        min_time = sorted_txs[0][1]
        max_time = sorted_txs[-1][1]
        time_span = max_time - min_time if max_time > min_time else 1.0

        # Map to block height range (last 144 blocks)
        start_block = (
            self.last_block_height - len(self.blocks) + 1
            if self.last_block_height
            else 0
        )

        # Loop through all outputs (line 1223)
        for amount_btc, timestamp in all_transactions:
            # Estimate fractional block height from timestamp
            time_progress = (timestamp - min_time) / time_span if time_span > 0 else 0.0
            block_height = start_block + (time_progress * len(self.blocks))

            # Try matching against each USD amount (line 1231)
            for usd in USD_AMOUNTS:
                # Calculate expected BTC range (lines 1234-1236)
                expected_btc = usd / rough_price
                btc_upper = expected_btc * (1.0 + PCT_RANGE)
                btc_lower = expected_btc * (1.0 - PCT_RANGE)

                # Check if transaction matches this USD amount (line 1239)
                if btc_lower < amount_btc < btc_upper:
                    should_append = True

                    # Exclude micro-round amounts (lines 1242-1248)
                    for round_amt in micro_remove_list:
                        rm_lower = round_amt * (1.0 - PCT_MICRO_REMOVE)
                        rm_upper = round_amt * (1.0 + PCT_MICRO_REMOVE)
                        if rm_lower < amount_btc < rm_upper:
                            should_append = False
                            break

                    # Calculate implied price (line 1252)
                    if should_append:
                        price = usd / amount_btc
                        output_points.append((price, block_height, timestamp))
                        break  # Found match for this transaction, move to next

        logger.info(
            f"Step 10: Generated {len(output_points)} intraday points from {len(all_transactions)} transactions"
        )
        return output_points

    def calculate_baseline(self) -> Optional[BaselineResult]:
        """
        Calculate baseline price using UTXOracle algorithm Steps 7-11.
        Returns None if insufficient data.
        """
        if len(self.blocks) < 10:
            logger.warning(f"Insufficient blocks for baseline: {len(self.blocks)}/144")
            return None

        # Collect all transactions from blocks
        all_transactions = []
        for block in self.blocks:
            all_transactions.extend(block["transactions"])

        if len(all_transactions) < 100:
            logger.warning(f"Insufficient transactions: {len(all_transactions)}")
            return None

        logger.info(
            f"Calculating baseline from {len(self.blocks)} blocks, {len(all_transactions)} tx"
        )

        # Step 5-6: Build histogram
        histogram = [0.0] * len(self.histogram_bins)
        for amount_btc, timestamp in all_transactions:
            bin_index = self._get_bin_index(amount_btc)
            if 0 <= bin_index < len(histogram):
                histogram[bin_index] += 1.0

        # Step 7: Remove round BTC amounts and normalize
        histogram = self._apply_step7_normalize(histogram)

        # Step 9: Stencil slide for rough price
        rough_price, confidence = self._apply_step9_stencil_slide(histogram)

        if rough_price is None:
            # Fallback: use default price if stencil slide fails (low confidence)
            logger.warning("Using fallback price $100k (stencil slide failed)")
            rough_price = 100000.0
            confidence = 0.1  # Low confidence

        # Step 11: Convergence (simplified for MVP - use rough price)
        # TODO: Full convergence algorithm for production (UTXOracle.py lines 1282-1356)
        exact_price = rough_price

        # Calculate price range (±5% for baseline)
        price_min = exact_price * 0.95
        price_max = exact_price * 1.05

        logger.info(
            f"Baseline calculated: ${exact_price:,.0f} "
            f"(range ${price_min:,.0f}-${price_max:,.0f}), "
            f"confidence {confidence:.2f}"
        )

        # Step 10: Generate intraday price points for dense visualization
        logger.info("Generating intraday price points (Step 10)...")
        intraday_points = self._generate_intraday_points(all_transactions, rough_price)
        logger.info(
            f"Generated {len(intraday_points)} intraday points for visualization"
        )

        # Sample transactions for frontend visualization (max 10k for performance)
        sampled_transactions = all_transactions
        if len(all_transactions) > 10000:
            import random

            sampled_transactions = random.sample(all_transactions, 10000)
            logger.info(
                f"Sampled {len(sampled_transactions)} transactions for visualization"
            )

        return BaselineResult(
            price=exact_price,
            price_min=price_min,
            price_max=price_max,
            confidence=confidence,
            timestamp=time.time(),
            block_height=self.last_block_height,
            num_transactions=len(all_transactions),
            transactions=sampled_transactions,
            intraday_points=intraday_points,
        )

    def get_state(self) -> dict:
        """Get current state of baseline calculator."""
        return {
            "blocks_loaded": len(self.blocks),
            "window_capacity": self.window_blocks,
            "last_block_height": self.last_block_height,
        }
