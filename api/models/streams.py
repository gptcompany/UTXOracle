"""Pydantic models for the consumer-facing streams contract (spec-061).

Wire-level shape is defined in
`specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml`
and the conceptual shape in `data-model.md`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StreamStatus(str, Enum):
    """Per-stream freshness verdict.

    OK      = fresh within SLA
    STALE   = table has rows but most recent is past SLA
    MISSING = table empty OR backend query failed (use `error` to distinguish;
              consumer treats both as block-strict-mode)
    """

    OK = "OK"
    STALE = "STALE"
    MISSING = "MISSING"


class OverallStatus(str, Enum):
    """Rollup verdict for the whole registry.

    OK iff every stream is OK; DEGRADED otherwise.
    """

    OK = "OK"
    DEGRADED = "DEGRADED"


class StreamHealthReading(BaseModel):
    """One stream's runtime freshness snapshot.

    For `freshness_strategy = max_ts`, `last_row_ts` is the result of
    `SELECT max(timestamp_column) FROM table`. For `tip_lag_blocks`,
    `last_row_ts` is always None because block lag is the authoritative
    signal and no per-row timestamp meaning exists.
    """

    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(
        ...,
        description="Contract stream identifier (matches `name` in stream_registry.yaml).",
    )
    last_row_ts: Optional[datetime] = Field(
        None,
        description=(
            "UTC ISO-8601 timestamp of the most recent row for max_ts streams; "
            "null for MISSING or tip_lag_blocks strategy."
        ),
    )
    stale_seconds: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Strategy-derived staleness in seconds; null when MISSING. "
            "For max_ts: now() - last_row_ts. "
            "For tip_lag_blocks: (current_tip - max(block_column)) * 600."
        ),
    )
    sla_seconds: int = Field(
        ..., gt=0, description="Maximum allowed staleness from the registry."
    )
    schema_version: str = Field(
        ..., description="SemVer of the stream's contract shape."
    )
    status: StreamStatus
    error: Optional[str] = Field(
        None,
        description=(
            "Optional diagnostic message when status is MISSING due to a backend "
            "failure. Consumer SHOULD NOT branch on this field."
        ),
    )


class StreamsHealthResponse(BaseModel):
    """Top-level response body of GET /v1/streams/health.

    Contract: `overall == OK` iff every `streams[i].status == OK`.
    """

    model_config = ConfigDict(use_enum_values=True)

    as_of: datetime = Field(..., description="Server clock at rollup time.")
    streams: List[StreamHealthReading] = Field(
        ...,
        min_length=1,
        description=(
            "One entry per registry stream. The exact-13 constraint is enforced "
            "by tests/test_stream_registry.py and by the endpoint at runtime, not "
            "by the wire schema, so future registry versions can extend without "
            "an OpenAPI bump."
        ),
    )
    overall: OverallStatus
