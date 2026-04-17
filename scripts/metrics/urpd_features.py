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
    current_price_usd: float,
    current_block: int,
    *,
    bucket_size_usd: float = 5000.0,
    timestamp: Optional[datetime] = None,
) -> URPDFeaturesResult:
    """Calculate scalar features from the current URPD snapshot."""
    if timestamp is None:
        timestamp = datetime.utcnow()

    urpd = calculate_urpd(
        conn=conn,
        current_price_usd=current_price_usd,
        bucket_size_usd=bucket_size_usd,
        block_height=current_block,
    )

    top_cluster_concentration = (
        urpd.dominant_bucket.percentage if urpd.dominant_bucket is not None else 0.0
    )
    if urpd.dominant_bucket is not None and current_price_usd > 0:
        dominant_midpoint = (
            urpd.dominant_bucket.price_low + urpd.dominant_bucket.price_high
        ) / 2.0
        dominant_bucket_distance_pct = (
            (dominant_midpoint - current_price_usd) / current_price_usd
        ) * 100.0
    else:
        dominant_bucket_distance_pct = 0.0

    entropy = _normalized_entropy([bucket.percentage for bucket in urpd.buckets])

    if urpd.total_supply_btc > 0 and urpd.buckets:
        confidence = 0.85
    elif urpd.buckets:
        confidence = 0.5
    else:
        confidence = 0.0

    return URPDFeaturesResult(
        supply_below_price_pct=urpd.supply_below_price_pct,
        supply_above_price_pct=urpd.supply_above_price_pct,
        top_cluster_concentration=top_cluster_concentration,
        dominant_bucket_distance_pct=dominant_bucket_distance_pct,
        distribution_entropy=entropy,
        current_price_usd=current_price_usd,
        bucket_size_usd=bucket_size_usd,
        total_supply_btc=urpd.total_supply_btc,
        block_height=current_block,
        timestamp=timestamp,
        confidence=confidence,
    )
