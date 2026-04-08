from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/entities", tags=["entities"])
MAX_ENTITY_ID_LENGTH = 256

ALLOWED_CLASSIFICATIONS = {
    "exchange_inflow",
    "exchange_outflow",
    "entity_to_entity",
    "entity_to_unlabeled",
    "unlabeled_to_entity",
    "internal_entity_reshuffle",
    "ambiguous",
}


def _canonicalize_entity_id(entity_id: str) -> str:
    if len(entity_id) > MAX_ENTITY_ID_LENGTH:
        raise HTTPException(status_code=422, detail="entity_id exceeds maximum length")
    if entity_id.startswith("cluster:"):
        return f"btc:entity:cluster:{entity_id.split(':', 1)[1]}"
    if entity_id.startswith("btc:entity:"):
        return entity_id
    raise HTTPException(status_code=422, detail="Unsupported entity_id format")


def _format_ts(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _pagination_response(items: list[dict], *, limit: int, token_field: str) -> tuple[list[dict], dict]:
    has_more = len(items) > limit
    visible = items[:limit]
    next_page_token = str(visible[-1][token_field]) if has_more and visible else None
    return visible, {"next_page_token": next_page_token, "has_more": has_more}


def _derive_flow_service_status(items: list[dict]) -> str:
    if not items:
        return "empty"

    materialization_statuses = {item["materialization_status"] for item in items}
    if "partial_materialization" in materialization_statuses:
        return "partial_materialization"
    if "degraded" in materialization_statuses:
        return "degraded"
    if "stale" in materialization_statuses:
        return "stale"
    if all(item["movement_classification"] == "ambiguous" for item in items):
        return "ambiguous"
    return "healthy"


@router.get("/flows")
async def get_entity_flows(
    request: Request,
    min_value: float = Query(default=0.0, ge=0.0),
    classification: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
):
    if classification is not None and classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(status_code=422, detail="Unsupported classification filter")

    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id) if entity_id else None
    after_window_start = datetime.fromisoformat(page_token) if page_token else None
    rows = await repo.get_entity_flows(
        min_value=min_value,
        classification=classification,
        entity_id=canonical_entity_id,
        limit=limit + 1,
        after_window_start=after_window_start,
    )

    items = [
        {
            "window_start": _format_ts(row.get("window_start")),
            "window_end": _format_ts(row.get("window_end")),
            "source_entity_id": row.get("source_entity_id"),
            "target_entity_id": row.get("target_entity_id"),
            "movement_classification": row.get("movement_classification"),
            "btc_amount": row.get("btc_amount"),
            "attribution_confidence": row.get("attribution_confidence"),
            "is_internal": bool(row.get("is_internal")),
            "materialization_status": row.get("materialization_status", "healthy"),
        }
        for row in rows
    ]
    visible, pagination = _pagination_response(items, limit=limit, token_field="window_start")
    service_status = _derive_flow_service_status(visible)
    return {
        "items": visible,
        "pagination": pagination,
        "service_status": service_status,
    }


@router.get("/{entity_id}")
async def get_entity_metadata(request: Request, entity_id: str):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id)
    row = await repo.get_entity_metadata(canonical_entity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Entity not found")

    provenance = await repo.get_entity_provenance(canonical_entity_id)
    provenance_summary = []
    if provenance and provenance.get("provenance_summary_json"):
        try:
            provenance_summary = json.loads(provenance["provenance_summary_json"])
        except (TypeError, json.JSONDecodeError):
            provenance_summary = []

    return {
        "entity_id": canonical_entity_id,
        "display_label": row.get("display_label"),
        "entity_kind": row.get("entity_kind", "unknown"),
        "registry_status": row.get("registry_status", "candidate"),
        "first_seen": _format_ts(row.get("first_seen")),
        "last_seen": _format_ts(row.get("last_seen")),
        "confidence": {
            "cluster_confidence": row.get("cluster_confidence"),
            "mapping_confidence": row.get("mapping_confidence"),
            "label_confidence": row.get("label_confidence"),
            "confidence_overall": row.get("confidence_overall"),
        },
        "labels": [],
        "provenance_summary": provenance_summary,
        "source_status": row.get("source_status", "healthy"),
    }


@router.get("/{entity_id}/history")
async def get_entity_history(
    request: Request,
    entity_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id)
    after_date = datetime.fromisoformat(page_token) if page_token else None
    rows = await repo.get_entity_history(canonical_entity_id, limit + 1, after_date)

    items = [
        {
            "entity_id": canonical_entity_id,
            "as_of": _format_ts(row.get("as_of") or row.get("date")),
            "event_type": row.get("event_type", "balance_snapshot"),
            "registry_status": row.get("registry_status", "active"),
            "cluster_ids": row.get("cluster_ids", []),
            "confidence_overall": row.get("confidence_overall"),
            "provenance_ref": row.get("provenance_ref"),
        }
        for row in rows
    ]
    visible, pagination = _pagination_response(items, limit=limit, token_field="as_of")
    return {"items": visible, "pagination": pagination}
