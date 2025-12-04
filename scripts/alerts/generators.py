"""
Event generators for the Webhook Alert System.

Factory functions to create AlertEvent objects for different event types:
- Whale movements
- Trading signals
- Regime changes
- Price divergence
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import AlertEvent


def create_whale_event(
    amount_btc: float,
    direction: str,
    signal_vote: float,
    exchange: str | None = None,
    usd_value: float | None = None,
) -> AlertEvent:
    """
    Create a whale movement alert event.

    Args:
        amount_btc: Amount of BTC moved
        direction: "INFLOW" or "OUTFLOW"
        signal_vote: Signal vote from -1.0 to +1.0
        exchange: Exchange name if known
        usd_value: USD value of the movement

    Returns:
        AlertEvent with whale payload
    """
    # Determine severity based on amount
    if amount_btc > 1000:
        severity = "critical"
    elif amount_btc > 500:
        severity = "high"
    elif amount_btc > 100:
        severity = "medium"
    else:
        severity = "low"

    payload: dict[str, Any] = {
        "amount_btc": amount_btc,
        "direction": direction,
        "signal_vote": signal_vote,
    }

    if exchange is not None:
        payload["exchange"] = exchange
    if usd_value is not None:
        payload["usd_value"] = usd_value

    return AlertEvent(
        event_id=str(uuid4()),
        event_type="whale",
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        payload=payload,
    )


def create_signal_event(
    action: str,
    confidence: float,
    signal_mean: float,
    top_contributors: list[dict[str, Any]],
) -> AlertEvent | None:
    """
    Create a trading signal alert event.

    Args:
        action: "BUY", "SELL", or "HOLD"
        confidence: Confidence score from 0.0 to 1.0
        signal_mean: Mean signal value from -1.0 to +1.0
        top_contributors: List of {name, value} dicts

    Returns:
        AlertEvent with signal payload, or None if action is HOLD
    """
    # Exclude HOLD signals - not actionable
    if action == "HOLD":
        return None

    # Determine severity based on confidence
    if confidence > 0.95:
        severity = "critical"
    elif confidence > 0.85:
        severity = "high"
    elif confidence > 0.70:
        severity = "medium"
    else:
        severity = "low"

    return AlertEvent(
        event_id=str(uuid4()),
        event_type="signal",
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        payload={
            "action": action,
            "confidence": confidence,
            "signal_mean": signal_mean,
            "top_contributors": top_contributors,
        },
    )


def create_regime_event(
    metric: str,
    from_state: str,
    to_state: str,
    details: dict[str, Any],
    implication: str,
) -> AlertEvent | None:
    """
    Create a regime change alert event.

    Args:
        metric: Metric name (e.g., "power_law", "symbolic", "wasserstein")
        from_state: Previous regime state
        to_state: New regime state
        details: Metric-specific details
        implication: Human-readable interpretation

    Returns:
        AlertEvent with regime payload, or None if no change
    """
    # No event if state hasn't changed
    if from_state == to_state:
        return None

    # Regime changes are generally medium severity
    # Could be enhanced based on the specific regime transition
    severity = "medium"

    return AlertEvent(
        event_id=str(uuid4()),
        event_type="regime",
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        payload={
            "metric": metric,
            "from_state": from_state,
            "to_state": to_state,
            "details": details,
            "implication": implication,
        },
    )


def create_price_event(
    utxoracle_price: float,
    exchange_price: float,
    divergence_pct: float,
) -> AlertEvent:
    """
    Create a price divergence alert event.

    Args:
        utxoracle_price: UTXOracle calculated price
        exchange_price: Exchange reported price
        divergence_pct: Percentage divergence (positive = UTXOracle higher)

    Returns:
        AlertEvent with price payload
    """
    direction = "ABOVE" if utxoracle_price >= exchange_price else "BELOW"

    # Price divergence is generally low severity (informational)
    severity = "low"

    return AlertEvent(
        event_id=str(uuid4()),
        event_type="price",
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        payload={
            "utxoracle_price": utxoracle_price,
            "exchange_price": exchange_price,
            "divergence_pct": divergence_pct,
            "direction": direction,
        },
    )
