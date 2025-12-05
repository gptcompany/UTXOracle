"""Change Output Detection Module.

Identifies likely change outputs in Bitcoin transactions using heuristics:
1. Odd amount heuristic - Payments are often round numbers, change is not
2. Size heuristic - Change is typically smaller than the payment
3. Address pattern matching - Change often returns to similar address type

These heuristics are probabilistic and should be used with caution.

Reference: Meiklejohn et al. (2013), Androulaki et al. (2013)
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Threshold for "odd" amount detection (significant decimal places)
ODD_AMOUNT_DECIMALS = 4  # More than 4 decimals = likely change

# Size threshold: output < this fraction of max is likely change
SIZE_THRESHOLD = 0.10  # 10%

# Threshold to detect if value is in satoshis vs BTC
SATOSHI_THRESHOLD = 1000


@dataclass
class ChangeDetectionResult:
    """Result of change output detection.

    Attributes:
        txid: Transaction identifier
        outputs: List of output dictionaries
        likely_payment_outputs: Indices of outputs likely to be payments
        likely_change_outputs: Indices of outputs likely to be change
    """

    txid: str
    outputs: list[dict] = field(default_factory=list)
    likely_payment_outputs: list[int] = field(default_factory=list)
    likely_change_outputs: list[int] = field(default_factory=list)


def _is_round_amount(value: float) -> bool:
    """Check if amount appears to be a round number.

    Handles both BTC and satoshi values (auto-detected).

    Args:
        value: Amount in BTC or satoshis

    Returns:
        True if amount has few decimal places (likely intentional)
    """
    import math

    # Handle edge cases: negative, zero, infinity, NaN
    if value <= 0 or math.isinf(value) or math.isnan(value):
        return True

    # Detect if value is in satoshis or BTC
    if value > SATOSHI_THRESHOLD:
        # Value is in satoshis - check directly as integer
        satoshis = int(value)
        # Check if it's a multiple of common round amounts
        for divisor in [100_000_000, 10_000_000, 1_000_000, 100_000, 10_000, 1_000]:
            if satoshis % divisor == 0:
                return True
        return False
    else:
        # Value is in BTC - convert to satoshis safely
        # Use round() to avoid floating point errors
        satoshis = round(value * 1e8)
        # Check if it's a multiple of common round amounts
        for divisor in [100_000_000, 10_000_000, 1_000_000, 100_000, 10_000, 1_000]:
            if satoshis % divisor == 0:
                return True

        # Fallback: Check decimal string representation for BTC values
        str_value = f"{value:.8f}".rstrip("0")
        decimal_part = str_value.split(".")[-1] if "." in str_value else ""
        return len(decimal_part) <= ODD_AMOUNT_DECIMALS


def detect_change_outputs(tx: dict) -> ChangeDetectionResult:
    """Detect likely change outputs in a transaction.

    Uses multiple heuristics:
    1. Round amount heuristic: Round numbers are likely payments
    2. Size heuristic: Small outputs (< 10% of max) are likely change

    Args:
        tx: Transaction dictionary with 'txid' and 'vout' keys

    Returns:
        ChangeDetectionResult with classified outputs

    Example:
        >>> tx = {"txid": "abc", "vout": [{"value": 1.0}, {"value": 0.12345678}]}
        >>> result = detect_change_outputs(tx)
        >>> print(result.likely_change_outputs)  # [1]
    """
    txid = tx.get("txid", "unknown")
    vouts = tx.get("vout", [])

    result = ChangeDetectionResult(
        txid=txid,
        outputs=vouts,
    )

    if len(vouts) < 2:
        # Single output - no change detection possible
        if vouts:
            result.likely_payment_outputs = [0]
        return result

    # Extract values
    values = [out.get("value", 0) for out in vouts]
    max_value = max(values) if values else 0

    # Apply heuristics to each output
    for idx, value in enumerate(values):
        is_round = _is_round_amount(value)
        is_small = max_value > 0 and value < (max_value * SIZE_THRESHOLD)

        # Determine classification
        if is_small:
            # Small output is likely change
            result.likely_change_outputs.append(idx)
        elif not is_round:
            # Odd amount with no other indicators is likely change
            # But only if there's a round amount to compare
            has_round_output = any(_is_round_amount(v) for v in values if v != value)
            if has_round_output:
                result.likely_change_outputs.append(idx)
            else:
                # Can't determine - both outputs are odd
                pass
        else:
            # Round amount, not small - likely payment
            result.likely_payment_outputs.append(idx)

    return result


def get_likely_change_address(tx: dict) -> str | None:
    """Get the most likely change address from a transaction.

    Args:
        tx: Transaction dictionary

    Returns:
        Change address if confidently detected, None otherwise
    """
    result = detect_change_outputs(tx)

    if len(result.likely_change_outputs) == 1:
        idx = result.likely_change_outputs[0]
        vouts = tx.get("vout", [])
        if idx < len(vouts):
            return vouts[idx].get("scriptPubKey", {}).get("address")

    return None
