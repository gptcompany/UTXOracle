from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from scripts.nautilus_live.client import LiveSnapshotPollingClient
from scripts.nautilus_live.contract import TradableSnapshot, normalize_live_snapshot
from scripts.nautilus_live.gates import GateDecision, NautilusSafetyGate


DecisionLogger = Callable[[dict[str, object]], None]
KillSwitchCheck = Callable[[], bool]


class AdapterMode(StrEnum):
    SHADOW_READ = "shadow_read"
    PAPER_TRADE = "paper_trade"


class NautilusLiveAdapter:
    def __init__(
        self,
        *,
        client: LiveSnapshotPollingClient,
        gate: NautilusSafetyGate,
        mode: AdapterMode = AdapterMode.SHADOW_READ,
        decision_logger: DecisionLogger | None = None,
        kill_switch_check: KillSwitchCheck | None = None,
    ) -> None:
        self.client = client
        self.gate = gate
        self.mode = mode
        self.decision_logger = decision_logger
        self.kill_switch_check = kill_switch_check

    async def poll_once(
        self,
        *,
        now: datetime,
    ) -> tuple[TradableSnapshot, GateDecision] | None:
        if self._kill_switch_active():
            self._log_decision(
                {
                    "mode": self.mode.value,
                    "state": "STATUS_HALT",
                    "accepted": False,
                    "reason": "operator_kill_switch",
                }
            )
            return None

        snapshot = await self.client.fetch_snapshot()
        return self._process_snapshot(snapshot, now=now)

    async def replay_recent_history(
        self,
        *,
        minutes: int,
        now: datetime,
    ) -> list[tuple[TradableSnapshot, GateDecision]]:
        if self._kill_switch_active():
            self._log_decision(
                {
                    "mode": self.mode.value,
                    "state": "STATUS_HALT",
                    "accepted": False,
                    "reason": "operator_kill_switch",
                }
            )
            return []

        snapshots = await self.client.fetch_history(minutes=minutes)
        results: list[tuple[TradableSnapshot, GateDecision]] = []
        for snapshot in snapshots:
            result = self._process_snapshot(snapshot, now=now)
            if result is not None:
                results.append(result)
        return results

    async def aclose(self) -> None:
        await self.client.aclose()

    def _process_snapshot(
        self,
        snapshot,
        *,
        now: datetime,
    ) -> tuple[TradableSnapshot, GateDecision] | None:
        try:
            normalized = normalize_live_snapshot(snapshot)
        except ValueError as exc:
            self._log_decision(
                {
                    "mode": self.mode.value,
                    "state": "STATUS_HALT",
                    "accepted": False,
                    "reason": f"normalization_failed:{exc}",
                }
            )
            return None

        decision = self.gate.evaluate(normalized, now=now)
        self._log_decision(
            {
                "mode": self.mode.value,
                "timestamp": normalized.timestamp.isoformat(),
                "block_height": normalized.block_height,
                "state": str(decision.state),
                "accepted": decision.accepted,
                "reason": decision.reason,
            }
        )
        return normalized, decision

    def _log_decision(self, event: dict[str, object]) -> None:
        if self.decision_logger is not None:
            self.decision_logger(event)

    def _kill_switch_active(self) -> bool:
        if self.kill_switch_check is None:
            return False
        return bool(self.kill_switch_check())
