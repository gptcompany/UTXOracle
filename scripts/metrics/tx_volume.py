"""
TX Volume USD Metric (spec-007, User Story 3).

Calculates total transaction volume in BTC and USD using UTXOracle on-chain price.
Implements change output heuristic for adjusted transfer volume.

Usage:
    from scripts.metrics.tx_volume import calculate_tx_volume, estimate_real_volume
    result = calculate_tx_volume(transactions, utxoracle_price=100000.0, confidence=0.85)
"""

from datetime import datetime
from typing import Optional
from scripts.models.metrics_models import TxVolumeMetric

# Satoshis per BTC
SATOSHI_PER_BTC = 100_000_000

# Units of vout["value"] accepted by estimate_real_volume / calculate_tx_volume.
VALUE_UNITS = ("sat", "btc")

# Confidence threshold below which low_confidence flag is set
LOW_CONFIDENCE_THRESHOLD = 0.3


def _btc_per_unit(value_unit: str) -> float:
    """Divisor that turns a vout["value"] in `value_unit` into BTC."""
    if value_unit not in VALUE_UNITS:
        raise ValueError(f"value_unit must be one of {VALUE_UNITS}, got {value_unit!r}")
    return SATOSHI_PER_BTC if value_unit == "sat" else 1


def estimate_real_volume(tx: dict, value_unit: str = "sat") -> float:
    """
    Estimate real transfer volume excluding likely change outputs.

    Uses heuristic: for 2-output transactions, if second output is <10%
    of first, it's likely change and excluded from volume.

    Units: tx["vout"][i]["value"] is in `value_unit` ("sat" = satoshi, the default and the
    raw mempool.space/electrs format; "btc" = already converted, as the daily_analysis
    fetchers leave it). The conversion to BTC happens here, once, only for "sat".

    Args:
        tx: Transaction dict with 'vout' list containing 'value' in `value_unit`
        value_unit: "sat" or "btc"

    Returns:
        Estimated real volume in BTC
    """
    per_btc = _btc_per_unit(value_unit)
    outputs = tx.get("vout", [])

    if not outputs:
        return 0.0

    # Extract values, filtering out None
    values = []
    for out in outputs:
        value = out.get("value")
        if value is not None and value > 0:
            values.append(value)

    if not values:
        return 0.0

    if len(values) == 1:
        # Single output = no change (or coinbase)
        return values[0] / per_btc

    # Sort descending
    values.sort(reverse=True)

    if len(values) == 2:
        # For 2 outputs: check if smaller is likely change (<10% of larger)
        if values[0] > 0 and values[1] / values[0] < 0.1:
            # Second output is likely change
            return values[0] / per_btc
        # Both significant = multi-recipient payment
        return sum(values) / per_btc

    # For 3+ outputs: sum all except smallest (likely change)
    return sum(values[:-1]) / per_btc


def calculate_tx_volume(
    transactions: list[dict],
    utxoracle_price: float,
    confidence: float,
    timestamp: Optional[datetime] = None,
    value_unit: str = "sat",
) -> TxVolumeMetric:
    """
    Calculate total BTC and USD transaction volume.

    Args:
        transactions: List of transaction dicts with 'vout' containing outputs
        utxoracle_price: UTXOracle-derived BTC/USD price
        confidence: UTXOracle confidence score (0.0-1.0)
        timestamp: Optional timestamp for the metric (defaults to now)
        value_unit: unit of transactions[].vout[].value, "sat" (default) or "btc"

    Units of the result: tx_volume_btc in BTC, tx_volume_usd in USD (BTC * the price,
    utxoracle_price being USD per BTC).

    Returns:
        TxVolumeMetric with tx_count, tx_volume_btc, tx_volume_usd
    """
    if timestamp is None:
        timestamp = datetime.now()

    # Count transactions
    tx_count = len(transactions)

    # Calculate adjusted volume
    total_btc = 0.0
    for tx in transactions:
        total_btc += estimate_real_volume(tx, value_unit)

    # Calculate USD value
    tx_volume_usd = total_btc * utxoracle_price

    # Check confidence threshold
    low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

    return TxVolumeMetric(
        timestamp=timestamp,
        tx_count=tx_count,
        tx_volume_btc=total_btc,
        tx_volume_usd=tx_volume_usd,
        utxoracle_price_used=utxoracle_price,
        low_confidence=low_confidence,
    )
