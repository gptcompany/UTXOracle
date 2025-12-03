# Task 03: Mempool Analyzer Module

**Assigned Agent**: `general-purpose`

**Duration**: 3-4 weeks

**Dependencies**: Task 02 (Transaction Processor)

---

## Objective

Implement real-time histogram updates and price estimation for mempool transactions using UTXOracle algorithm (Steps 5-11).

---

## Requirements

### Functional
1. Maintain rolling histogram of mempool tx outputs
2. Apply round BTC smoothing (Step 7)
3. Slide stencils for price estimation (Steps 8-9)
4. Iterative convergence for exact price (Step 11)
5. Handle tx additions and removals (rolling window)

### Non-Functional
1. **Latency**: Price update <500ms after new tx
2. **Memory**: <200MB for 50k active tx
3. **Accuracy**: Price within ±1% of confirmed blocks (validated historically)
4. **Dependencies**: Pure Python (reuse UTXOracle.py algorithm)

---

## Implementation Details

### File Structure
```
live/backend/
├── mempool_analyzer.py     # Main analyzer
├── histogram.py            # Histogram management (Step 5-7)
├── stencil.py              # Stencil sliding (Step 8-9)
└── convergence.py          # Price convergence (Step 11)
```

### Core Interface

```python
# live/backend/mempool_analyzer.py

from collections import deque
from typing import List, Tuple
import time
from .histogram import Histogram
from .stencil import StencilMatcher
from .convergence import PriceConvergence
from .tx_processor import ProcessedTransaction

class MempoolAnalyzer:
    """
    Real-time mempool price analyzer using UTXOracle algorithm.

    Black Box Contract:
    - Input: ProcessedTransaction stream
    - Output: Current BTC/USD price estimate
    - Side Effects: Maintains rolling histogram (in-memory)
    """

    def __init__(self, rolling_window_hours: int = 3):
        self.rolling_window_sec = rolling_window_hours * 3600
        self.tx_queue = deque(maxlen=100000)  # Max 100k tx in memory

        # Algorithm components (from UTXOracle.py)
        self.histogram = Histogram()
        self.stencil_matcher = StencilMatcher()
        self.convergence = PriceConvergence()

        # Metrics
        self.last_price_update = time.time()
        self.total_txs_processed = 0

    def add_transaction(self, tx: ProcessedTransaction) -> None:
        """
        Add transaction to rolling histogram.

        Updates histogram bins with new tx amounts.
        Removes old transactions outside rolling window.
        """
        # Add to queue
        for amount in tx.amounts:
            self.tx_queue.append((amount, tx.timestamp))
            self.histogram.add_amount(amount)

        # Remove old tx
        self._cleanup_old_transactions()

        self.total_txs_processed += 1

    def remove_transaction(self, txid: str) -> None:
        """
        Remove transaction from histogram (e.g., on RBF or block confirmation).

        Note: Requires tracking txid -> amounts mapping.
        """
        pass

    def estimate_price(self) -> Tuple[float, float]:
        """
        Estimate current BTC/USD price from mempool.

        Returns:
            (price, confidence_score)

        Process:
            1. Normalize histogram (Step 7)
            2. Slide stencils (Steps 8-9)
            3. Converge to exact price (Step 11)
        """
        # Step 7: Remove round BTC, normalize
        self.histogram.smooth_round_btc()
        self.histogram.normalize()

        # Steps 8-9: Rough price estimate
        rough_price = self.stencil_matcher.find_price(
            self.histogram.bin_counts
        )

        # Step 11: Exact price via convergence
        intraday_points = self._create_intraday_points(rough_price)
        exact_price = self.convergence.find_central_price(intraday_points)

        # Confidence score (based on data density)
        confidence = self._calculate_confidence()

        self.last_price_update = time.time()
        return exact_price, confidence

    def _cleanup_old_transactions(self) -> None:
        """Remove transactions older than rolling window"""
        now = time.time()
        cutoff = now - self.rolling_window_sec

        while self.tx_queue and self.tx_queue[0][1] < cutoff:
            old_amount, old_time = self.tx_queue.popleft()
            self.histogram.remove_amount(old_amount)

    def _create_intraday_points(self, rough_price: float) -> List[float]:
        """
        Create price points from recent tx (Step 10).

        Similar to UTXOracle.py lines 1186-1255
        """
        pass

    def _calculate_confidence(self) -> float:
        """
        Calculate confidence score [0.0, 1.0] based on:
        - Number of transactions in window
        - Histogram density
        - Price convergence stability
        """
        pass

    def get_stats(self) -> dict:
        """Return analyzer statistics"""
        return {
            'total_txs_processed': self.total_txs_processed,
            'active_txs_in_window': len(self.tx_queue),
            'last_price_update': self.last_price_update,
            'rolling_window_hours': self.rolling_window_sec / 3600
        }
```

### Histogram Module

```python
# live/backend/histogram.py

"""
Histogram management from UTXOracle.py Steps 5-7.

Maintains logarithmic bins and counts for BTC amounts.
"""

from math import log10
from typing import List

class Histogram:
    """
    Logarithmic histogram for BTC amounts.

    Copied from UTXOracle.py lines 620-641 (Step 5)
    """

    def __init__(self):
        self.bins = self._create_bins()
        self.bin_counts = [0.0] * len(self.bins)

        # UTXOracle parameters
        self.first_bin_value = -6  # 10^-6 BTC (100 sats)
        self.last_bin_value = 6    # 10^6 BTC
        self.range_bin_values = 12
        self.round_btc_bins = [201, 401, 461, ...]  # From line 926

    def _create_bins(self) -> List[float]:
        """
        Create logarithmic bins.

        From UTXOracle.py lines 625-635
        """
        bins = [0.0]
        for exponent in range(-6, 6):
            for b in range(0, 200):
                bin_value = 10 ** (exponent + b/200)
                bins.append(bin_value)
        return bins

    def add_amount(self, amount: float) -> None:
        """Add BTC amount to histogram"""
        bin_idx = self._find_bin(amount)
        if bin_idx is not None:
            self.bin_counts[bin_idx] += 1.0

    def remove_amount(self, amount: float) -> None:
        """Remove BTC amount from histogram (for rolling window)"""
        bin_idx = self._find_bin(amount)
        if bin_idx is not None:
            self.bin_counts[bin_idx] = max(0, self.bin_counts[bin_idx] - 1.0)

    def _find_bin(self, amount: float) -> int:
        """
        Find bin index for BTC amount.

        From UTXOracle.py lines 866-871
        """
        if not (1e-5 < amount < 1e5):
            return None

        amount_log = log10(amount)
        percent_in_range = (amount_log - self.first_bin_value) / self.range_bin_values
        bin_number_est = int(percent_in_range * len(self.bins))

        # Binary search for exact bin
        while bin_number_est < len(self.bins) and self.bins[bin_number_est] <= amount:
            bin_number_est += 1

        return bin_number_est - 1

    def smooth_round_btc(self) -> None:
        """
        Smooth histogram bins at round BTC amounts (Step 7).

        From UTXOracle.py lines 947-951
        """
        for r in self.round_btc_bins:
            if r >= len(self.bin_counts):
                continue
            amount_above = self.bin_counts[r+1]
            amount_below = self.bin_counts[r-1]
            self.bin_counts[r] = 0.5 * (amount_above + amount_below)

    def normalize(self) -> None:
        """
        Normalize histogram to percentages (Step 7).

        From UTXOracle.py lines 953-964
        """
        # Sum non-zero bins
        curve_sum = sum(self.bin_counts[201:1601])

        if curve_sum == 0:
            return  # Empty histogram

        # Normalize and cap extremes
        for n in range(201, 1601):
            self.bin_counts[n] /= curve_sum
            if self.bin_counts[n] > 0.008:
                self.bin_counts[n] = 0.008
```

### Stencil Matcher

```python
# live/backend/stencil.py

"""
Stencil sliding for price estimation (Steps 8-9).

From UTXOracle.py lines 1000-1154
"""

class StencilMatcher:
    """Find best price fit by sliding stencils across histogram"""

    def __init__(self):
        self.smooth_stencil = self._create_smooth_stencil()
        self.spike_stencil = self._create_spike_stencil()

    def _create_smooth_stencil(self) -> List[float]:
        """
        Gaussian stencil for coarse price estimate.

        From UTXOracle.py lines 1005-1009
        """
        num_elements = 803
        mean = 411
        std_dev = 201

        stencil = []
        for x in range(num_elements):
            exp_part = -((x - mean) ** 2) / (2 * (std_dev ** 2))
            stencil.append((0.00150 * 2.718281828459045 ** exp_part) + (0.0000005 * x))

        return stencil

    def _create_spike_stencil(self) -> List[float]:
        """
        Spike stencil for fine price tuning.

        From UTXOracle.py lines 1012-1046 (hard-coded weights)
        """
        stencil = [0.0] * 803

        # Round USD amounts (from historical testing)
        stencil[40] = 0.001300198324984352   # $1
        stencil[141] = 0.001676746949820743  # $5
        stencil[201] = 0.003468805546942046  # $10
        stencil[401] = 0.006174500465286022  # $100 (highest weight)
        # ... (all values from UTXOracle.py)

        return stencil

    def find_price(self, histogram_bins: List[float]) -> float:
        """
        Slide stencils to find best price fit.

        From UTXOracle.py lines 1074-1153
        """
        best_slide = 0
        best_slide_score = 0.0

        # Slide parameters
        center_p001 = 601
        min_slide = -141  # $500k
        max_slide = 201   # $5k

        left_p001 = center_p001 - int((len(self.spike_stencil) + 1) / 2)
        right_p001 = center_p001 + int((len(self.spike_stencil) + 1) / 2)

        # Slide and score
        for slide in range(min_slide, max_slide):
            shifted_curve = histogram_bins[left_p001+slide:right_p001+slide]

            # Score smooth stencil
            slide_score_smooth = sum(
                shifted_curve[n] * self.smooth_stencil[n]
                for n in range(len(self.smooth_stencil))
            )

            # Score spike stencil
            slide_score_spike = sum(
                shifted_curve[n] * self.spike_stencil[n]
                for n in range(len(self.spike_stencil))
            )

            # Combined score
            slide_score = slide_score_spike + slide_score_smooth * 0.65

            if slide_score > best_slide_score:
                best_slide_score = slide_score
                best_slide = slide

        # Calculate price from best slide
        # (implementation from UTXOracle.py lines 1121-1153)
        ...

        return rough_price
```

### Convergence Module

```python
# live/backend/convergence.py

"""
Iterative price convergence (Step 11).

From UTXOracle.py lines 1282-1368
"""

class PriceConvergence:
    """Find exact price via geometric median"""

    def find_central_price(self, price_points: List[float]) -> float:
        """
        Iteratively converge to central price.

        From UTXOracle.py lines 1325-1344
        """
        pct_range_tight = 0.05
        rough_estimate = sum(price_points) / len(price_points)

        price_up = rough_estimate * (1 + pct_range_tight)
        price_dn = rough_estimate * (1 - pct_range_tight)

        central_price, _ = self._find_central_output(price_points, price_dn, price_up)

        # Iterative convergence
        seen_prices = set([central_price])
        while central_price not in seen_prices:
            seen_prices.add(central_price)
            price_up = central_price * (1 + pct_range_tight)
            price_dn = central_price * (1 - pct_range_tight)
            central_price, _ = self._find_central_output(price_points, price_dn, price_up)

        return central_price

    def _find_central_output(self, prices: List[float], price_min: float, price_max: float) -> Tuple[float, float]:
        """
        Find geometric median (minimum total distance).

        From UTXOracle.py lines 1283-1322
        """
        # Filter and sort
        filtered = [p for p in prices if price_min < p < price_max]
        if not filtered:
            return (price_min + price_max) / 2, 0.0

        outputs = sorted(filtered)
        n = len(outputs)

        # Prefix sums for efficient distance calculation
        prefix_sum = []
        total = 0
        for x in outputs:
            total += x
            prefix_sum.append(total)

        # Find minimum total distance
        min_index = 0
        min_dist = float('inf')

        for i in range(n):
            left_sum = prefix_sum[i-1] if i > 0 else 0
            right_sum = total - prefix_sum[i]

            left_count = i
            right_count = n - i - 1

            dist = (outputs[i] * left_count - left_sum) + (right_sum - outputs[i] * right_count)

            if dist < min_dist:
                min_dist = dist
                min_index = i

        best_output = outputs[min_index]

        # Median absolute deviation
        deviations = sorted([abs(x - best_output) for x in outputs])
        m = len(deviations)
        mad = deviations[m//2] if m % 2 == 1 else (deviations[m//2-1] + deviations[m//2]) / 2

        return best_output, mad
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_mempool_analyzer.py

def test_histogram_add_remove():
    """Test rolling window histogram updates"""
    hist = Histogram()

    # Add amounts
    hist.add_amount(0.01)
    hist.add_amount(0.01)
    assert hist.bin_counts[hist._find_bin(0.01)] == 2.0

    # Remove amount
    hist.remove_amount(0.01)
    assert hist.bin_counts[hist._find_bin(0.01)] == 1.0

def test_stencil_price_estimation():
    """Test stencil sliding returns reasonable price"""
    matcher = StencilMatcher()

    # Mock histogram (simulated $100k BTC)
    histogram = [0.0] * 2400
    # Populate histogram around $100k price level
    for i in range(500, 700):
        histogram[i] = 0.005

    price = matcher.find_price(histogram)

    assert 50000 < price < 200000  # Reasonable range

def test_full_analyzer_pipeline():
    """Test end-to-end analysis"""
    analyzer = MempoolAnalyzer(rolling_window_hours=1)

    # Add 1000 sample transactions
    for i in range(1000):
        tx = ProcessedTransaction(
            txid=f"tx{i}",
            amounts=[0.001 + i*0.0001],
            timestamp=time.time(),
            fee_rate=10.0,
            input_count=2,
            output_count=2
        )
        analyzer.add_transaction(tx)

    # Estimate price
    price, confidence = analyzer.estimate_price()

    assert price > 0
    assert 0 <= confidence <= 1.0
```

---

## Deliverables

- [ ] `live/backend/mempool_analyzer.py`
- [ ] `live/backend/histogram.py`
- [ ] `live/backend/stencil.py`
- [ ] `live/backend/convergence.py`
- [ ] Unit tests (>85% coverage)
- [ ] Historical validation (compare mempool vs confirmed prices)

---

## Acceptance Criteria

✅ **Must Have**:
1. Rolling histogram updates in real-time
2. Price estimate within ±2% of confirmed blocks (historical validation)
3. Processes 1000 tx additions/removals per second
4. Memory <200MB for 50k active tx

✅ **Should Have**:
1. Confidence score reflects data quality
2. Graceful handling of empty mempool
3. Metrics for monitoring

---

**Status**: NOT STARTED
**Dependencies**: Task 02 complete
**Target Completion**: __________ (4 weeks from Task 02 completion)
