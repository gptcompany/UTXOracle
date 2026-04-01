from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python < 3.11 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        pass

from pydantic import BaseModel, ConfigDict

from scripts.nautilus_live.contract import TradableSnapshot


class GateState(StrEnum):
    STATUS_OK = "STATUS_OK"
    STATUS_LIQUIDATE_ONLY = "STATUS_LIQUIDATE_ONLY"
    STATUS_HALT = "STATUS_HALT"


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: GateState
    accepted: bool
    reason: str


@dataclass(frozen=True)
class GateConfig:
    ok_max_age_seconds: float
    liquidate_only_max_age_seconds: float
    ok_min_confidence: float
    liquidate_only_min_confidence: float
    ok_max_spread_bps: float
    liquidate_only_max_spread_bps: float
    required_sources: tuple[str, ...]
    liquidate_only_recovery_streak: int


class NautilusSafetyGate:
    def __init__(
        self,
        *,
        config: GateConfig,
        kill_switch_enabled: bool = False,
    ) -> None:
        self.config = config
        self.kill_switch_enabled = kill_switch_enabled
        self._last_seen_timestamp: datetime | None = None
        self._last_seen_block_height: int | None = None
        self._last_state: GateState | None = None
        self._healthy_recovery_streak = 0
        self._halted = False

    def reset(self) -> None:
        self._halted = False
        self._healthy_recovery_streak = 0
        self._last_state = None

    def evaluate(self, snapshot: TradableSnapshot, *, now: datetime) -> GateDecision:
        if self.kill_switch_enabled:
            self._healthy_recovery_streak = 0
            self._last_state = GateState.STATUS_HALT
            return GateDecision(
                state=GateState.STATUS_HALT,
                accepted=False,
                reason="operator_kill_switch",
            )

        if self._halted:
            self._last_state = GateState.STATUS_HALT
            return GateDecision(
                state=GateState.STATUS_HALT,
                accepted=False,
                reason="manual_reset_required",
            )

        monotonicity_error = self._check_monotonicity(snapshot)
        if monotonicity_error is not None:
            self._halted = True
            self._healthy_recovery_streak = 0
            self._last_state = GateState.STATUS_HALT
            return GateDecision(
                state=GateState.STATUS_HALT,
                accepted=False,
                reason=monotonicity_error,
            )

        base_state, reason = self._evaluate_base_state(snapshot, now=now)

        self._last_seen_timestamp = snapshot.timestamp
        self._last_seen_block_height = snapshot.block_height

        if base_state == GateState.STATUS_OK and self._last_state == GateState.STATUS_LIQUIDATE_ONLY:
            self._healthy_recovery_streak += 1
            if self._healthy_recovery_streak < self.config.liquidate_only_recovery_streak:
                state = GateState.STATUS_LIQUIDATE_ONLY
                reason = (
                    f"recovery_in_progress:{self._healthy_recovery_streak}"
                    f"_of_{self.config.liquidate_only_recovery_streak}"
                )
            else:
                state = GateState.STATUS_OK
                reason = "ok"
        else:
            state = base_state
            self._healthy_recovery_streak = 0

        if state == GateState.STATUS_HALT:
            self._halted = True

        self._last_state = state
        return GateDecision(
            state=state,
            accepted=state in (GateState.STATUS_OK, GateState.STATUS_LIQUIDATE_ONLY),
            reason=reason,
        )

    def _check_monotonicity(self, snapshot: TradableSnapshot) -> str | None:
        if self._last_seen_timestamp is not None and snapshot.timestamp <= self._last_seen_timestamp:
            return "timestamp_not_monotonic"
        if (
            self._last_seen_block_height is not None
            and snapshot.block_height is not None
            and snapshot.block_height < self._last_seen_block_height
        ):
            return "block_height_moved_backward"
        return None

    def _evaluate_base_state(self, snapshot: TradableSnapshot, *, now: datetime) -> tuple[GateState, str]:
        age_seconds = (now - snapshot.timestamp).total_seconds()
        if age_seconds > self.config.liquidate_only_max_age_seconds:
            return GateState.STATUS_HALT, "snapshot_stale"
        if age_seconds > self.config.ok_max_age_seconds:
            return GateState.STATUS_LIQUIDATE_ONLY, "snapshot_stale_borderline"

        for source_name in self.config.required_sources:
            status = snapshot.required_source_statuses.get(source_name)
            if status != "healthy":
                return GateState.STATUS_HALT, f"required_source_unhealthy:{source_name}"

        if snapshot.utxoracle_confidence < self.config.liquidate_only_min_confidence:
            return GateState.STATUS_HALT, "confidence_too_low"
        if snapshot.utxoracle_confidence < self.config.ok_min_confidence:
            return GateState.STATUS_LIQUIDATE_ONLY, "confidence_borderline"

        if snapshot.source_spread_bps > self.config.liquidate_only_max_spread_bps:
            return GateState.STATUS_HALT, "spread_bps_too_high"
        if snapshot.source_spread_bps > self.config.ok_max_spread_bps:
            return GateState.STATUS_LIQUIDATE_ONLY, "spread_bps_borderline"

        return GateState.STATUS_OK, "ok"
