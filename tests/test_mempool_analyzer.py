"""
Tests for Mempool Analyzer (Module 3)

TDD Phase: RED - All tests must FAIL initially

Tasks:
- T024 [P]: test_histogram_add_transaction
- T025 [P]: test_estimate_price_from_histogram
"""

import pytest
import time
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.shared.models import ProcessedTransaction, MempoolState, calculate_confidence


# =============================================================================
# T084: Stats Collection Accuracy Test (User Story 4)
# =============================================================================


def test_get_stats_accuracy():
    """
    Test that MempoolAnalyzer.get_state() returns accurate statistics.

    Requirements (User Story 4):
    - total_received: Total transactions received since startup
    - total_filtered: Total transactions filtered out (not meeting UTXOracle criteria)
    - active_tx_count: Current transactions in rolling window
    - uptime_seconds: Time since analyzer started
    - All stats must be accurate and non-negative

    Contract:
        MempoolAnalyzer.get_state() -> MempoolState
        MempoolState contains: total_received, total_filtered, active_tx_count, uptime_seconds

    Task: T084 [US4]
    """
    # Arrange: Create analyzer and track start time
    start_time = time.time()
    analyzer = MempoolAnalyzer(window_hours=3)

    # Act: Add some transactions
    tx1 = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=time.time(),
        input_count=2,
        output_count=2,
    )
    tx2 = ProcessedTransaction(
        txid="b" * 64,
        amounts=[0.005, 0.010],
        timestamp=time.time(),
        input_count=1,
        output_count=2,
    )
    tx3 = ProcessedTransaction(
        txid="c" * 64,
        amounts=[0.100, 0.050],
        timestamp=time.time(),
        input_count=3,
        output_count=2,
    )

    analyzer.add_transaction(tx1)
    analyzer.add_transaction(tx2)
    analyzer.add_transaction(tx3)

    # Get state
    state = analyzer.get_state()

    # Assert: Stats are accurate
    assert state.total_received == 3, "Should track total_received correctly"
    assert state.active_tx_count == 3, "Should have 3 active transactions in window"
    assert state.uptime_seconds >= 0, "Uptime must be non-negative"
    assert state.uptime_seconds <= (time.time() - start_time + 1), (
        "Uptime must be reasonable"
    )

    # Assert: Stats are internally consistent
    assert state.total_received >= state.active_tx_count, (
        "total_received must be >= active_tx_count"
    )
    assert state.total_received >= state.total_filtered, (
        "total_received must be >= total_filtered"
    )
    assert state.total_filtered >= 0, "total_filtered must be non-negative"

    # Assert: Additional fields present
    assert state.price > 0, "Price must be positive"
    assert 0.0 <= state.confidence <= 1.0, "Confidence must be in [0, 1]"


# Keep existing tests below...


# =============================================================================
# T024: Histogram Operations Test
# =============================================================================


def test_histogram_add_transaction():
    """
    Test that MempoolAnalyzer adds transactions to rolling histogram correctly.

    Requirements (from UTXOracle.py Steps 5-7):
    - Initialize histogram with price range [0, 200000] USD
    - Use 10,000 bins for precision
    - Add transaction amounts to histogram bins based on estimated price
    - Weight transactions by BTC amount (not just count)
    - Maintain 3-hour rolling window (remove old transactions)

    Contract:
        MempoolAnalyzer.add_transaction(tx: ProcessedTransaction) -> None
        MempoolAnalyzer.get_histogram_bin_count() -> int
    """
    # Arrange: Create analyzer
    analyzer = MempoolAnalyzer(window_hours=3)

    # Create sample transactions
    tx1 = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],  # 2 outputs
        timestamp=time.time(),
        input_count=2,
        output_count=2,
    )

    tx2 = ProcessedTransaction(
        txid="b" * 64,
        amounts=[0.005, 0.010],
        timestamp=time.time(),
        input_count=1,
        output_count=2,
    )

    # Act: Add transactions to histogram
    analyzer.add_transaction(tx1)
    analyzer.add_transaction(tx2)

    # Assert: Transactions were added
    assert analyzer.get_transaction_count() == 2, "Should have 2 transactions"

    # Assert: Histogram has non-zero bins
    histogram_data = analyzer.get_histogram_data()
    assert len(histogram_data) > 0, "Histogram should have data"

    # Assert: Total BTC amount tracked
    total_btc = sum(tx1.amounts) + sum(
        tx2.amounts
    )  # 0.001 + 0.002 + 0.005 + 0.010 = 0.018
    assert abs(analyzer.get_total_btc_tracked() - total_btc) < 1e-8, (
        "Should track total BTC correctly"
    )


def test_histogram_rolling_window():
    """
    Test that histogram maintains 3-hour rolling window.

    Requirements:
    - Only keep transactions from last 3 hours
    - Automatically remove transactions older than 3 hours
    - Update active_tx_count accordingly

    Contract:
        MempoolAnalyzer maintains transactions within window_hours
    """
    # Arrange: Create analyzer with 1-hour window (for faster testing)
    analyzer = MempoolAnalyzer(window_hours=1)

    current_time = time.time()

    # Add transaction from 30 minutes ago (should be kept)
    tx_recent = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=current_time - 1800,  # 30 minutes ago
        input_count=1,
        output_count=2,
    )

    # Add transaction from 2 hours ago (should be removed)
    tx_old = ProcessedTransaction(
        txid="b" * 64,
        amounts=[0.005, 0.010],
        timestamp=current_time - 7200,  # 2 hours ago
        input_count=1,
        output_count=2,
    )

    # Act: Add both transactions
    analyzer.add_transaction(tx_recent)
    analyzer.add_transaction(tx_old)

    # Trigger cleanup (normally done automatically)
    analyzer.cleanup_old_transactions(current_time)

    # Assert: Only recent transaction remains
    assert analyzer.get_transaction_count() == 1, (
        "Should only have 1 transaction (recent one)"
    )

    # Get state to verify active count
    state = analyzer.get_state()
    assert state.active_tx_count == 1, "active_tx_count should be 1"


def test_histogram_bin_distribution():
    """
    Test that transactions are distributed across histogram bins correctly.

    Requirements:
    - Map USD amounts to correct bin indices
    - Use logarithmic or linear binning as per UTXOracle algorithm
    - Bin index calculation: bin = floor((price / max_price) * num_bins)

    Contract: Histogram bins contain correct transaction counts/weights
    """
    # Arrange: Create analyzer
    analyzer = MempoolAnalyzer()

    # Add transactions with known amounts
    # If we assume rough price of $100,000/BTC:
    # 0.001 BTC = ~$100
    # 0.010 BTC = ~$1000
    # 0.100 BTC = ~$10,000

    txs = [
        ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001 * (i + 1), 0.002 * (i + 1)],
            timestamp=time.time(),
            input_count=1,
            output_count=2,
        )
        for i in range(10)
    ]

    # Act: Add all transactions
    for tx in txs:
        analyzer.add_transaction(tx)

    # Assert: Histogram has bins populated
    histogram = analyzer.get_histogram_data()
    assert len(histogram) > 0, "Histogram should have populated bins"

    # Assert: Bins are within valid range [0, num_bins)
    num_bins = analyzer.get_num_bins()
    for bin_index in histogram.keys():
        assert 0 <= bin_index < num_bins, (
            f"Bin index {bin_index} should be in range [0, {num_bins})"
        )


# =============================================================================
# T025: Price Estimation Test
# =============================================================================


def test_estimate_price_from_histogram():
    """
    Test that MempoolAnalyzer estimates BTC/USD price from histogram.

    Requirements (from UTXOracle.py Steps 8-11):
    - Use "Price Finding Stencil" statistical clustering
    - Find peak in histogram representing most common price
    - Calculate volume-weighted median price
    - Return confidence score based on transaction count and distribution

    Contract:
        MempoolAnalyzer.estimate_price() -> float
        MempoolAnalyzer.get_state() -> MempoolState
    """
    # Arrange: Create analyzer and add transactions
    analyzer = MempoolAnalyzer()

    # Add transactions simulating market activity around $110,000/BTC
    # We'll add transactions with amounts that imply this price
    current_time = time.time()

    # Simulate 100 transactions
    for i in range(100):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001 + i * 0.0001, 0.002 + i * 0.0001],
            timestamp=current_time - i * 10,  # Spread over last 1000 seconds
            input_count=min(i % 5 + 1, 5),  # 1-5 inputs
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Act: Estimate price
    estimated_price = analyzer.estimate_price()

    # Assert: Price is positive and in reasonable range
    assert estimated_price > 0, "Price must be positive"
    assert 10000 <= estimated_price <= 200000, (
        "Price should be in reasonable range [$10k, $200k]"
    )

    # Get full state
    state = analyzer.get_state()

    # Assert: State has correct data
    assert isinstance(state, MempoolState)
    assert state.price == estimated_price
    assert 0.0 <= state.confidence <= 1.0, "Confidence must be in [0.0, 1.0]"
    assert state.active_tx_count == 100, "Should have 100 active transactions"


def test_price_estimation_confidence_levels():
    """
    Test that confidence score increases with more transactions.

    Confidence Rules (from data-model.md):
    - 0-100 tx: Low confidence (0.0-0.3)
    - 100-1000 tx: Medium confidence (0.3-0.8)
    - 1000+ tx: High confidence (0.8-1.0)

    Contract: MempoolState.confidence follows defined rules
    """
    # Test using calculate_confidence helper function

    # Low confidence range
    assert 0.0 <= calculate_confidence(0) <= 0.3
    assert 0.0 <= calculate_confidence(50) <= 0.3
    assert 0.0 <= calculate_confidence(99) <= 0.3

    # Medium confidence range
    assert 0.3 <= calculate_confidence(100) <= 0.8
    assert 0.3 <= calculate_confidence(500) <= 0.8
    assert 0.3 <= calculate_confidence(999) <= 0.8

    # High confidence range
    assert 0.8 <= calculate_confidence(1000) <= 1.0
    assert 0.8 <= calculate_confidence(5000) <= 1.0
    assert 0.8 <= calculate_confidence(10000) <= 1.0

    # Test with analyzer
    analyzer = MempoolAnalyzer()

    # Add 50 transactions (low confidence)
    for i in range(50):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=time.time(),
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    state = analyzer.get_state()
    assert 0.0 <= state.confidence <= 0.3, "50 tx should give low confidence"


def test_price_estimation_with_sparse_data():
    """
    Test price estimation behavior with very few transactions.

    Requirements:
    - Should still return price estimate even with <10 transactions
    - Confidence should be very low (<0.1)
    - Should not crash or return invalid price

    Contract: Estimator handles edge cases gracefully
    """
    # Arrange: Analyzer with only 3 transactions
    analyzer = MempoolAnalyzer()

    for i in range(3):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=time.time(),
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Act: Get state
    state = analyzer.get_state()

    # Assert: Price is valid but confidence is very low
    assert state.price > 0, "Should return positive price even with sparse data"
    assert state.confidence < 0.1, (
        "Confidence should be very low with only 3 transactions"
    )
    assert state.active_tx_count == 3


def test_price_estimation_convergence():
    """
    Test that price estimate converges as more transactions are added.

    Requirements:
    - Price estimate should stabilize with more data
    - Variance should decrease as transaction count increases
    - Final price should be within 5% of true market price (if we had reference)

    Contract: Price estimate becomes more stable with more data
    """
    # Arrange: Analyzer
    analyzer = MempoolAnalyzer()

    # Track price estimates as we add transactions
    price_history = []

    # Add transactions in batches
    for batch in range(10):
        # Add 50 transactions per batch
        for i in range(50):
            tx = ProcessedTransaction(
                txid=f"{batch:01x}{i:063x}",
                amounts=[0.001, 0.002],
                timestamp=time.time(),
                input_count=1,
                output_count=2,
            )
            analyzer.add_transaction(tx)

        # Record price after each batch
        price = analyzer.estimate_price()
        price_history.append(price)

    # Assert: Price estimates exist
    assert len(price_history) == 10, "Should have 10 price estimates"

    # Calculate variance of early vs late estimates
    early_variance = max(price_history[:3]) - min(price_history[:3])
    late_variance = max(price_history[-3:]) - min(price_history[-3:])

    # Late estimates should be more stable (lower variance)
    # This is a heuristic - actual convergence depends on algorithm
    assert late_variance <= early_variance * 2, (
        "Price should converge (variance decrease)"
    )


def test_get_state_returns_complete_mempool_state():
    """
    Test that get_state() returns complete MempoolState with all fields.

    Requirements:
    - price: Current estimate
    - confidence: Based on transaction count
    - active_tx_count: Transactions in window
    - total_received: All transactions since startup
    - total_filtered: Transactions that were filtered out (should be 0 in analyzer)
    - uptime_seconds: Time since analyzer started

    Contract: MempoolState has all required fields validated
    """
    # Arrange: Create analyzer
    analyzer = MempoolAnalyzer()
    start_time = time.time()

    # Add some transactions
    for i in range(25):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=time.time(),
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Wait a bit to test uptime
    time.sleep(0.1)

    # Act: Get state
    state = analyzer.get_state()

    # Assert: All fields present and valid
    assert isinstance(state, MempoolState)
    assert state.price > 0
    assert 0.0 <= state.confidence <= 1.0
    assert state.active_tx_count == 25
    assert state.total_received == 25
    assert state.total_filtered == 0  # Analyzer receives pre-filtered transactions
    assert state.uptime_seconds > 0.1  # At least our sleep time
    assert state.uptime_seconds < (time.time() - start_time) + 1  # Reasonable uptime

    # Validate MempoolState constraints (from models.py)
    # These will raise ValueError if invalid
    try:
        # This should not raise
        _ = MempoolState(
            price=state.price,
            confidence=state.confidence,
            active_tx_count=state.active_tx_count,
            total_received=state.total_received,
            total_filtered=state.total_filtered,
            uptime_seconds=state.uptime_seconds,
        )
    except ValueError as e:
        pytest.fail(f"MempoolState validation failed: {e}")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_processed_transactions():
    """Sample processed transactions for testing"""
    current_time = time.time()
    return [
        ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001 + i * 0.0001, 0.002 + i * 0.0001],
            timestamp=current_time - i * 10,
            input_count=min(i % 5 + 1, 5),
            output_count=2,
        )
        for i in range(20)
    ]


@pytest.fixture
def analyzer_with_data():
    """MempoolAnalyzer pre-populated with test data"""
    analyzer = MempoolAnalyzer()
    current_time = time.time()

    for i in range(100):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=current_time - i * 10,
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    return analyzer


# =============================================================================
# T067: Transaction History Test (User Story 2)
# =============================================================================


def test_transaction_history_buffer():
    """
    Test that MempoolAnalyzer maintains transaction history buffer for visualization.

    Requirements (User Story 2 - T067):
    - Store last 300-500 transaction points (timestamp, price)
    - History is limited to 500 points (Canvas performance)
    - Points are ordered by timestamp (ascending)
    - Each point includes timestamp and estimated price at that moment
    - History is accessible via get_transaction_history() method

    Contract:
        MempoolAnalyzer.get_transaction_history() -> List[Tuple[float, float]]
        Returns: [(timestamp1, price1), (timestamp2, price2), ...]

    Task: T067 [US2]
    """
    # Arrange: Create analyzer
    analyzer = MempoolAnalyzer()
    current_time = time.time()

    # Act: Add transactions and track history
    for i in range(10):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=current_time + i,  # Increasing timestamps
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Assert: History exists and has correct structure
    history = analyzer.get_transaction_history()

    assert isinstance(history, list), "History should be a list"
    assert len(history) > 0, "History should have entries after adding transactions"
    assert len(history) <= 500, "History should not exceed 500 entries (Canvas limit)"

    # Assert: Each entry has timestamp and price
    for entry in history:
        assert isinstance(entry, tuple), "Each entry should be a tuple"
        assert len(entry) == 2, "Each entry should have (timestamp, price)"
        timestamp, price = entry
        assert isinstance(timestamp, float), "Timestamp should be float"
        assert isinstance(price, (int, float)), "Price should be numeric"
        assert timestamp > 0, "Timestamp should be positive"
        assert price > 0, "Price should be positive"

    # Assert: History is ordered by timestamp (ascending - oldest first)
    timestamps = [entry[0] for entry in history]
    assert timestamps == sorted(timestamps), (
        "History should be ordered by timestamp (oldest first)"
    )


# =============================================================================
# T075: Confidence Score Ranges Test (User Story 3)
# =============================================================================


def test_confidence_score_ranges():
    """
    Test confidence score calculation follows spec ranges.

    Spec (from spec.md User Story 3):
    - 0-100 tx: confidence 0.0-0.3 (Low)
    - 100-1000 tx: confidence 0.3-0.8 (Medium)
    - 1000+ tx: confidence 0.8-1.0 (High)

    Task: T075 [US3]
    """
    # Low confidence: <100 transactions
    assert calculate_confidence(0) < 0.3, "0 tx should be < 0.3"
    assert calculate_confidence(50) < 0.3, "50 tx should be < 0.3"
    assert calculate_confidence(99) < 0.3, "99 tx should be < 0.3"

    # Medium confidence: 100-1000 transactions
    assert 0.3 <= calculate_confidence(100) < 0.8, "100 tx should be 0.3-0.8"
    assert 0.3 <= calculate_confidence(500) < 0.8, "500 tx should be 0.3-0.8"
    assert 0.3 <= calculate_confidence(999) < 0.8, "999 tx should be 0.3-0.8"

    # High confidence: 1000+ transactions
    assert calculate_confidence(1000) >= 0.8, "1000 tx should be >= 0.8"
    assert calculate_confidence(5000) >= 0.8, "5000 tx should be >= 0.8"
    assert calculate_confidence(10000) >= 0.8, "10000 tx should be >= 0.8"

    # Additional validation: should never exceed 1.0
    assert calculate_confidence(100000) <= 1.0, "Should never exceed 1.0"


def test_set_baseline():
    """Test MempoolAnalyzer can receive baseline reference (T103)"""
    from live.backend.baseline_calculator import BaselineResult

    analyzer = MempoolAnalyzer()
    baseline = BaselineResult(
        price=113600.0,
        price_min=113000.0,
        price_max=114200.0,
        confidence=0.95,
        timestamp=time.time(),
        block_height=800000,
        num_transactions=5000,
    )
    analyzer.set_baseline(baseline)
    assert analyzer.baseline is not None
    assert analyzer.baseline.price == 113600.0


def test_estimate_price_uses_baseline():
    """Test estimate_price() uses baseline when <10 transactions (T104)"""
    from live.backend.baseline_calculator import BaselineResult

    analyzer = MempoolAnalyzer()

    # Set baseline first
    baseline = BaselineResult(
        price=113600.0,
        price_min=113000.0,
        price_max=114200.0,
        confidence=0.95,
        timestamp=time.time(),
        block_height=800000,
        num_transactions=5000,
    )
    analyzer.set_baseline(baseline)

    # Add only 5 transactions (<10 threshold)
    for i in range(5):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=time.time(),
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Act: Estimate price with <10 transactions
    estimated_price = analyzer.estimate_price()

    # Assert: Should use baseline price (113600.0) instead of fallback (100000.0)
    assert estimated_price == 113600.0, (
        f"Expected baseline price 113600.0, got {estimated_price}"
    )


def test_get_combined_history():
    """Test get_combined_history() returns baseline + mempool data (T105)"""
    from live.backend.baseline_calculator import BaselineResult

    analyzer = MempoolAnalyzer()

    # Set baseline
    baseline = BaselineResult(
        price=113600.0,
        price_min=113000.0,
        price_max=114200.0,
        confidence=0.95,
        timestamp=time.time(),
        block_height=800000,
        num_transactions=5000,
    )
    analyzer.set_baseline(baseline)

    # Add some transactions to create mempool history
    for i in range(10):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",
            amounts=[0.001, 0.002],
            timestamp=time.time() + i,
            input_count=1,
            output_count=2,
        )
        analyzer.add_transaction(tx)

    # Act: Get combined history
    combined = analyzer.get_combined_history()

    # Assert: Dictionary structure
    assert isinstance(combined, dict), "Should return a dictionary"
    assert "baseline" in combined, "Should have 'baseline' key"
    assert "mempool" in combined, "Should have 'mempool' key"

    # Assert: Baseline data
    assert combined["baseline"] is not None, "Baseline should not be None"
    assert combined["baseline"].price == 113600.0, "Should return correct baseline"

    # Assert: Mempool data
    assert isinstance(combined["mempool"], list), "Mempool should be a list"
    assert len(combined["mempool"]) == 10, "Should have 10 transaction history entries"

    # Assert: Mempool data structure (same as get_transaction_history)
    for entry in combined["mempool"]:
        assert isinstance(entry, tuple), "Each entry should be a tuple"
        assert len(entry) == 2, "Each entry should have (timestamp, price)"
