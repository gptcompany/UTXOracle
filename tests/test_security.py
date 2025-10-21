"""
Security tests for UTXOracle Live

Tests for T103 Security Audit - validates DoS protection against malicious inputs
"""

import pytest
from live.backend.tx_processor import TransactionProcessor


def test_malicious_varint_does_not_cause_memory_exhaustion():
    """
    Verify parser handles malicious varint claiming 2^32 inputs without
    allocating massive memory (DoS protection).

    Security requirement: Parser must fail gracefully on malicious varints
    that claim impossibly large counts without exhausting system memory.
    """
    processor = TransactionProcessor()

    # Craft transaction with varint = 0xFE claiming 2^32 inputs
    malicious_tx = bytes(
        [
            0x01,
            0x00,
            0x00,
            0x00,  # version
            0xFE,  # varint marker (4-byte value follows)
            0xFF,
            0xFF,
            0xFF,
            0xFF,  # 2^32-1 inputs (4,294,967,295)
            # ... rest truncated (parser should fail before allocating memory)
        ]
    )

    # Should raise ValueError due to truncated data, NOT attempt to allocate 2^32 objects
    # This validates that bounds checking happens BEFORE memory allocation
    with pytest.raises(ValueError, match="truncated|invalid|Truncated|exceeds"):
        processor.parse_transaction(malicious_tx)
