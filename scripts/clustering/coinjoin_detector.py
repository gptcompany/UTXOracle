"""CoinJoin Detection Module.

Identifies privacy-enhancing CoinJoin transactions using multiple heuristics:
- Equal output detection
- Known protocol patterns (Wasabi, Whirlpool, JoinMarket)
- Input/output ratio analysis

CoinJoin transactions should be filtered from whale tracking to avoid
false positives and improve signal accuracy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


# Whirlpool fixed denominations in SATOSHIS (for electrs API compatibility)
# 0.001 BTC = 100,000 sats, 0.01 BTC = 1,000,000 sats, etc.
WHIRLPOOL_DENOMINATIONS_SATS = frozenset([100_000, 1_000_000, 5_000_000, 50_000_000])

# Also keep BTC versions for test compatibility
WHIRLPOOL_DENOMINATIONS_BTC = frozenset([0.001, 0.01, 0.05, 0.5])

# Threshold to detect if value is in satoshis vs BTC
# Any value > 1000 is likely satoshis (smallest pool is 0.001 BTC = 100,000 sats)
SATOSHI_THRESHOLD = 1000

# Minimum thresholds
MIN_EQUAL_OUTPUTS_GENERIC = 5  # Generic CoinJoin threshold
MIN_INPUTS_GENERIC = 3  # Minimum inputs for CoinJoin


def _normalize_to_satoshis(value: float) -> int:
    """Normalize a value to satoshis regardless of input unit.

    Args:
        value: Amount in either BTC or satoshis

    Returns:
        Amount in satoshis (integer), or 0 for invalid values
    """
    import math

    # Handle edge cases: negative, zero, infinity, NaN
    if value <= 0 or math.isinf(value) or math.isnan(value):
        return 0

    if value > SATOSHI_THRESHOLD:
        # Already in satoshis
        return int(value)
    else:
        # In BTC, convert to satoshis
        return int(value * 100_000_000)


@dataclass
class CoinJoinResult:
    """Result of CoinJoin detection analysis.

    Attributes:
        txid: Transaction identifier
        is_coinjoin: Whether transaction is likely a CoinJoin
        confidence: Confidence score (0.0 to 1.0)
        coinjoin_type: Detected protocol type or None
        equal_output_count: Number of outputs with equal values
        total_inputs: Total number of transaction inputs
        total_outputs: Total number of transaction outputs
        detection_reasons: List of reasons for classification
    """

    txid: str
    is_coinjoin: bool = False
    confidence: float = 0.0
    coinjoin_type: str | None = None
    equal_output_count: int = 0
    total_inputs: int = 0
    total_outputs: int = 0
    detection_reasons: list[str] = field(default_factory=list)


def _check_equal_outputs(vouts: list[dict]) -> tuple[int, float | None]:
    """Check for equal value outputs in transaction.

    Args:
        vouts: List of transaction outputs

    Returns:
        Tuple of (count of most common equal value, the value or None)
    """
    if not vouts:
        return 0, None

    values = [out.get("value", 0) for out in vouts]
    value_counts = Counter(values)

    if not value_counts:
        return 0, None

    most_common_value, count = value_counts.most_common(1)[0]
    return count, most_common_value if count > 1 else None


def _check_known_patterns(
    vouts: list[dict],
    equal_count: int,
    equal_value: float | None,
    total_inputs: int,
) -> tuple[str | None, float, list[str]]:
    """Check for known CoinJoin protocol patterns.

    Args:
        vouts: Transaction outputs
        equal_count: Number of equal outputs
        equal_value: The equal output value (in original units - BTC or sats)
        total_inputs: Number of inputs

    Returns:
        Tuple of (coinjoin_type, confidence, reasons)
    """
    reasons = []
    coinjoin_type = None
    confidence = 0.0

    # Check for Wasabi pattern (100+ equal outputs)
    if equal_count >= 100:
        coinjoin_type = "wasabi"
        confidence = 0.95
        reasons.append(f"Wasabi pattern: {equal_count} equal outputs")
        return coinjoin_type, confidence, reasons

    # Check for Whirlpool pattern (fixed denominations)
    # Handle both BTC and satoshi values
    if equal_value is not None:
        equal_value_sats = _normalize_to_satoshis(equal_value)
        is_whirlpool_denom = (
            equal_value_sats in WHIRLPOOL_DENOMINATIONS_SATS
            or equal_value in WHIRLPOOL_DENOMINATIONS_BTC
        )
        if is_whirlpool_denom and equal_count >= 5:
            coinjoin_type = "whirlpool"
            confidence = 0.85
            # Display value in BTC for readability
            display_value = (
                equal_value
                if equal_value < SATOSHI_THRESHOLD
                else equal_value / 100_000_000
            )
            reasons.append(
                f"Whirlpool pattern: {equal_count} outputs at {display_value} BTC"
            )
            return coinjoin_type, confidence, reasons

    # Check for JoinMarket pattern (maker/taker, 3-10 equal outputs)
    if 3 <= equal_count <= 20 and total_inputs >= 3:
        # JoinMarket typically has taker + makers
        coinjoin_type = "joinmarket"
        confidence = 0.7
        reasons.append(
            f"JoinMarket pattern: {equal_count} equal outputs, {total_inputs} inputs"
        )
        return coinjoin_type, confidence, reasons

    # Generic CoinJoin
    if equal_count >= MIN_EQUAL_OUTPUTS_GENERIC and total_inputs >= MIN_INPUTS_GENERIC:
        coinjoin_type = "generic"
        confidence = 0.7 + min(0.2, equal_count / 50)  # Scale up to 0.9
        reasons.append(f"Generic CoinJoin: {equal_count} equal outputs")

    return coinjoin_type, confidence, reasons


def detect_coinjoin(tx: dict) -> CoinJoinResult:
    """Detect if a transaction is a CoinJoin.

    Analyzes transaction structure using multiple heuristics:
    1. Equal output detection - Most CoinJoins have equal-value outputs
    2. Known patterns - Wasabi, Whirlpool, JoinMarket signatures
    3. Input/output ratio - CoinJoins typically have many inputs and outputs

    Args:
        tx: Transaction dictionary with 'txid', 'vin', and 'vout' keys

    Returns:
        CoinJoinResult with detection analysis

    Example:
        >>> tx = {"txid": "abc", "vin": [...], "vout": [...]}
        >>> result = detect_coinjoin(tx)
        >>> if result.is_coinjoin:
        ...     print(f"CoinJoin detected: {result.coinjoin_type}")
    """
    txid = tx.get("txid", "unknown")
    vins = tx.get("vin", [])
    vouts = tx.get("vout", [])

    total_inputs = len(vins)
    total_outputs = len(vouts)

    result = CoinJoinResult(
        txid=txid,
        total_inputs=total_inputs,
        total_outputs=total_outputs,
    )

    # Quick rejection: too few outputs for CoinJoin
    if total_outputs < MIN_EQUAL_OUTPUTS_GENERIC:
        result.detection_reasons.append(
            f"Too few outputs ({total_outputs}) for CoinJoin"
        )
        return result

    # Check for equal outputs
    equal_count, equal_value = _check_equal_outputs(vouts)
    result.equal_output_count = equal_count

    # Check known patterns
    coinjoin_type, confidence, reasons = _check_known_patterns(
        vouts, equal_count, equal_value, total_inputs
    )

    if coinjoin_type:
        result.is_coinjoin = True
        result.coinjoin_type = coinjoin_type
        result.confidence = confidence
        result.detection_reasons.extend(reasons)
    else:
        result.detection_reasons.append("No CoinJoin pattern detected")

    return result


def save_coinjoin_result(
    result: CoinJoinResult,
    db_path: str = str(UTXORACLE_DB_PATH),
) -> bool:
    """Save CoinJoin detection result to database cache.

    Args:
        result: CoinJoinResult to save
        db_path: Path to DuckDB database

    Returns:
        True if saved successfully, False otherwise
    """
    import duckdb
    from datetime import datetime

    try:
        conn = duckdb.connect(db_path)
        conn.execute(
            """
            INSERT INTO coinjoin_cache (
                txid, is_coinjoin, confidence, coinjoin_type,
                equal_output_count, total_inputs, total_outputs, detected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (txid) DO UPDATE SET
                is_coinjoin = EXCLUDED.is_coinjoin,
                confidence = EXCLUDED.confidence,
                coinjoin_type = EXCLUDED.coinjoin_type,
                detected_at = EXCLUDED.detected_at
            """,
            [
                result.txid,
                result.is_coinjoin,
                result.confidence,
                result.coinjoin_type,
                result.equal_output_count,
                result.total_inputs,
                result.total_outputs,
                datetime.now(),
            ],
        )
        conn.close()
        return True
    except Exception:
        return False


def is_coinjoin(tx: dict, threshold: float = 0.7) -> bool:
    """Simple boolean check if transaction is CoinJoin.

    Args:
        tx: Transaction dictionary
        threshold: Minimum confidence threshold

    Returns:
        True if likely CoinJoin, False otherwise
    """
    result = detect_coinjoin(tx)
    return result.is_coinjoin and result.confidence >= threshold
