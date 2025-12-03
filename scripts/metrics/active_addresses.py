"""
Active Addresses Metric (spec-007, User Story 2).

Counts unique addresses per block/day from transaction inputs and outputs.
Includes anomaly detection using 3-sigma from 30-day moving average.

Usage:
    from scripts.metrics.active_addresses import count_active_addresses, detect_anomaly
    result = count_active_addresses(transactions)
"""

from datetime import datetime
from statistics import mean, stdev
from typing import Optional
from scripts.models.metrics_models import ActiveAddressesMetric


def count_active_addresses(
    transactions: list[dict],
    block_height: int = 0,
    timestamp: Optional[datetime] = None,
) -> ActiveAddressesMetric:
    """
    Count unique active addresses from list of transactions.

    An address is "active" if it appears in any transaction input (sender)
    or output (receiver). OP_RETURN outputs are excluded (no address).

    Args:
        transactions: List of transaction dicts with 'vin' and 'vout'
        block_height: Bitcoin block height for the metric
        timestamp: Optional timestamp (defaults to now)

    Returns:
        ActiveAddressesMetric with unique sender/receiver counts
    """
    if timestamp is None:
        timestamp = datetime.now()

    senders = set()
    receivers = set()

    for tx in transactions:
        # Input addresses (senders) - may be None for coinbase tx
        for inp in tx.get("vin", []):
            prevout = inp.get("prevout", {})
            if addr := prevout.get("scriptpubkey_address"):
                senders.add(addr)

        # Output addresses (receivers) - exclude OP_RETURN (no address)
        for out in tx.get("vout", []):
            if addr := out.get("scriptpubkey_address"):
                receivers.add(addr)

    # Total unique = union of senders and receivers
    all_active = senders | receivers

    return ActiveAddressesMetric(
        timestamp=timestamp,
        block_height=block_height,
        active_addresses_block=len(all_active),
        unique_senders=len(senders),
        unique_receivers=len(receivers),
        is_anomaly=False,  # Set by detect_anomaly if needed
    )


def detect_anomaly(current_count: int, historical_counts: list[int]) -> bool:
    """
    Detect if current count is >3 sigma from moving average.

    Args:
        current_count: Current active address count
        historical_counts: List of historical counts (e.g., last 30 days)

    Returns:
        True if current_count > mean + 3*stdev, False otherwise
    """
    if len(historical_counts) < 2:
        # Not enough data for anomaly detection
        return False

    hist_mean = mean(historical_counts)
    hist_std = stdev(historical_counts)

    # Threshold = mean + 3*sigma
    threshold = hist_mean + 3 * hist_std

    return current_count > threshold
