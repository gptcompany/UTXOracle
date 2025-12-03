"""
Tests for Transaction Processor (Module 2)

TDD Phase: RED - All tests must FAIL initially

Tasks:
- T022 [P]: test_parse_binary_transaction (version, inputs, outputs, locktime)
- T023 [P]: test_filter_transactions (≤5 inputs, 2 outputs, amount range)
"""

import pytest
from live.backend.tx_processor import TransactionProcessor
from live.shared.models import ProcessedTransaction


# =============================================================================
# T022: Binary Transaction Parsing Test
# =============================================================================


def test_parse_binary_transaction():
    """
    Test that TransactionProcessor can parse binary transaction data.

    Requirements (from UTXOracle.py Step 6):
    - Parse version (4 bytes, little endian, int32)
    - Parse input count (varint)
    - Parse each input (prev_tx, prev_index, script_sig, sequence)
    - Parse output count (varint)
    - Parse each output (value in satoshis, script_pubkey)
    - Parse locktime (4 bytes, little endian, uint32)
    - Handle both legacy and SegWit transactions

    Contract:
        TransactionProcessor.parse_transaction(raw_bytes: bytes) -> ParsedTransaction
    """
    # Arrange: Create processor
    processor = TransactionProcessor()

    # Sample transaction bytes (legacy format, 1 input, 2 outputs)
    raw_bytes = bytes.fromhex(
        "02000000"  # version = 2
        "01"  # 1 input
        # Input 1
        "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"  # prev tx (32 bytes)
        "00000000"  # prev index = 0
        "00"  # script sig length = 0
        "ffffffff"  # sequence
        "02"  # 2 outputs
        # Output 1: 0.001 BTC (100,000 satoshis)
        "a086010000000000"  # value = 100000 satoshis
        "19"  # script length = 25
        "76a914"
        "0000000000000000000000000000000000000000"
        "88ac"  # P2PKH script
        # Output 2: 0.002 BTC (200,000 satoshis)
        "400d030000000000"  # value = 200000 satoshis
        "19"  # script length = 25
        "76a914"
        "1111111111111111111111111111111111111111"
        "88ac"  # P2PKH script
        "00000000"  # locktime = 0
    )

    # Act: Parse transaction
    parsed = processor.parse_transaction(raw_bytes)

    # Assert: Version parsed correctly
    assert parsed.version == 2, "Version should be 2"

    # Assert: Inputs parsed correctly
    assert len(parsed.inputs) == 1, "Should have 1 input"
    assert parsed.inputs[0].prev_index == 0, "Previous output index should be 0"
    assert parsed.inputs[0].sequence == 0xFFFFFFFF, "Sequence should be 0xffffffff"

    # Assert: Outputs parsed correctly
    assert len(parsed.outputs) == 2, "Should have 2 outputs"
    assert parsed.outputs[0].value == 100000, "Output 1 should be 100000 satoshis"
    assert parsed.outputs[1].value == 200000, "Output 2 should be 200000 satoshis"
    assert parsed.outputs[0].to_btc() == 0.001, "Output 1 should be 0.001 BTC"
    assert parsed.outputs[1].to_btc() == 0.002, "Output 2 should be 0.002 BTC"

    # Assert: Locktime parsed correctly
    assert parsed.locktime == 0, "Locktime should be 0"

    # Assert: Transaction type detected
    assert not parsed.is_segwit, "Should be detected as non-segwit (legacy)"


def test_parse_segwit_transaction():
    """
    Test that TransactionProcessor can parse SegWit transactions.

    Requirements:
    - Detect SegWit marker (0x00) and flag (0x01)
    - Parse witness data separately
    - Extract witness fields correctly

    Contract: Same as test_parse_binary_transaction but with is_segwit=True
    """
    # Arrange: Create processor
    processor = TransactionProcessor()

    # Sample SegWit transaction (simplified)
    raw_bytes = bytes.fromhex(
        "02000000"  # version = 2
        "0001"  # SegWit marker (0x00) + flag (0x01)
        "01"  # 1 input
        # Input
        "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        "00000000"
        "00"
        "ffffffff"
        "02"  # 2 outputs
        # Output 1
        "a086010000000000"
        "16"  # SegWit script length
        "0014"
        "0000000000000000000000000000000000000000"  # P2WPKH
        # Output 2
        "400d030000000000"
        "16"
        "0014"
        "1111111111111111111111111111111111111111"
        # Witness data (simplified - actual witness would be more complex)
        "02"  # 2 witness stack items
        "47"  # 71 bytes
        + "30" * 71  # Dummy signature
        + "21"  # 33 bytes
        + "02"
        + "ff" * 32  # Dummy pubkey
        + "00000000"  # locktime
    )

    # Act: Parse transaction
    parsed = processor.parse_transaction(raw_bytes)

    # Assert: SegWit detected
    assert parsed.is_segwit, "Should be detected as SegWit"
    assert parsed.witness_data is not None, "Witness data should be extracted"
    assert len(parsed.inputs) == 1
    assert len(parsed.outputs) == 2


def test_parse_transaction_with_multiple_inputs():
    """
    Test parsing transaction with multiple inputs (up to 5 per UTXOracle filter).

    Requirements:
    - Parse variable input count (varint encoding)
    - Handle multiple inputs correctly

    Contract: Parsed transaction has correct input count and data
    """
    # Arrange: Transaction with 3 inputs, 2 outputs
    processor = TransactionProcessor()

    # Build transaction manually
    raw_bytes = bytes.fromhex(
        "01000000"  # version = 1
        "03"  # 3 inputs
        # Input 1
        + "00" * 32  # prev tx
        + "00000000"  # prev index
        + "00"  # script sig
        + "ffffffff"  # sequence
        # Input 2
        + "11" * 32
        + "01000000"
        + "00"
        + "ffffffff"
        # Input 3
        + "22" * 32
        + "02000000"
        + "00"
        + "ffffffff"
        + "02"  # 2 outputs
        # Output 1
        + "a086010000000000"
        + "00"
        # Output 2
        + "400d030000000000"
        + "00"
        + "00000000"  # locktime
    )

    # Act: Parse
    parsed = processor.parse_transaction(raw_bytes)

    # Assert: Input count correct
    assert len(parsed.inputs) == 3, "Should have 3 inputs"
    assert parsed.inputs[0].prev_index == 0
    assert parsed.inputs[1].prev_index == 1
    assert parsed.inputs[2].prev_index == 2


def test_parse_transaction_error_handling():
    """
    Test that parser handles malformed transaction data gracefully.

    Requirements:
    - Raise ValueError for truncated transactions
    - Raise ValueError for invalid varint encoding
    - Provide descriptive error messages

    Contract: parse_transaction() raises ValueError with clear message
    """
    processor = TransactionProcessor()

    # Test 1: Truncated transaction (too short)
    with pytest.raises(ValueError) as exc_info:
        processor.parse_transaction(b"\x01\x00\x00")  # Only 3 bytes

    assert (
        "truncated" in str(exc_info.value).lower()
        or "invalid" in str(exc_info.value).lower()
    )

    # Test 2: Empty transaction
    with pytest.raises(ValueError) as exc_info:
        processor.parse_transaction(b"")

    assert (
        "empty" in str(exc_info.value).lower()
        or "invalid" in str(exc_info.value).lower()
    )


# =============================================================================
# T023: Transaction Filtering Test
# =============================================================================


def test_filter_transactions():
    """
    Test that TransactionProcessor applies UTXOracle filters correctly.

    UTXOracle Filtering Rules (from UTXOracle.py Step 6):
    - Input count: ≤ 5 inputs
    - Output count: Exactly 2 outputs
    - Output amounts: Each output in range [1e-5, 1e5] BTC (0.00001 to 100,000 BTC)
    - Exclude round amounts: No outputs with exactly round BTC values (1.0, 2.0, etc.)

    Contract:
        TransactionProcessor.filter_transaction(parsed: ParsedTransaction) -> bool
        TransactionProcessor.to_processed(parsed: ParsedTransaction) -> ProcessedTransaction
    """
    # Arrange: Create processor
    processor = TransactionProcessor()

    # Test Case 1: Valid transaction (should pass filter)
    valid_tx_bytes = bytes.fromhex(
        "02000000"
        "02"  # 2 inputs (≤5, valid)
        + "00" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "11" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "02"  # 2 outputs (valid)
        + "a086010000000000"  # 0.001 BTC (valid range, not round)
        + "00"
        + "400d030000000000"  # 0.002 BTC (valid range, not round)
        + "00"
        + "00000000"
    )

    valid_parsed = processor.parse_transaction(valid_tx_bytes)

    # Act: Filter transaction
    should_process = processor.filter_transaction(valid_parsed)

    # Assert: Valid transaction passes filter
    assert should_process, "Valid transaction should pass filter"

    # Convert to ProcessedTransaction
    processed = processor.to_processed(valid_parsed, timestamp=1678901234.567)

    assert isinstance(processed, ProcessedTransaction)
    assert processed.input_count == 2
    assert processed.output_count == 2
    assert len(processed.amounts) == 2
    assert processed.amounts[0] == 0.001
    assert processed.amounts[1] == 0.002


def test_filter_rejects_too_many_inputs():
    """
    Test that filter rejects transactions with >5 inputs.

    UTXOracle Rule: ≤5 inputs only
    """
    processor = TransactionProcessor()

    # Transaction with 6 inputs (should fail)
    raw_bytes = bytes.fromhex(
        "01000000"
        "06"  # 6 inputs (INVALID - exceeds limit)
        + ("00" * 32 + "00000000" + "00" + "ffffffff") * 6
        + "02"
        + "a086010000000000"
        + "00"
        + "400d030000000000"
        + "00"
        + "00000000"
    )

    parsed = processor.parse_transaction(raw_bytes)

    # Act & Assert: Should be rejected
    assert not processor.filter_transaction(parsed), (
        "Should reject transaction with >5 inputs"
    )


def test_filter_rejects_wrong_output_count():
    """
    Test that filter rejects transactions without exactly 2 outputs.

    UTXOracle Rule: Exactly 2 outputs
    """
    processor = TransactionProcessor()

    # Test 1: 1 output (should fail)
    raw_bytes_1_output = bytes.fromhex(
        "01000000"
        "01"  # 1 input
        + "00" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "01"  # 1 output (INVALID)
        + "a086010000000000"
        + "00"
        + "00000000"
    )

    parsed_1 = processor.parse_transaction(raw_bytes_1_output)
    assert not processor.filter_transaction(parsed_1), (
        "Should reject transaction with 1 output"
    )

    # Test 2: 3 outputs (should fail)
    raw_bytes_3_outputs = bytes.fromhex(
        "01000000"
        "01"
        + "00" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "03"  # 3 outputs (INVALID)
        + "a086010000000000"
        + "00"
        + "400d030000000000"
        + "00"
        + "e093040000000000"
        + "00"  # Third output
        + "00000000"
    )

    parsed_3 = processor.parse_transaction(raw_bytes_3_outputs)
    assert not processor.filter_transaction(parsed_3), (
        "Should reject transaction with 3 outputs"
    )


def test_filter_rejects_out_of_range_amounts():
    """
    Test that filter rejects outputs outside [1e-5, 1e5] BTC range.

    UTXOracle Rule: Output amounts must be in [0.00001 BTC, 100,000 BTC]
    """
    processor = TransactionProcessor()

    # Test 1: Amount too small (0.000001 BTC = 100 satoshis)
    raw_bytes_too_small = bytes.fromhex(
        "01000000"
        "01" + "00" * 32 + "00000000" + "00" + "ffffffff"
        "02"
        + "6400000000000000"  # 100 satoshis = 0.000001 BTC (INVALID - too small)
        + "00"
        + "400d030000000000"  # 0.002 BTC (valid)
        + "00"
        + "00000000"
    )

    parsed_small = processor.parse_transaction(raw_bytes_too_small)
    assert not processor.filter_transaction(parsed_small), (
        "Should reject amounts < 1e-5 BTC"
    )

    # Test 2: Amount too large (200,000 BTC)
    # 200,000 BTC = 20,000,000,000,000 satoshis = 0x1C6BF52634000
    raw_bytes_too_large = bytes.fromhex(
        "01000000"
        "01" + "00" * 32 + "00000000" + "00" + "ffffffff"
        "02"
        + "400d030000000000"  # 0.002 BTC (valid)
        + "00"
        + "0000341C6BF52600"  # 200,000 BTC (INVALID - too large)
        + "00"
        + "00000000"
    )

    parsed_large = processor.parse_transaction(raw_bytes_too_large)
    assert not processor.filter_transaction(parsed_large), (
        "Should reject amounts > 1e5 BTC"
    )


def test_filter_rejects_round_amounts():
    """
    Test that filter rejects transactions with round BTC amounts.

    UTXOracle Rule (Step 7): Exclude transactions with exactly round amounts
    (1.0 BTC, 2.0 BTC, etc.) as they are likely non-market activity
    """
    processor = TransactionProcessor()

    # Transaction with exactly 1.0 BTC output (should fail)
    raw_bytes_round = bytes.fromhex(
        "01000000"
        "01" + "00" * 32 + "00000000" + "00" + "ffffffff"
        "02"
        + "00e1f50500000000"  # 1.0 BTC exactly = 100,000,000 satoshis (INVALID - round)
        + "00"
        + "400d030000000000"  # 0.002 BTC (valid, not round)
        + "00"
        + "00000000"
    )

    parsed_round = processor.parse_transaction(raw_bytes_round)
    assert not processor.filter_transaction(parsed_round), (
        "Should reject round BTC amounts"
    )


def test_to_processed_generates_correct_txid():
    """
    Test that to_processed() generates correct transaction ID.

    Requirements:
    - TXID = SHA256(SHA256(raw_transaction_bytes))
    - TXID displayed as hex string (64 characters)
    - TXID is reversed byte order (Bitcoin convention)

    Contract: ProcessedTransaction.txid is valid 64-char hex string
    """
    processor = TransactionProcessor()

    raw_bytes = bytes.fromhex(
        "01000000"
        "01" + "00" * 32 + "00000000" + "00" + "ffffffff"
        "02" + "a086010000000000" + "00" + "400d030000000000" + "00" + "00000000"
    )

    parsed = processor.parse_transaction(raw_bytes)
    processed = processor.to_processed(parsed, timestamp=1678901234.567)

    # Assert: TXID is 64-character hex string
    assert len(processed.txid) == 64, "TXID must be 64 characters"
    assert all(c in "0123456789abcdef" for c in processed.txid.lower()), (
        "TXID must be hex"
    )

    # Assert: TXID is deterministic (same input = same txid)
    parsed2 = processor.parse_transaction(raw_bytes)
    processed2 = processor.to_processed(parsed2, timestamp=1678901234.567)
    assert processed.txid == processed2.txid, "TXID must be deterministic"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_valid_transaction_bytes() -> bytes:
    """Sample valid transaction that passes all UTXOracle filters"""
    return bytes.fromhex(
        "02000000"  # version
        "02"  # 2 inputs
        + "00" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "11" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "02"  # 2 outputs
        + "a086010000000000"  # 0.001 BTC
        + "00"
        + "400d030000000000"  # 0.002 BTC
        + "00"
        + "00000000"  # locktime
    )
