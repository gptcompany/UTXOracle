from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/entities", tags=["entities"])

@router.get("/flows")
async def get_entity_flows(
    request: Request,
    min_value: float = Query(default=0.0),
    classification: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500)
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")
        
    rows = await repo.get_entity_flows(min_value, limit)
    
    items = []
    for row in rows:
        items.append({
            "entity_id": row["entity_id"],
            "date": row["date"].isoformat() if isinstance(row["date"], datetime) else str(row["date"]),
            "inflow_btc": row["inflow_btc"],
            "outflow_btc": row["outflow_btc"],
            "netflow_btc": row["netflow_btc"],
            "is_exchange": row["is_exchange"]
        })
        
    return {
        "items": items,
        "service_status": "healthy",
        "pagination": {"next_page_token": None, "has_more": False}
    }

@router.get("/{entity_id}")
async def get_entity_metadata(request: Request, entity_id: str):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")
        
    row = await repo.get_entity_metadata(entity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Entity not found")
        
    return {
        "entity_id": row["entity_id"],
        "entity_kind": row["entity_kind"],
        "registry_status": row["registry_status"],
        "display_label": row["display_label"],
        "confidence_overall": row["confidence_overall"],
        "last_seen": row["last_seen"].isoformat() if isinstance(row["last_seen"], datetime) else str(row["last_seen"]),
        "labels": [], # Detailed labels would require joining entity_labels
        "provenance_summary": {} # Provenance summary would require joining provenance table
    }

@router.get("/{entity_id}/history")
async def get_entity_history(
    request: Request, 
    entity_id: str,
    limit: int = Query(default=50, ge=1, le=500)
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")
        
    rows = await repo.get_entity_history(entity_id, limit)
    
    items = []
    for row in rows:
        items.append({
            "date": row["date"].isoformat() if isinstance(row["date"], datetime) else str(row["date"]),
            "inflow_btc": row["inflow_btc"],
            "outflow_btc": row["outflow_btc"],
            "netflow_btc": row["netflow_btc"],
        })
        
    return {
        "items": items,
        "pagination": {"next_page_token": None, "has_more": False}
    }
