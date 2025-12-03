#!/usr/bin/env python3
"""
RBF (Replace-By-Fee) Detection Utility
Task: T024 - Implements RBF detection logic

RBF is signaled when any input's sequence number is less than 0xFFFFFFFE (BIP 125).
This allows fee bumping for unconfirmed transactions.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# BIP 125: Sequence value that signals non-RBF
RBF_SEQUENCE_THRESHOLD = 0xFFFFFFFE  # 4294967294


def is_rbf_enabled(transaction: Dict[str, Any]) -> bool:
    """
    Check if a transaction has RBF (Replace-By-Fee) enabled.

    According to BIP 125, a transaction signals RBF if ANY input has a
    sequence number less than 0xFFFFFFFE (4294967294).

    Args:
        transaction: Transaction dict with 'vin' array containing inputs

    Returns:
        True if RBF is enabled, False otherwise

    Examples:
        >>> tx = {"vin": [{"sequence": 4294967293}]}
        >>> is_rbf_enabled(tx)
        True

        >>> tx = {"vin": [{"sequence": 4294967295}]}
        >>> is_rbf_enabled(tx)
        False
    """
    if not isinstance(transaction, dict):
        logger.warning(f"Invalid transaction type: {type(transaction)}")
        return False

    inputs = transaction.get("vin", [])
    if not inputs:
        logger.debug("Transaction has no inputs (coinbase?)")
        return False

    # Check if ANY input has sequence < 0xFFFFFFFE
    for i, input_data in enumerate(inputs):
        if not isinstance(input_data, dict):
            logger.warning(f"Invalid input #{i}: {type(input_data)}")
            continue

        sequence = input_data.get("sequence")
        if sequence is None:
            logger.debug(f"Input #{i} missing sequence field")
            continue

        try:
            sequence_int = int(sequence) if not isinstance(sequence, int) else sequence
            if sequence_int < RBF_SEQUENCE_THRESHOLD:
                logger.debug(
                    f"RBF detected: input #{i} has sequence {sequence_int} "
                    f"< {RBF_SEQUENCE_THRESHOLD}"
                )
                return True
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid sequence value in input #{i}: {sequence} - {e}")
            continue

    return False


def get_rbf_status(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed RBF status for a transaction.

    Args:
        transaction: Transaction dict with 'vin' array

    Returns:
        Dict with RBF analysis:
        {
            'rbf_enabled': bool,
            'rbf_inputs_count': int,
            'total_inputs': int,
            'min_sequence': int,
            'details': List[Dict[str, Any]]
        }
    """
    inputs = transaction.get("vin", [])
    total_inputs = len(inputs)
    rbf_inputs = []
    sequences = []

    for i, input_data in enumerate(inputs):
        if not isinstance(input_data, dict):
            continue

        sequence = input_data.get("sequence")
        if sequence is None:
            continue

        try:
            sequence_int = int(sequence) if not isinstance(sequence, int) else sequence
            sequences.append(sequence_int)

            if sequence_int < RBF_SEQUENCE_THRESHOLD:
                rbf_inputs.append(
                    {
                        "input_index": i,
                        "sequence": sequence_int,
                        "txid": input_data.get("txid", "unknown"),
                        "vout": input_data.get("vout"),
                    }
                )
        except (ValueError, TypeError):
            continue

    return {
        "rbf_enabled": len(rbf_inputs) > 0,
        "rbf_inputs_count": len(rbf_inputs),
        "total_inputs": total_inputs,
        "min_sequence": min(sequences) if sequences else None,
        "details": rbf_inputs,
    }


def is_transaction_replaceable(
    txid: str, transaction_cache: Optional[Dict[str, Dict[str, Any]]] = None
) -> bool:
    """
    Check if a specific transaction in the mempool is replaceable via RBF.

    Args:
        txid: Transaction ID to check
        transaction_cache: Optional cache of transactions (txid -> tx data)

    Returns:
        True if transaction is RBF-enabled and in mempool, False otherwise
    """
    if transaction_cache is None:
        logger.warning(
            f"No transaction cache provided, cannot check RBF for {txid[:16]}..."
        )
        return False

    tx = transaction_cache.get(txid)
    if tx is None:
        logger.debug(f"Transaction {txid[:16]}... not found in cache")
        return False

    return is_rbf_enabled(tx)


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Test case 1: RBF enabled (sequence < 0xFFFFFFFE)
    rbf_tx = {
        "txid": "abc123",
        "vin": [
            {"txid": "prev1", "vout": 0, "sequence": 4294967293},  # RBF enabled
            {"txid": "prev2", "vout": 1, "sequence": 4294967294},  # RBF enabled
        ],
    }

    # Test case 2: RBF disabled (all sequences = 0xFFFFFFFE or 0xFFFFFFFF)
    non_rbf_tx = {
        "txid": "def456",
        "vin": [
            {"txid": "prev3", "vout": 0, "sequence": 4294967294},  # Non-RBF
            {"txid": "prev4", "vout": 1, "sequence": 4294967295},  # Final (0xFFFFFFFF)
        ],
    }

    # Test case 3: Mixed (one RBF, one non-RBF)
    mixed_tx = {
        "txid": "ghi789",
        "vin": [
            {"txid": "prev5", "vout": 0, "sequence": 4294967290},  # RBF enabled
            {"txid": "prev6", "vout": 1, "sequence": 4294967295},  # Non-RBF
        ],
    }

    print("\n✅ Testing RBF Detection:")
    print(f"\n1. RBF Transaction: {is_rbf_enabled(rbf_tx)}")
    print(f"   Status: {get_rbf_status(rbf_tx)}")

    print(f"\n2. Non-RBF Transaction: {is_rbf_enabled(non_rbf_tx)}")
    print(f"   Status: {get_rbf_status(non_rbf_tx)}")

    print(f"\n3. Mixed Transaction: {is_rbf_enabled(mixed_tx)}")
    print(f"   Status: {get_rbf_status(mixed_tx)}")

    # Test cache lookup
    cache = {
        "abc123": rbf_tx,
        "def456": non_rbf_tx,
    }

    print(f"\n4. Cache Lookup (abc123): {is_transaction_replaceable('abc123', cache)}")
    print(f"5. Cache Lookup (def456): {is_transaction_replaceable('def456', cache)}")
    print(f"6. Cache Lookup (unknown): {is_transaction_replaceable('xyz', cache)}")
