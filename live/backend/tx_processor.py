"""
Transaction Processor Module (Module 2)

IMPLEMENTAZIONE COMPLETA - Copia questo contenuto in live/backend/tx_processor.py

Parses Bitcoin binary transactions and applies UTXOracle filtering rules.
"""

from __future__ import annotations

import struct
import hashlib
from dataclasses import dataclass
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from live.shared.models import RawTransaction, ProcessedTransaction


@dataclass
class TransactionInput:
    """Parsed transaction input (internal to Module 2)"""

    prev_tx: str  # Previous transaction ID (hex)
    prev_index: int  # Previous output index
    script_sig: bytes  # Signature script
    sequence: int


@dataclass
class TransactionOutput:
    """Parsed transaction output (internal to Module 2)"""

    value: int  # Satoshis (int64)
    script_pubkey: bytes  # Locking script

    def to_btc(self) -> float:
        """Convert satoshis to BTC"""
        return self.value / 100_000_000


@dataclass
class ParsedTransaction:
    """
    Fully parsed transaction (internal to Module 2).

    This is NOT exported to other modules.
    Converted to ProcessedTransaction after filtering.
    """

    version: int
    inputs: List[TransactionInput]
    outputs: List[TransactionOutput]
    locktime: int
    is_segwit: bool
    witness_data: Optional[bytes] = None
    raw_bytes: Optional[bytes] = None


class TransactionProcessor:
    """
    Bitcoin transaction binary parser with UTXOracle filtering.

    Implements:
    - T033-T034: Binary transaction parsing (legacy + SegWit)
    - T035-T037: UTXOracle filtering rules
    - T038: TXID generation
    """

    def __init__(self):
        """Initialize transaction processor"""
        pass

    def parse_transaction(self, raw_bytes: bytes) -> ParsedTransaction:
        """
        Parse Bitcoin binary transaction format.

        Args:
            raw_bytes: Complete binary transaction data

        Returns:
            ParsedTransaction with all fields parsed

        Raises:
            ValueError: If transaction data is malformed
        """
        if len(raw_bytes) == 0:
            raise ValueError("Cannot parse empty transaction")

        if len(raw_bytes) < 10:
            raise ValueError("Transaction data is truncated or invalid")

        offset = 0

        # Parse version (4 bytes, little-endian int32)
        version = struct.unpack("<i", raw_bytes[offset : offset + 4])[0]
        offset += 4

        # Check for SegWit marker (0x00) and flag (0x01)
        is_segwit = False
        if offset + 1 < len(raw_bytes) and raw_bytes[offset] == 0x00:
            if offset + 2 < len(raw_bytes) and raw_bytes[offset + 1] == 0x01:
                is_segwit = True
                offset += 2  # Skip marker and flag

        # Parse input count (varint)
        input_count, bytes_read = self._read_varint(raw_bytes, offset)
        offset += bytes_read

        # Parse inputs
        inputs = []
        for _ in range(input_count):
            tx_input, bytes_read = self._parse_input(raw_bytes, offset)
            inputs.append(tx_input)
            offset += bytes_read

        # Parse output count (varint)
        output_count, bytes_read = self._read_varint(raw_bytes, offset)
        offset += bytes_read

        # Parse outputs
        outputs = []
        for _ in range(output_count):
            tx_output, bytes_read = self._parse_output(raw_bytes, offset)
            outputs.append(tx_output)
            offset += bytes_read

        # Parse witness data if SegWit
        witness_data = None
        if is_segwit:
            witness_start = offset
            for _ in range(input_count):
                witness_count, bytes_read = self._read_varint(raw_bytes, offset)
                offset += bytes_read
                for _ in range(witness_count):
                    item_len, bytes_read = self._read_varint(raw_bytes, offset)
                    offset += bytes_read
                    offset += item_len
            witness_data = raw_bytes[witness_start:offset]

        # Parse locktime (4 bytes, little-endian uint32)
        if offset + 4 > len(raw_bytes):
            raise ValueError("Transaction data truncated at locktime")

        locktime = struct.unpack("<I", raw_bytes[offset : offset + 4])[0]

        return ParsedTransaction(
            version=version,
            inputs=inputs,
            outputs=outputs,
            locktime=locktime,
            is_segwit=is_segwit,
            witness_data=witness_data,
            raw_bytes=raw_bytes,
        )

    def _read_varint(self, data: bytes, offset: int) -> Tuple[int, int]:
        """Read Bitcoin compact size (varint) encoding."""
        if offset >= len(data):
            raise ValueError("Cannot read varint: offset exceeds data length")

        first_byte = data[offset]

        if first_byte < 0xFD:
            return (first_byte, 1)
        elif first_byte == 0xFD:
            if offset + 3 > len(data):
                raise ValueError("Truncated varint (0xFD)")
            value = struct.unpack("<H", data[offset + 1 : offset + 3])[0]
            return (value, 3)
        elif first_byte == 0xFE:
            if offset + 5 > len(data):
                raise ValueError("Truncated varint (0xFE)")
            value = struct.unpack("<I", data[offset + 1 : offset + 5])[0]
            return (value, 5)
        else:  # 0xFF
            if offset + 9 > len(data):
                raise ValueError("Truncated varint (0xFF)")
            value = struct.unpack("<Q", data[offset + 1 : offset + 9])[0]
            return (value, 9)

    def _parse_input(self, data: bytes, offset: int) -> Tuple[TransactionInput, int]:
        """Parse single transaction input."""
        start_offset = offset

        if offset + 32 > len(data):
            raise ValueError("Truncated input: prev_tx")
        prev_tx = data[offset : offset + 32].hex()
        offset += 32

        if offset + 4 > len(data):
            raise ValueError("Truncated input: prev_index")
        prev_index = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4

        script_sig_len, bytes_read = self._read_varint(data, offset)
        offset += bytes_read

        if offset + script_sig_len > len(data):
            raise ValueError("Truncated input: script_sig")
        script_sig = data[offset : offset + script_sig_len]
        offset += script_sig_len

        if offset + 4 > len(data):
            raise ValueError("Truncated input: sequence")
        sequence = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4

        tx_input = TransactionInput(
            prev_tx=prev_tx,
            prev_index=prev_index,
            script_sig=script_sig,
            sequence=sequence,
        )

        return (tx_input, offset - start_offset)

    def _parse_output(self, data: bytes, offset: int) -> Tuple[TransactionOutput, int]:
        """Parse single transaction output."""
        start_offset = offset

        if offset + 8 > len(data):
            raise ValueError("Truncated output: value")
        value = struct.unpack("<Q", data[offset : offset + 8])[0]
        offset += 8

        script_len, bytes_read = self._read_varint(data, offset)
        offset += bytes_read

        if offset + script_len > len(data):
            raise ValueError("Truncated output: script_pubkey")
        script_pubkey = data[offset : offset + script_len]
        offset += script_len

        tx_output = TransactionOutput(value=value, script_pubkey=script_pubkey)

        return (tx_output, offset - start_offset)

    def filter_transaction(self, parsed: ParsedTransaction) -> bool:
        """Apply UTXOracle filtering rules."""
        # Rule 1: ≤5 inputs
        if len(parsed.inputs) > 5:
            return False

        # Rule 2: Exactly 2 outputs
        if len(parsed.outputs) != 2:
            return False

        # Rule 3 & 4: Check each output
        for output in parsed.outputs:
            btc_amount = output.to_btc()

            # Rule 3: Amount range [1e-5, 1e5] BTC
            if btc_amount < 1e-5 or btc_amount > 1e5:
                return False

            # Rule 4: Exclude round amounts
            if self._is_round_amount(btc_amount):
                return False

        return True

    def _is_round_amount(self, btc_amount: float) -> bool:
        """Check if amount is exactly a round BTC value."""
        return abs(btc_amount - round(btc_amount)) < 1e-8

    def to_processed(
        self, parsed: ParsedTransaction, timestamp: float
    ) -> ProcessedTransaction:
        """Convert ParseedTransaction to ProcessedTransaction."""
        from live.shared.models import ProcessedTransaction

        if parsed.raw_bytes is None:
            raise ValueError("Cannot generate TXID: raw_bytes is None")

        # For SegWit transactions, use transaction data WITHOUT witness
        if parsed.is_segwit:
            txid_bytes = self._serialize_for_txid(parsed)
        else:
            txid_bytes = parsed.raw_bytes

        # Double SHA256
        hash1 = hashlib.sha256(txid_bytes).digest()
        hash2 = hashlib.sha256(hash1).digest()

        # Reverse byte order (Bitcoin convention)
        txid = hash2[::-1].hex()

        # Extract amounts from outputs
        amounts = [output.to_btc() for output in parsed.outputs]

        return ProcessedTransaction(
            txid=txid,
            amounts=amounts,
            timestamp=timestamp,
            fee_rate=None,
            input_count=len(parsed.inputs),
            output_count=len(parsed.outputs),
        )

    def _serialize_for_txid(self, parsed: ParsedTransaction) -> bytes:
        """Serialize transaction for TXID calculation (excludes witness data)."""
        result = bytearray()

        # Version (4 bytes)
        result.extend(struct.pack("<i", parsed.version))

        # Input count (varint)
        result.extend(self._encode_varint(len(parsed.inputs)))

        # Inputs
        for tx_input in parsed.inputs:
            result.extend(bytes.fromhex(tx_input.prev_tx))
            result.extend(struct.pack("<I", tx_input.prev_index))
            result.extend(self._encode_varint(len(tx_input.script_sig)))
            result.extend(tx_input.script_sig)
            result.extend(struct.pack("<I", tx_input.sequence))

        # Output count (varint)
        result.extend(self._encode_varint(len(parsed.outputs)))

        # Outputs
        for tx_output in parsed.outputs:
            result.extend(struct.pack("<Q", tx_output.value))
            result.extend(self._encode_varint(len(tx_output.script_pubkey)))
            result.extend(tx_output.script_pubkey)

        # Locktime (4 bytes)
        result.extend(struct.pack("<I", parsed.locktime))

        return bytes(result)

    def _encode_varint(self, n: int) -> bytes:
        """Encode integer as Bitcoin compact size (varint)."""
        if n < 0xFD:
            return bytes([n])
        elif n <= 0xFFFF:
            return b"\xfd" + struct.pack("<H", n)
        elif n <= 0xFFFFFFFF:
            return b"\xfe" + struct.pack("<I", n)
        else:
            return b"\xff" + struct.pack("<Q", n)


def process_mempool_transaction(
    raw_tx: RawTransaction,
) -> Optional[ProcessedTransaction]:
    """
    One-shot processing: parse + filter + convert.

    Black Box Interface (Module 1 → Module 2 → Module 3):
        Input: RawTransaction (from ZMQ listener)
        Output: ProcessedTransaction (if passes filters) or None
    """

    processor = TransactionProcessor()

    try:
        parsed = processor.parse_transaction(raw_tx.raw_bytes)

        if not processor.filter_transaction(parsed):
            return None  # Filtered out

        processed = processor.to_processed(parsed, timestamp=raw_tx.timestamp)

        return processed

    except (ValueError, struct.error):
        return None  # Malformed transaction - skip
