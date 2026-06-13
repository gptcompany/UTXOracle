"""Derived scalar features from URPD / cost-basis distributions.

This module intentionally compresses the full histogram into a small set of
stable features that are easier to store, expose, and backtest.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from scripts.metrics.urpd import calculate_urpd
from scripts.models.metrics_models import URPDFeaturesResult


def _normalized_entropy(percentages: list[float]) -> float:
    """Return Shannon entropy normalized to [0, 1]."""
    positive = [pct / 100.0 for pct in percentages if pct > 0]
    if len(positive) <= 1:
        return 0.0

    entropy = -sum(probability * math.log(probability) for probability in positive)
    max_entropy = math.log(len(positive))
    if max_entropy <= 0:
        return 0.0
    return entropy / max_entropy


def calculate_urpd_features_signal(
    conn,
    current_price_usd: Optional[float],
    current_block: int,
    *,
    bucket_size_usd: float = 5000.0,
    timestamp: Optional[datetime] = None,
    availability_timestamp: Optional[datetime] = None,
    schema_version: str = "urpd_features_daily.v1",
    source_health: Optional[dict] = None,
) -> URPDFeaturesResult:
    """Calculate scalar features from the current URPD snapshot."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    if availability_timestamp is None:
        availability_timestamp = datetime.utcnow()

    has_current_price = current_price_usd is not None and current_price_usd > 0
    urpd_price = float(current_price_usd) if has_current_price else 1.0

    urpd = calculate_urpd(
        conn=conn,
        current_price_usd=urpd_price,
        bucket_size_usd=bucket_size_usd,
        block_height=current_block,
    )

    has_distribution = bool(urpd.buckets) and urpd.total_supply_btc > 0
    top_bucket_concentration = None
    dominant_bucket_distance_pct = None
    entropy = None
    supply_below_price_pct = None
    supply_above_price_pct = None

    if has_distribution and urpd.dominant_bucket is not None:
        top_bucket_concentration = urpd.dominant_bucket.percentage

    if has_distribution and urpd.dominant_bucket is not None and has_current_price:
        dominant_midpoint = (
            urpd.dominant_bucket.price_low + urpd.dominant_bucket.price_high
        ) / 2.0
        dominant_bucket_distance_pct = (
            (dominant_midpoint - float(current_price_usd)) / float(current_price_usd)
        ) * 100.0

    if has_distribution:
        entropy = _normalized_entropy([bucket.percentage for bucket in urpd.buckets])

    if has_distribution and has_current_price:
        supply_below_price_pct = urpd.supply_below_price_pct
        supply_above_price_pct = urpd.supply_above_price_pct

    if has_distribution and has_current_price:
        confidence = 0.85
    elif has_distribution:
        confidence = 0.5
    else:
        confidence = 0.0

    health = dict(source_health or {})
    health.setdefault(
        "status",
        "healthy" if has_distribution and has_current_price else "degraded",
    )
    health.setdefault("has_current_price", has_current_price)
    health.setdefault("priced_bucket_count", len(urpd.buckets))
    health.setdefault("priced_supply_btc", urpd.total_supply_btc)
    total_supply_btc = urpd.total_supply_btc
    if not has_distribution and health.get("visible_utxos", 0) > 0:
        total_supply_btc = None

    return URPDFeaturesResult(
        supply_below_price_pct=supply_below_price_pct,
        supply_above_price_pct=supply_above_price_pct,
        top_bucket_concentration=top_bucket_concentration,
        dominant_bucket_distance_pct=dominant_bucket_distance_pct,
        distribution_entropy=entropy,
        current_price_usd=float(current_price_usd) if has_current_price else None,
        bucket_size_usd=bucket_size_usd,
        total_supply_btc=total_supply_btc,
        block_height=current_block,
        timestamp=timestamp,
        availability_timestamp=availability_timestamp,
        confidence=confidence,
        schema_version=schema_version,
        source_health=health,
    )
