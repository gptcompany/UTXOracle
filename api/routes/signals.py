from datetime import datetime, timezone
import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/signals/btc", tags=["signals-btc"])
logger = logging.getLogger(__name__)

def _empty_signal() -> Dict[str, Any]:
    return {
        "schema_version": "v1",
        "sequence_id": 0,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "block_height": 0,
        "service_status": "empty",
        "bias": "neutral",
        "conviction": 0.0,
        "regime_score": 0.0,
        "flow_score": 0.0,
        "valuation_score": 0.0,
        "quality_score": 0.0,
        "degraded_reasons": ["Database empty or not materialized"],
        "input_refs": {
            "core_sequence_id": 0,
            "flow_sequence_id": 0,
            "macro_sequence_id": 0,
            "cohort_sequence_id": 0,
        },
        "component_details": {}
    }


def _misconfigured_signal(reason: str) -> Dict[str, Any]:
    payload = _empty_signal()
    payload["service_status"] = "misconfigured"
    payload["degraded_reasons"] = [reason]
    return payload

@router.get("/latest")
async def get_signal_latest(request: Request):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        return _misconfigured_signal("QuestDB repository unavailable")
        
    try:
        row = await repo.get_latest_signal_snapshot()
        if not row:
            return _empty_signal()
            
        payload = json.loads(row["payload_json"])
        
        # Ensure top-level metadata exists in case not fully stored in JSON
        payload["schema_version"] = "v1"
        payload["sequence_id"] = row["sequence_id"]
        payload["produced_at"] = row["produced_at"].isoformat() if isinstance(row["produced_at"], datetime) else str(row["produced_at"])
        payload["service_status"] = row["service_status"]
            
        return payload
    except Exception as exc:
        logger.exception("Failed to fetch latest signal snapshot: %s", exc)
        return _misconfigured_signal("Failed to fetch signal snapshot from QuestDB")

@router.get("/history")
async def get_signal_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    page_token: int | None = Query(default=None, ge=0),
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB repository unavailable")
        
    try:
        rows = await repo.get_signal_snapshot_history(limit + 1, page_token)
        if not rows:
            return {"items": [], "pagination": {"next_page_token": None, "has_more": False}}
            
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
            
        items = []
        for row in visible_rows:
            payload = json.loads(row["payload_json"])
            payload["schema_version"] = "v1"
            payload["sequence_id"] = row["sequence_id"]
            payload["produced_at"] = row["produced_at"].isoformat() if isinstance(row["produced_at"], datetime) else str(row["produced_at"])
            payload["service_status"] = row["service_status"]
            items.append(payload)
            
        items.sort(key=lambda x: (x["sequence_id"], x["produced_at"]))
        
        next_page_token = str(items[-1]["sequence_id"]) if has_more and items else None
        
        return {"items": items, "pagination": {"next_page_token": next_page_token, "has_more": has_more}}
    except Exception as exc:
        logger.exception("Failed to fetch signal snapshot history: %s", exc)
        raise HTTPException(status_code=503, detail="Failed to fetch signal history")
