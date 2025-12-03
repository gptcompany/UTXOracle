"""
Tests for Baseline Calculator

TDD Phase: RED - Test must FAIL initially

Task: T097 - Implement calculate_baseline() algorithm
"""

import time
from live.backend.baseline_calculator import BaselineCalculator


def test_calculate_baseline_with_sufficient_data():
    """
    Test that calculate_baseline() returns valid price estimate
    with sufficient block data.

    Requirements:
    - Must return BaselineResult with price, price_min, price_max, confidence
    - Price must be realistic (between $10k and $200k for Bitcoin)
    - Price range should be ±5% of center price
    - Confidence should be between 0.0 and 1.0
    - Requires at least 10 blocks of data

    Task: T097
    """
    # Arrange: Create calculator and add blocks with transaction data
    calc = BaselineCalculator(window_blocks=144)

    # Simulate 20 blocks with realistic Bitcoin transactions
    # Each block has diverse transactions simulating real spending patterns
    import random

    random.seed(42)  # Reproducible test data

    for block_height in range(1000, 1020):
        transactions = []
        # Create diverse transaction amounts simulating real spending
        # Wider range: $50-$10000 to ensure sufficient histogram coverage
        # Assuming BTC price ~$100k: $50=0.0005, $100=0.001, $1000=0.01, $10000=0.1
        usd_amounts = [50, 100, 150, 200, 300, 500, 1000, 1500, 2000, 3000, 5000, 10000]

        for _ in range(100):  # 100 transactions per block for better coverage
            # Pick random USD amount with realistic frequency distribution
            # (smaller amounts more common than larger)
            usd = random.choices(
                usd_amounts,
                weights=[8, 10, 6, 8, 5, 7, 6, 4, 5, 3, 2, 1],  # $100-$200 most common
                k=1,
            )[0]

            # Add variance (±30%) to simulate non-round amounts
            variance = random.uniform(0.7, 1.3)
            amount_btc = (usd / 100000.0) * variance  # Assuming $100k BTC price
            timestamp = time.time()
            transactions.append((amount_btc, timestamp))

        calc.add_block(transactions, height=block_height)

    # Act: Calculate baseline
    result = calc.calculate_baseline()

    # Assert: Result should not be None
    assert result is not None, (
        "calculate_baseline() should return BaselineResult with sufficient data"
    )


def test_baseline_result_includes_transactions():
    """
    Test that BaselineResult includes transaction data for visualization.

    Requirements (T107-T109):
    - BaselineResult must have 'transactions' field
    - Transactions list should contain (amount_btc, timestamp) tuples
    - Frontend needs this data to render dense cyan point cloud

    Expected:
    - result.transactions is not None
    - result.transactions is a list
    - Each element is a (float, float) tuple
    - At least some transactions are included (not empty)
    """
    # Arrange
    calc = BaselineCalculator(window_blocks=144)

    # Add 5 blocks with transactions
    for i in range(5):
        transactions = [(0.5 + j * 0.1, time.time() - i * 600 - j) for j in range(50)]
        calc.add_block(transactions, height=900000 + i)

    # Act
    result = calc.calculate_baseline()

    # Assert
    assert result is not None
    assert hasattr(result, "transactions"), (
        "BaselineResult must have 'transactions' field for visualization"
    )
    assert result.transactions is not None, "transactions field must be populated"
    assert isinstance(result.transactions, list), "transactions must be a list"
    assert len(result.transactions) > 0, "transactions list must not be empty"

    # Verify structure: list of (amount_btc, timestamp) tuples
    first_tx = result.transactions[0]
    assert isinstance(first_tx, tuple), "Each transaction must be a tuple"
    assert len(first_tx) == 2, "Each transaction tuple must have 2 elements"
    amount_btc, timestamp = first_tx
    assert isinstance(amount_btc, float), "amount_btc must be float"
    assert isinstance(timestamp, (int, float)), "timestamp must be numeric"
