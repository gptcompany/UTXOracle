"""
Benchmark test for histogram binning performance.

Target: <100ms for 10k bins with 1000 transactions
"""

import time
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.shared.models import ProcessedTransaction


def test_histogram_binning_performance():
    """
    Test histogram add_transaction performance.

    REQUIREMENT: Must complete 1000 transactions in <100ms for 10k bins.
    """
    # Arrange: Create analyzer with 10k bins
    analyzer = MempoolAnalyzer()

    # Create 1000 test transactions with current timestamps (avoid rolling window expiration)
    base_time = time.time()
    transactions = []
    for i in range(1000):
        tx = ProcessedTransaction(
            txid=f"{i:064x}",  # Unique TXIDs
            amounts=[0.001 * (i + 1), 0.002 * (i + 1)],
            timestamp=base_time + i,
            input_count=2,
            output_count=2,
        )
        transactions.append(tx)

    # Act: Time histogram updates
    start_time = time.perf_counter()

    for tx in transactions:
        analyzer.add_transaction(tx)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Assert: Must be <100ms
    assert elapsed_ms < 100.0, (
        f"Histogram binning took {elapsed_ms:.2f}ms for 1000 transactions "
        f"(target: <100ms). Performance regression detected!"
    )

    # Additional check: verify transactions were added
    state = analyzer.get_state()
    assert state.active_tx_count == 1000, "All transactions should be tracked"
