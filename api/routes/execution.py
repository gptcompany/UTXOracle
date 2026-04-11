import yaml
from pathlib import Path
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Tuple, List

from fastapi import APIRouter, Request, Depends

from api.models.execution import (
    ExecutionMode,
    CompatibilityStatus,
    OperatorStage,
    ExecutionStatus,
    FreshnessSummary,
    SequenceSummary,
)
from api.routes.live import (
    get_live_snapshot_store,
    _call_store,
    _build_live_health_summary_from_snapshot,
)
from scripts.live.storage import LiveSnapshotStore

router = APIRouter(prefix="/api/execution/btc", tags=["execution-btc"])
logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"
EXECUTION_SAFETY_PATH = DOCS_DIR / "contracts" / "execution_safety.yaml"
HEALTHY_INPUT_STATUSES = {"healthy", "ok"}


def _coerce_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        produced_at = value
    else:
        try:
            produced_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return fallback

    if produced_at.tzinfo is None:
        produced_at = produced_at.replace(tzinfo=timezone.utc)
    return produced_at


def _is_healthy_status(value: Any) -> bool:
    return str(value).lower() in HEALTHY_INPUT_STATUSES


def _coerce_sequence_id(
    row: dict[str, Any],
    key: str,
    gaps_detected: List[str],
) -> int | None:
    value = row.get("sequence_id")
    if value is None:
        gaps_detected.append(f"{key}_sequence_missing")
        return None

    try:
        sequence_id = int(value)
    except (TypeError, ValueError):
        gaps_detected.append(f"{key}_sequence_invalid")
        return None

    if sequence_id < 1:
        gaps_detected.append(f"{key}_sequence_invalid")
        return None

    return sequence_id


def _check_recent_sequence_rows(
    key: str,
    rows: list[dict[str, Any]],
    gaps_detected: List[str],
) -> bool:
    if not rows:
        gaps_detected.append(f"{key}_sequence_missing")
        return False

    latest_sequence_id = _coerce_sequence_id(rows[0], key, gaps_detected)
    if latest_sequence_id is None:
        return False

    if len(rows) < 2:
        return True

    previous_sequence_id = _coerce_sequence_id(rows[1], key, gaps_detected)
    if previous_sequence_id is None:
        return False

    if latest_sequence_id <= previous_sequence_id:
        gaps_detected.append(f"{key}_sequence_non_monotonic")
        return False

    if latest_sequence_id - previous_sequence_id > 1:
        gaps_detected.append(f"{key}_sequence_gap")
        return False

    return True


def _get_operator_stage() -> Tuple[OperatorStage, ExecutionMode]:
    try:
        with open(EXECUTION_SAFETY_PATH, "r") as f:
            data = yaml.safe_load(f)
        stage_str = data.get("operator_stage", "shadow")
        stage = OperatorStage(stage_str)
        max_mode_str = (
            data.get("operator_stages", {})
            .get(stage_str, {})
            .get("max_execution_mode", "observe_only")
        )
        max_mode = ExecutionMode(max_mode_str)
        return stage, max_mode
    except Exception as exc:
        logger.warning(
            f"Failed to read operator stage from {EXECUTION_SAFETY_PATH}: {exc}"
        )
        return OperatorStage.shadow, ExecutionMode.observe_only


@router.get("/status", response_model=ExecutionStatus)
async def get_execution_status(
    request: Request,
    store: LiveSnapshotStore = Depends(get_live_snapshot_store),
) -> ExecutionStatus:
    now = datetime.now(timezone.utc)

    # 1. Fetch operator stage
    operator_stage, max_execution_mode = _get_operator_stage()

    # Defaults for failures
    stale_inputs: List[str] = []
    gaps_detected: List[str] = []
    input_refs: Dict[str, str] = {}
    is_fresh = True
    is_monotonic = True

    try:
        # 2. Check /health and snapshot
        snapshot = await _call_store(store, "get_latest")
        health_summary = _build_live_health_summary_from_snapshot(snapshot)

        if health_summary.get("status") != "healthy":
            stale_inputs.append("health")
            is_fresh = False

        if not snapshot:
            stale_inputs.append("live_snapshot")
            is_fresh = False
        else:
            snap_age = (now - snapshot.timestamp).total_seconds()
            input_refs["live_snapshot"] = snapshot.timestamp.isoformat()
            if snap_age >= 30:
                stale_inputs.append("live_snapshot")
                is_fresh = False

        # 3. Check features and signals from QuestDB
        repo = getattr(request.app.state, "questdb_repo", None)
        if not repo:
            stale_inputs.extend(
                [
                    "core_feature",
                    "flow_feature",
                    "macro_feature",
                    "cohort_feature",
                    "signal",
                ]
            )
            is_fresh = False
        else:
            # Check bundles
            bundles_to_check = {
                "core_feature": "btc_core_live.v1",
                "flow_feature": "btc_flow.v1",
                "macro_feature": "btc_macro.v1",
                "cohort_feature": "btc_cohort.v1",
            }

            for key, bundle_id in bundles_to_check.items():
                row = await repo.get_latest_feature_bundle(bundle_id)
                if not row:
                    stale_inputs.append(key)
                    is_fresh = False
                    continue

                produced_at = _coerce_datetime(row["produced_at"], now)

                bundle_age = (now - produced_at).total_seconds()
                input_refs[key] = produced_at.isoformat()

                if bundle_age >= 60:
                    stale_inputs.append(key)
                    is_fresh = False

                if not _is_healthy_status(row.get("bundle_status")):
                    stale_inputs.append(f"{key}_status_not_ok")
                    is_fresh = False

                recent_rows = await repo.get_recent_feature_bundle_sequence(bundle_id, 2)
                if not _check_recent_sequence_rows(key, recent_rows or [row], gaps_detected):
                    is_monotonic = False
                else:
                    input_refs[f"{key}_sequence_id"] = str(
                        recent_rows[0]["sequence_id"] if recent_rows else row["sequence_id"]
                    )

            # Check signals
            sig_row = await repo.get_latest_signal_snapshot()
            if not sig_row:
                stale_inputs.append("signal")
                is_fresh = False
            else:
                sig_produced_at = _coerce_datetime(sig_row["produced_at"], now)

                sig_age = (now - sig_produced_at).total_seconds()
                input_refs["signal"] = sig_produced_at.isoformat()

                if sig_age >= 60:
                    stale_inputs.append("signal")
                    is_fresh = False

                if not _is_healthy_status(sig_row.get("service_status")):
                    stale_inputs.append("signal_status_not_ok")
                    is_fresh = False

                recent_signal_rows = await repo.get_recent_signal_sequence(2)
                if not _check_recent_sequence_rows("signal", recent_signal_rows or [sig_row], gaps_detected):
                    is_monotonic = False
                else:
                    input_refs["signal_sequence_id"] = str(
                        recent_signal_rows[0]["sequence_id"] if recent_signal_rows else sig_row["sequence_id"]
                    )

        # Compute Mode
        if not is_fresh or not is_monotonic:
            mode = ExecutionMode.halted
            reason = f"Fail-closed due to degraded inputs: stale={stale_inputs}, gaps={gaps_detected}"
        else:
            # All good, use the max allowed by operator stage
            mode = max_execution_mode
            reason = f"All tier-1 inputs healthy and fresh. Operating at max mode for stage: {operator_stage.value}"

    except Exception as exc:
        logger.exception("Execution derivation failed: %s", exc)
        mode = ExecutionMode.halted
        reason = f"Internal error during execution derivation: {exc}"
        is_fresh = False
        stale_inputs.append("internal_error")

    # Map compatibility status
    if mode == ExecutionMode.trade_enabled:
        comp_status = CompatibilityStatus.STATUS_OK
    elif mode == ExecutionMode.manage_only:
        comp_status = CompatibilityStatus.STATUS_LIQUIDATE_ONLY
    else:
        comp_status = CompatibilityStatus.STATUS_HALT

    return ExecutionStatus(
        execution_mode=mode,
        status_reason=reason,
        compatibility_status=comp_status,
        evaluated_at=now,
        input_refs=input_refs,
        freshness_summary=FreshnessSummary(
            is_fresh=is_fresh, stale_inputs=stale_inputs
        ),
        sequence_summary=SequenceSummary(
            is_monotonic=is_monotonic, gaps_detected=gaps_detected
        ),
        restatement_status="none",
        operator_stage=operator_stage,
    )
