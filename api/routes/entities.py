from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.rate_limiter import RateLimiter, rate_limit

router = APIRouter(prefix="/api/entities", tags=["entities"])
MAX_ENTITY_ID_LENGTH = 256
STALE_MATERIALIZATION_AGE = timedelta(hours=48)
UNKNOWN_ENTITY_ID = "btc:entity:cluster:unknown"
ENTITY_ROUTE_LIMITER = RateLimiter(max_requests=100, window_seconds=60)

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
    if not entity_id or len(entity_id) > MAX_ENTITY_ID_LENGTH:
        raise HTTPException(status_code=422, detail="entity_id exceeds maximum length")

    if entity_id.startswith("cluster:"):
        cluster_id = entity_id.split(":", 1)[1]
        if not cluster_id:
            raise HTTPException(status_code=422, detail="Unsupported entity_id format")
        canonical_entity_id = f"btc:entity:cluster:{cluster_id}"
    elif entity_id.startswith("btc:entity:"):
        remainder = entity_id[len("btc:entity:") :]
        namespace, separator, stable_id = remainder.partition(":")
        if not separator or not namespace or not stable_id:
            raise HTTPException(status_code=422, detail="Unsupported entity_id format")
        canonical_entity_id = entity_id
    else:
        raise HTTPException(status_code=422, detail="Unsupported entity_id format")

    if len(canonical_entity_id) > MAX_ENTITY_ID_LENGTH:
        raise HTTPException(status_code=422, detail="entity_id exceeds maximum length")
    return canonical_entity_id


def _parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _parse_page_token(page_token: str | None) -> datetime | None:
    if page_token is None:
        return None

    parsed = _parse_timestamp(page_token)
    if parsed is None:
        raise HTTPException(status_code=422, detail="Invalid page_token")
    return parsed


def _normalize_flow_window(
    window_start: str | None,
    window_end: str | None,
) -> tuple[datetime, datetime]:
    parsed_end = _parse_timestamp(window_end)
    parsed_start = _parse_timestamp(window_start)
    if window_end is not None and parsed_end is None:
        raise HTTPException(status_code=422, detail="Invalid window_end")
    if window_start is not None and parsed_start is None:
        raise HTTPException(status_code=422, detail="Invalid window_start")

    parsed_end = parsed_end or datetime.now(timezone.utc)
    parsed_start = parsed_start or (parsed_end - timedelta(days=30))

    if parsed_end <= parsed_start:
        raise HTTPException(status_code=422, detail="window_end must be after window_start")
    if parsed_end - parsed_start > timedelta(days=366):
        raise HTTPException(status_code=422, detail="Flow window exceeds maximum span of 366 days")
    return parsed_start, parsed_end


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


def _parse_provenance_summary(provenance: dict | None) -> list[dict]:
    if not provenance or not provenance.get("provenance_summary_json"):
        return []

    try:
        parsed = json.loads(provenance["provenance_summary_json"])
    except (TypeError, json.JSONDecodeError):
        return []

    return parsed if isinstance(parsed, list) else []


def _collect_labels(row: dict, provenance_summary: list[dict]) -> list[str]:
    labels: list[str] = []

    raw_labels = row.get("labels")
    if isinstance(raw_labels, list):
        labels.extend(label for label in raw_labels if isinstance(label, str) and label)

    display_label = row.get("display_label")
    if isinstance(display_label, str) and display_label:
        labels.append(display_label)

    for entry in provenance_summary:
        label = entry.get("label")
        if isinstance(label, str) and label:
            labels.append(label)

    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)
    return deduped


def _is_stale_materialization(row: dict) -> bool:
    ts = _parse_timestamp(row.get("ts"))
    if ts is None:
        return False
    return datetime.now(timezone.utc) - ts > STALE_MATERIALIZATION_AGE


def _derive_metadata_source_status(row: dict, provenance_summary: list[dict]) -> str:
    explicit_status = row.get("source_status")
    if explicit_status == "ambiguous":
        return "ambiguous"
    if _is_stale_materialization(row):
        return "stale"
    if explicit_status == "stale":
        return "stale"

    required_confidence_fields = (
        "cluster_confidence",
        "mapping_confidence",
        "label_confidence",
        "confidence_overall",
    )
    missing_confidence = any(row.get(field) is None for field in required_confidence_fields)
    incomplete_metadata = not row.get("display_label") or not provenance_summary
    if explicit_status == "degraded" or missing_confidence or incomplete_metadata:
        return "degraded"
    return "healthy"


def _normalize_flow_row(row: dict) -> dict:
    source_entity_id = row.get("source_entity_id")
    target_entity_id = row.get("target_entity_id")
    same_known_entity = (
        source_entity_id is not None
        and source_entity_id == target_entity_id
        and source_entity_id != UNKNOWN_ENTITY_ID
    )

    movement_classification = row.get("movement_classification")
    if same_known_entity:
        movement_classification = "internal_entity_reshuffle"

    materialization_status = row.get("materialization_status") or "healthy"
    if materialization_status == "healthy" and _is_stale_materialization(row):
        materialization_status = "stale"

    is_internal = bool(row.get("is_internal"))
    if same_known_entity or movement_classification == "internal_entity_reshuffle":
        is_internal = True
    elif source_entity_id == target_entity_id == UNKNOWN_ENTITY_ID:
        is_internal = False

    return {
        "window_start": _format_ts(row.get("window_start")),
        "window_end": _format_ts(row.get("window_end")),
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "movement_classification": movement_classification,
        "btc_amount": row.get("btc_amount"),
        "attribution_confidence": row.get("attribution_confidence"),
        "is_internal": is_internal,
        "materialization_status": materialization_status,
    }


def _coerce_service_status(value: str) -> str:
    allowed_statuses = {"healthy", "stale", "degraded", "partial_materialization"}
    return value if value in allowed_statuses else "healthy"


def _derive_flow_service_status(items: list[dict]) -> str:
    if not items:
        return "empty"

    materialization_statuses = {_coerce_service_status(item["materialization_status"]) for item in items}
    if "partial_materialization" in materialization_statuses:
        return "partial_materialization"
    if "degraded" in materialization_statuses:
        return "degraded"
    if "stale" in materialization_statuses:
        return "stale"
    if any(item["movement_classification"] == "ambiguous" for item in items):
        return "ambiguous"
    return "healthy"


def _derive_cluster_ids(entity_id: str) -> list[str]:
    cluster_prefix = "btc:entity:cluster:"
    if entity_id.startswith(cluster_prefix):
        return [entity_id[len(cluster_prefix):]]
    return []


def _build_provenance_ref(row: dict) -> str | None:
    source_kind = row.get("primary_source_kind")
    review_status = row.get("review_status")
    provenance_ts = _format_ts(row.get("provenance_ts"))
    if not any((source_kind, review_status, provenance_ts)):
        return None
    return (
        "entity_provenance_serving:"
        f"{source_kind or 'unknown'}:{review_status or 'unknown'}:{provenance_ts or 'unknown'}"
    )


@router.get("/flows")
async def get_entity_flows(
    request: Request,
    _: None = Depends(rate_limit(ENTITY_ROUTE_LIMITER)),
    min_value: float = Query(default=0.0, ge=0.0),
    classification: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    window_start: str | None = Query(default=None),
    window_end: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
):
    if classification is not None and classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(status_code=422, detail="Unsupported classification filter")

    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id) if entity_id else None
    normalized_window_start, normalized_window_end = _normalize_flow_window(window_start, window_end)
    after_window_start = _parse_page_token(page_token)
    if after_window_start and (
        after_window_start < normalized_window_start or after_window_start >= normalized_window_end
    ):
        raise HTTPException(status_code=422, detail="page_token must fall within the requested flow window")
    rows = await repo.get_entity_flows(
        min_value=min_value,
        classification=classification,
        entity_id=canonical_entity_id,
        limit=limit + 1,
        window_start=normalized_window_start,
        window_end=normalized_window_end,
        after_window_start=after_window_start,
    )

    items = [_normalize_flow_row(row) for row in rows]
    visible, pagination = _pagination_response(items, limit=limit, token_field="window_start")
    service_status = _derive_flow_service_status(visible)
    return {
        "items": visible,
        "pagination": pagination,
        "service_status": service_status,
    }


@router.get("/{entity_id}")
async def get_entity_metadata(
    request: Request,
    entity_id: str,
    _: None = Depends(rate_limit(ENTITY_ROUTE_LIMITER)),
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id)
    row = await repo.get_entity_metadata(canonical_entity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Entity not found")

    provenance = await repo.get_entity_provenance(canonical_entity_id)
    provenance_summary = _parse_provenance_summary(provenance)
    labels = _collect_labels(row, provenance_summary)
    source_status = _derive_metadata_source_status(row, provenance_summary)

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
        "labels": labels,
        "provenance_summary": provenance_summary,
        "source_status": source_status,
    }


@router.get("/{entity_id}/history")
async def get_entity_history(
    request: Request,
    entity_id: str,
    _: None = Depends(rate_limit(ENTITY_ROUTE_LIMITER)),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
):
    repo = getattr(request.app.state, "questdb_repo", None)
    if not repo:
        raise HTTPException(status_code=503, detail="QuestDB unavailable")

    canonical_entity_id = _canonicalize_entity_id(entity_id)
    after_date = _parse_page_token(page_token)
    rows = await repo.get_entity_history(canonical_entity_id, limit + 1, after_date)

    items = [
        {
            "entity_id": canonical_entity_id,
            "as_of": _format_ts(row.get("as_of") or row.get("date")),
            "event_type": "balance_snapshot",
            "registry_status": row.get("registry_status"),
            "cluster_ids": _derive_cluster_ids(canonical_entity_id),
            "confidence_overall": row.get("confidence_overall"),
            "provenance_ref": _build_provenance_ref(row),
        }
        for row in rows
    ]
    visible, pagination = _pagination_response(items, limit=limit, token_field="as_of")
    return {"items": visible, "pagination": pagination}
