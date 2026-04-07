from datetime import datetime, timezone
from typing import Dict, Any
import json

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/features/btc", tags=["features-btc"])

BUNDLE_CONTRACTS = {
    "core": {
        "bundle_id": "btc_core_live.v1",
        "payload_keys": {"live_snapshot", "metrics_latest"},
    },
    "flow": {
        "bundle_id": "btc_flow.v1",
        "payload_keys": {"whale_summary", "recent_whale_window", "absorption_rates"},
    },
    "macro": {
        "bundle_id": "btc_macro.v1",
        "payload_keys": {"macro_metrics", "source_metadata"},
    },
    "cohort": {
        "bundle_id": "btc_cohort.v1",
        "payload_keys": {
            "address_cohorts",
            "wallet_waves",
            "absorption_rates",
            "cost_basis",
        },
    },
}

def _empty_bundle(bundle_type: str) -> Dict[str, Any]:
    contract = BUNDLE_CONTRACTS[bundle_type]
    payload = {
        "metadata": {
            "schema_version": "v1",
            "bundle_id": contract["bundle_id"],
            "sequence_id": 0,
            "produced_at": datetime.now(timezone.utc).isoformat(),
            "bundle_status": "empty",
            "degraded_reasons": ["Database empty or not materialized"]
        }
    }
    for key in contract["payload_keys"]:
        payload[key] = {}
    return payload

@router.get("/{bundle_type}/latest")
async def get_bundle_latest(request: Request, bundle_type: str):
    if bundle_type not in BUNDLE_CONTRACTS:
        raise HTTPException(status_code=404, detail="Unknown bundle type")
        
    contract = BUNDLE_CONTRACTS[bundle_type]
    bundle_id = contract["bundle_id"]
    repo = getattr(request.app.state, "questdb_repo", None)
    
    if not repo:
        # Fall back to empty in case the table isn't created yet or connection fails
        return _empty_bundle(bundle_type) if "latest" in request.url.path else {"items": [], "pagination": {"next_page_token": None, "has_more": False}}
        
    try:
        row = await repo.get_latest_feature_bundle(bundle_id)
        if not row:
            return _empty_bundle(bundle_type)
            
        payload = json.loads(row["payload_json"])
        
        # Ensure metadata exists
        if "metadata" not in payload:
            payload["metadata"] = {
                "schema_version": "v1",
                "bundle_id": bundle_id,
                "sequence_id": row["sequence_id"],
                "produced_at": row["produced_at"].isoformat() if isinstance(row["produced_at"], datetime) else str(row["produced_at"]),
                "bundle_status": row["bundle_status"],
                "degraded_reasons": []
            }
            
        return payload
    except Exception as e:
        # Fall back to empty in case the table isn't created yet or connection fails
        return _empty_bundle(bundle_type)


@router.get("/{bundle_type}/history")
async def get_bundle_history(request: Request, bundle_type: str, limit: int = Query(default=50)):
    if bundle_type not in BUNDLE_CONTRACTS:
        raise HTTPException(status_code=404, detail="Unknown bundle type")
        
    contract = BUNDLE_CONTRACTS[bundle_type]
    bundle_id = contract["bundle_id"]
    repo = getattr(request.app.state, "questdb_repo", None)
    
    if not repo:
        # Fall back to empty in case the table isn't created yet or connection fails
        return _empty_bundle(bundle_type) if "latest" in request.url.path else {"items": [], "pagination": {"next_page_token": None, "has_more": False}}
        
    try:
        rows = await repo.get_feature_bundle_history(bundle_id, limit)
        if not rows:
            return {"items": [], "pagination": {"next_page_token": None, "has_more": False}}
            
        items = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if "metadata" not in payload:
                payload["metadata"] = {
                    "schema_version": "v1",
                    "bundle_id": bundle_id,
                    "sequence_id": row["sequence_id"],
                    "produced_at": row["produced_at"].isoformat() if isinstance(row["produced_at"], datetime) else str(row["produced_at"]),
                    "bundle_status": row["bundle_status"],
                    "degraded_reasons": []
                }
            items.append(payload)
            
        # The db query returns ORDER BY sequence_id DESC, produced_at DESC,
        # but the spec asks for oldest-to-newest ordering by default for history (T017)
        items.sort(key=lambda x: (x["metadata"]["sequence_id"], x["metadata"]["produced_at"]))
        
        return {"items": items, "pagination": {"next_page_token": None, "has_more": False}}
    except Exception as e:
        return {"items": [], "pagination": {"next_page_token": None, "has_more": False}}
