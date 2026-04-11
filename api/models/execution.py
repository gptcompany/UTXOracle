from enum import Enum
from datetime import datetime
from typing import Dict, List
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    halted = "halted"
    warming_up = "warming_up"
    observe_only = "observe_only"
    manage_only = "manage_only"
    trade_enabled = "trade_enabled"


class CompatibilityStatus(str, Enum):
    STATUS_OK = "STATUS_OK"
    STATUS_LIQUIDATE_ONLY = "STATUS_LIQUIDATE_ONLY"
    STATUS_HALT = "STATUS_HALT"


class OperatorStage(str, Enum):
    shadow = "shadow"
    paper_live = "paper_live"
    canary_capital = "canary_capital"
    full_capital = "full_capital"


class FreshnessSummary(BaseModel):
    is_fresh: bool = Field(
        description="True if all required inputs are within freshness bounds"
    )
    stale_inputs: List[str] = Field(
        default_factory=list,
        description="List of inputs that exceeded freshness limits",
    )


class SequenceSummary(BaseModel):
    is_monotonic: bool = Field(
        description="True if all sequence IDs are monotonically increasing without gaps"
    )
    gaps_detected: List[str] = Field(
        default_factory=list,
        description="List of inputs where sequence gaps were detected",
    )


class ExecutionStatus(BaseModel):
    execution_mode: ExecutionMode = Field(
        description="The primary and authoritative execution state"
    )
    status_reason: str = Field(
        description="Human-readable reason for the current execution mode"
    )
    compatibility_status: CompatibilityStatus = Field(
        description="Legacy spec-043 adapter status for older consumers"
    )
    evaluated_at: datetime = Field(
        description="Timestamp when this execution decision was derived"
    )
    input_refs: Dict[str, str] = Field(
        description="References to the tier-1 inputs evaluated, usually their timestamps or sequence IDs"
    )
    freshness_summary: FreshnessSummary = Field(
        description="Summary of input freshness evaluation"
    )
    sequence_summary: SequenceSummary = Field(
        description="Summary of sequence continuity evaluation"
    )
    restatement_status: str = Field(
        default="none", description="Tracks unresolved critical restatements"
    )
    operator_stage: OperatorStage = Field(
        description="The current capital rollout stage configured by the operator"
    )
