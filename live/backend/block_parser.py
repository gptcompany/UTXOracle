"""
Block Parser - Extract transactions from raw Bitcoin blocks

Reuses tx_processor logic to parse individual transactions from blocks.
"""

import logging
import struct
from typing import List, Tuple

logger = logging.getLogger("live.block_parser")


def read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Read Bitcoin varint from bytes.

    Returns: (value, new_offset)
    """
    first_byte = data[offset]

    if first_byte < 0xFD:
        return (first_byte, offset + 1)
    elif first_byte == 0xFD:
        return (struct.unpack("<H", data[offset + 1:offset + 3])[0], offset + 3)
    elif first_byte == 0xFE:
        return (struct.unpack("<I", data[offset + 1:offset + 5])[0], offset + 5)
    else:  # 0xFF
        return (struct.unpack("<Q", data[offset + 1:offset + 9])[0], offset + 9)


def parse_transaction_from_block(data: bytes, offset: int) -> Tuple[List[Tuple[float, float]], int]:
    """
    Parse a single transaction from block data.

    Returns: ([(amount_btc, value_satoshis), ...], new_offset)

    This is a simplified parser that extracts output amounts only.
    Full validation is not needed for baseline price calculation.
    """
    try:
        start_offset = offset

        # Read version (4 bytes)
        version = struct.unpack("<I", data[offset:offset + 4])[0]
        offset += 4

        # Check for SegWit marker (0x00 0x01)
        is_segwit = False
        if offset + 2 <= len(data) and data[offset] == 0x00 and data[offset + 1] == 0x01:
            is_segwit = True
            offset += 2

        # Read input count
        input_count, offset = read_varint(data, offset)

        # Skip inputs
        for _ in range(input_count):
            # Previous output hash (32 bytes)
            offset += 32
            # Previous output index (4 bytes)
            offset += 4
            # Script length
            script_len, offset = read_varint(data, offset)
            # Script
            offset += script_len
            # Sequence (4 bytes)
            offset += 4

        # Read output count
        output_count, offset = read_varint(data, offset)

        # Parse outputs
        outputs = []
        for _ in range(output_count):
            # Value (8 bytes, satoshis)
            value_satoshis = struct.unpack("<Q", data[offset:offset + 8])[0]
            offset += 8

            # Script length
            script_len, offset = read_varint(data, offset)
            # Script
            offset += script_len

            # Convert to BTC
            value_btc = value_satoshis / 100_000_000.0
            outputs.append((value_btc, float(value_satoshis)))

        # Skip witness data if SegWit
        if is_segwit:
            for _ in range(input_count):
                witness_count, offset = read_varint(data, offset)
                for _ in range(witness_count):
                    witness_len, offset = read_varint(data, offset)
                    offset += witness_len

        # Locktime (4 bytes)
        offset += 4

        return (outputs, offset)

    except Exception as e:
        logger.error(f"Failed to parse transaction at offset {offset}: {e}")
        # Return empty outputs and skip to end
        return ([], offset + 250)  # Approximate tx size skip


def extract_transactions_from_block(block_bytes: bytes, block_timestamp: float) -> List[Tuple[float, float]]:
    """
    Extract all transaction outputs from a raw block.

    Args:
        block_bytes: Raw block data from ZMQ
        block_timestamp: Block timestamp (Unix epoch seconds)

    Returns:
        List of (amount_btc, timestamp) tuples for baseline calculator
    """
    try:
        # Skip block header (80 bytes)
        offset = 80

        # Read transaction count
        tx_count, offset = read_varint(block_bytes, offset)
        logger.info(f"Parsing block with {tx_count} transactions")

        # Extract all transaction outputs
        all_outputs = []

        for tx_idx in range(tx_count):
            outputs, offset = parse_transaction_from_block(block_bytes, offset)

            # Filter outputs by UTXOracle criteria
            for amount_btc, value_sats in outputs:
                # Apply same filters as mempool: amount range [1e-5, 1e5] BTC
                if 1e-5 <= amount_btc <= 1e5:
                    all_outputs.append((amount_btc, block_timestamp))

        logger.info(f"Extracted {len(all_outputs)} outputs from {tx_count} transactions")
        return all_outputs

    except Exception as e:
        logger.exception(f"Failed to parse block: {e}")
        return []
