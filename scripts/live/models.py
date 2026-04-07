from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceStatus = Literal["healthy", "degraded", "stale", "unavailable"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_ISO_FRACTION_TRIM_RE = re.compile(r"(\.\d{6})\d+(?=(?:[+-]\d{2}:\d{2})?$)")


def coerce_utc_datetime(value: datetime | str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000.0 if value > 1_000_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        normalized = _ISO_FRACTION_TRIM_RE.sub(r"\1", normalized)
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class SourceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SourceStatus
    latency_ms: float | None = Field(default=None, ge=0)
    last_success: datetime | None = None
    last_error: str | None = None
    observed_height: int | None = Field(default=None, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("last_success", mode="before")
    @classmethod
    def _normalize_last_success(
        cls, value: datetime | str | int | float | None
    ) -> datetime | None:
        return coerce_utc_datetime(value)


class LiveFeatureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brk_realized_price: float | None = Field(default=None, gt=0)
    brk_liveliness: float | None = Field(default=None, ge=0, le=1)
    brk_reserve_risk: float | None = Field(default=None, ge=0)
    brk_nupl: float | None = Field(default=None, ge=-1, le=1)
    brk_sopr: float | None = Field(default=None, ge=0)


class LiveComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utxo_vs_mempool_bps: float | None = None
    utxo_vs_hl_oracle_bps: float | None = None
    utxo_vs_hl_mark_bps: float | None = None


class HyperliquidPriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["api", "filesystem"]
    timestamp: datetime = Field(default_factory=utc_now)
    oracle_price: float | None = Field(default=None, gt=0)
    mark_price: float | None = Field(default=None, gt=0)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(
        cls, value: datetime | str | int | float | None
    ) -> datetime | None:
        return coerce_utc_datetime(value)


class OracleObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=utc_now)
    price: float | None = Field(default=None, gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(
        cls, value: datetime | str | int | float | None
    ) -> datetime | None:
        return coerce_utc_datetime(value)


class LiveComparisonSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    block_height: int | None = Field(default=None, ge=0)
    utxoracle_price: float | None = Field(default=None, gt=0)
    mempool_exchange_price: float | None = Field(default=None, gt=0)
    hyperliquid_oracle_price: float | None = Field(default=None, gt=0)
    hyperliquid_mark_price: float | None = Field(default=None, gt=0)
    comparison: LiveComparison = Field(default_factory=LiveComparison)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(
        cls, value: datetime | str | int | float | None
    ) -> datetime | None:
        return coerce_utc_datetime(value)


class LiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="v1")
    timestamp: datetime = Field(default_factory=utc_now)
    block_height: int | None = Field(default=None, ge=0)
    utxoracle_price: float | None = Field(default=None, gt=0)
    utxoracle_confidence: float | None = Field(default=None, ge=0, le=1)
    mempool_exchange_price: float | None = Field(default=None, gt=0)
    hyperliquid_oracle_price: float | None = Field(default=None, gt=0)
    hyperliquid_mark_price: float | None = Field(default=None, gt=0)
    comparison: LiveComparison = Field(default_factory=LiveComparison)
    features: LiveFeatureSet = Field(default_factory=LiveFeatureSet)
    source_health: dict[str, SourceHealth] = Field(default_factory=dict)
    source_timestamps: dict[str, datetime | None] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(
        cls, value: datetime | str | int | float | None
    ) -> datetime | None:
        return coerce_utc_datetime(value)

    @field_validator("source_timestamps", mode="before")
    @classmethod
    def _normalize_source_timestamps(
        cls, value: dict[str, datetime | str | int | float | None] | None
    ) -> dict[str, datetime | None]:
        if value is None:
            return {}
        return {key: coerce_utc_datetime(item) for key, item in value.items()}


class LiveHistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes: int = Field(default=60, ge=1, le=24 * 60)
