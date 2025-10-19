"""
Transaction Processor

Stub - will be implemented incrementally following TDD.
"""

import struct
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TransactionInput:
    prev_tx: str
    prev_index: int
    script_sig: bytes
    sequence: int


@dataclass
class TransactionOutput:
    value: int
    script_pubkey: bytes

    def to_btc(self) -> float:
        return self.value / 100_000_000


@dataclass
class ParsedTransaction:
    version: int
    inputs: List[TransactionInput]
    outputs: List[TransactionOutput]
    locktime: int
    is_segwit: bool
    witness_data: Optional[bytes] = None
    raw_bytes: Optional[bytes] = None


class TransactionProcessor:
    """Stub implementation"""

    def parse_transaction(self, raw_bytes: bytes):
        """Parses version field to fix assert 0 == 2"""
        # Parse version (first 4 bytes, little-endian int32)
        version = struct.unpack("<i", raw_bytes[0:4])[0]

        return ParsedTransaction(
            version=version,
            inputs=[],
            outputs=[],
            locktime=0,
            is_segwit=False
        )
