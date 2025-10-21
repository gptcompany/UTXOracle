"""
Benchmark tests for Transaction Processor (Module 2)

Validates T060: Processing throughput must exceed 1000 tx/sec
"""

import time
import pytest
from pathlib import Path

# Import the transaction processor
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from live.backend.tx_processor import TransactionProcessor
from live.shared.models import RawTransaction


@pytest.fixture
def sample_transaction_bytes():
    """Load sample Bitcoin transaction binary data"""
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    sample_tx_path = fixtures_dir / "sample_tx.bin"

    if not sample_tx_path.exists():
        # Create a minimal valid Bitcoin transaction if fixture doesn't exist
        pytest.skip("sample_tx.bin fixture not found")

    with open(sample_tx_path, "rb") as f:
        return f.read()


@pytest.fixture
def tx_processor():
    """Create a TransactionProcessor instance"""
    return TransactionProcessor()


def test_transaction_processing_throughput(tx_processor, sample_transaction_bytes):
    """
    Test transaction processing throughput.

    Target: >1000 tx/sec
    Specification: T060 requirement
    """
    # Number of transactions to process
    num_transactions = 10_000

    # Create RawTransaction objects
    raw_txs = [
        RawTransaction(
            raw_bytes=sample_transaction_bytes, timestamp=time.time(), topic="rawtx"
        )
        for _ in range(num_transactions)
    ]

    # Benchmark: Process all transactions
    start = time.perf_counter()
    successful = 0
    failed = 0

    for raw_tx in raw_txs:
        try:
            result = tx_processor.process_mempool_transaction(raw_tx)
            if result is not None:
                successful += 1
            else:
                # Transaction was filtered out (this is OK)
                pass
        except Exception:
            failed += 1

    elapsed = time.perf_counter() - start

    # Calculate throughput
    throughput = num_transactions / elapsed

    # Print results
    print(f"\n{'=' * 60}")
    print("Transaction Processing Benchmark")
    print(f"{'=' * 60}")
    print(f"Total transactions:     {num_transactions:,}")
    print(f"Successful processing:  {successful:,}")
    print(f"Failed:                 {failed:,}")
    print(f"Elapsed time:           {elapsed:.3f} seconds")
    print(f"Throughput:             {throughput:.1f} tx/sec")
    print("Target:                 1,000 tx/sec")
    print(f"Status:                 {'✅ PASS' if throughput >= 1000 else '❌ FAIL'}")
    print(f"{'=' * 60}\n")

    # Assert throughput meets requirement
    assert throughput >= 1000, (
        f"Processing throughput is {throughput:.1f} tx/sec, "
        f"which is below the required 1000 tx/sec"
    )


if __name__ == "__main__":
    # Allow running benchmark directly
    pytest.main([__file__, "-v", "-s"])
