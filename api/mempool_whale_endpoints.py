#!/usr/bin/env python3
"""
Mempool Whale Detection REST API Endpoints
Task: T036 - Historical queries for whale transactions

Provides REST API endpoints for querying whale transaction history
from the DuckDB database with filtering and pagination.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging
from api.questdb_repository import QuestDBRepository

router = APIRouter(prefix="/api/whale", tags=["whale-detection"])


WHALE_EVENT_SCHEMA_VERSION = "whale_event.v1"
WHALE_EVENT_SOURCE = "questdb.mempool_predictions"
WHALE_EVENT_STATUS = "detected"
WHALE_SURFACE_ID = "whale_query_surface"
WHALE_ENTITY_CLUSTER_CONFIDENCE = 0.60
WHALE_ENTITY_LABEL_CONFIDENCE = 0.80


class WhaleEntityAttributionResponse(BaseModel):
    """Optional inferred entity metadata for whale events."""

    cluster_id: Optional[str]
    entity_id: Optional[str]
    entity_label: Optional[str]
    label_source: Optional[str]
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    attribution_kind: Optional[str]


class WhaleEntityPolicyResponse(BaseModel):
    """Observed vs inferred field policy for whale_event responses."""

    observed_fields: List[str]
    inferred_fields: List[str]
    omission_behavior: str


class WhaleTransactionResponse(BaseModel):
    """Whale transaction response model"""

    event_id: str
    prediction_id: str
    transaction_id: str
    flow_type: str
    btc_value: float
    fee_rate: float
    urgency_score: float
    rbf_enabled: bool
    detection_timestamp: str
    predicted_confirmation_block: Optional[int]
    confidence_score: Optional[float]
    source: str
    status: str
    entity_enrichment_status: str
    entity: Optional[WhaleEntityAttributionResponse]


class WhaleSummaryResponse(BaseModel):
    """Summary statistics for whale transactions"""

    surface_id: str
    event_schema_version: str
    total_transactions: int
    total_btc_volume: float
    avg_urgency_score: float
    high_urgency_count: int
    rbf_enabled_count: int
    time_period: str
    entity_enrichment_mode: str
    entity_policy: WhaleEntityPolicyResponse


def _whale_entity_policy() -> WhaleEntityPolicyResponse:
    return WhaleEntityPolicyResponse(
        observed_fields=[
            "event_id",
            "prediction_id",
            "transaction_id",
            "flow_type",
            "btc_value",
            "fee_rate",
            "urgency_score",
            "rbf_enabled",
            "detection_timestamp",
            "predicted_confirmation_block",
            "confidence_score",
            "source",
            "status",
        ],
        inferred_fields=[
            "entity.cluster_id",
            "entity.entity_id",
            "entity.entity_label",
            "entity.label_source",
            "entity.confidence",
            "entity.attribution_kind",
        ],
        omission_behavior=(
            "entity is null and entity_enrichment_status is unavailable or "
            "ambiguous when clustering or label enrichment cannot be derived "
            "from exchange_addresses and address_clusters."
        ),
    )


def _parse_exchange_addresses(raw_addresses: Optional[str]) -> list[str]:
    if not raw_addresses:
        return []

    return [
        address
        for address in {part.strip() for part in raw_addresses.split(",")}
        if address
    ]


async def _fetch_cluster_rows(
    repo: QuestDBRepository, addresses: list[str]
) -> dict[str, list[dict]]:
    if not addresses:
        return {}

    placeholders = ", ".join(f"${idx}" for idx in range(1, len(addresses) + 1))
    query = f"""
        SELECT
            address,
            cluster_id,
            label
        FROM address_clusters
        WHERE address IN ({placeholders})
    """

    try:
        rows = await repo.fetch(query, *addresses)
    except Exception as exc:
        logging.warning("Whale entity enrichment unavailable: %s", exc)
        return {}

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        address = row["address"]
        grouped.setdefault(address, []).append(
            {
                "cluster_id": row["cluster_id"],
                "label": row["label"],
            }
        )
    return grouped


async def _derive_entity_attribution(
    repo: QuestDBRepository,
    exchange_addresses: list[str],
    cluster_rows_by_address: dict[str, list[dict]],
) -> tuple[Optional[WhaleEntityAttributionResponse], str]:
    if not exchange_addresses:
        return None, "unavailable"

    records: list[dict] = []
    for address in exchange_addresses:
        records.extend(cluster_rows_by_address.get(address, []))

    if not records:
        return None, "unavailable"

    cluster_ids = sorted({row["cluster_id"] for row in records if row["cluster_id"]})
    if len(cluster_ids) != 1:
        return None, "ambiguous"

    cluster_id = cluster_ids[0]
    
    # Try to find a richer entity ID from the new registry
    entity_id = f"cluster:{cluster_id}"
    confidence = WHALE_ENTITY_CLUSTER_CONFIDENCE
    label_source = "questdb.address_clusters.cluster_id"
    
    entity_row = await repo.get_entity_metadata(f"btc:entity:cluster:{cluster_id}")
    if entity_row:
        entity_id = entity_row["entity_id"]
        entity_label = entity_row["display_label"]
        confidence = entity_row["confidence_overall"]
        label_source = "questdb.entity_registry_serving"
    else:
        labels = sorted({row["label"] for row in records if row["label"]})
        entity_label = labels[0] if len(labels) == 1 else None
        if entity_label is not None:
            label_source = "questdb.address_clusters.label"
            confidence = WHALE_ENTITY_LABEL_CONFIDENCE

    return (
        WhaleEntityAttributionResponse(
            cluster_id=cluster_id,
            entity_id=entity_id,
            entity_label=entity_label,
            label_source=label_source,
            confidence=confidence,
            attribution_kind="inferred",
        ),
        "inferred",
    )


def _build_whale_event(
    row,
    entity: Optional[WhaleEntityAttributionResponse],
    entity_status: str,
) -> WhaleTransactionResponse:
    return WhaleTransactionResponse(
        event_id=row["prediction_id"],
        prediction_id=row["prediction_id"],
        transaction_id=row["transaction_id"],
        flow_type=row["flow_type"],
        btc_value=row["btc_value"],
        fee_rate=row["fee_rate"],
        urgency_score=row["urgency_score"],
        rbf_enabled=row["rbf_enabled"],
        detection_timestamp=row["detection_timestamp"].isoformat(),
        predicted_confirmation_block=row["predicted_confirmation_block"],
        confidence_score=row["confidence_score"],
        source=WHALE_EVENT_SOURCE,
        status=WHALE_EVENT_STATUS,
        entity_enrichment_status=entity_status,
        entity=entity,
    )


@router.get("/transactions", response_model=List[WhaleTransactionResponse])
async def get_whale_transactions(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (max 7 days)"),
    flow_type: Optional[str] = Query(None, description="Filter by flow type"),
    min_btc: Optional[float] = Query(
        None, ge=100, description="Minimum BTC value filter"
    ),
    min_urgency: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Minimum urgency score filter"
    ),
    rbf_only: bool = Query(False, description="Show only RBF-enabled transactions"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
):
    """
    Get historical whale transactions from QuestDB with optional filtering
    """
    repo: QuestDBRepository = request.app.state.questdb_repo
    try:
        # Build query with filters (QuestDB compatible)
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        query = """
            SELECT
                prediction_id,
                transaction_id,
                flow_type,
                btc_value,
                fee_rate,
                urgency_score,
                rbf_enabled,
                ts as detection_timestamp,
                predicted_confirmation_block,
                confidence_score,
                exchange_addresses
            FROM mempool_predictions
            WHERE ts >= $1
        """
        params = [cutoff_time]
        arg_idx = 2

        if flow_type:
            query += f" AND flow_type = ${arg_idx}"
            params.append(flow_type)
            arg_idx += 1

        if min_btc:
            query += f" AND btc_value >= ${arg_idx}"
            params.append(min_btc)
            arg_idx += 1

        if min_urgency is not None:
            query += f" AND urgency_score >= ${arg_idx}"
            params.append(min_urgency)
            arg_idx += 1

        if rbf_only:
            query += " AND rbf_enabled = TRUE"

        query += f" ORDER BY ts DESC LIMIT ${arg_idx}"
        params.append(limit)

        result = await repo.fetch(query, *params)
        all_addresses = sorted(
            {
                address
                for row in result
                for address in _parse_exchange_addresses(row["exchange_addresses"])
            }
        )
        cluster_rows_by_address = await _fetch_cluster_rows(repo, all_addresses)

        events: list[WhaleTransactionResponse] = []
        for row in result:
            exchange_addresses = _parse_exchange_addresses(row["exchange_addresses"])
            entity, entity_status = await _derive_entity_attribution(
                repo, exchange_addresses, cluster_rows_by_address
            )
            events.append(_build_whale_event(row, entity, entity_status))
        return events

    except Exception as e:
        logging.error(f"Whale transactions query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


@router.get("/summary", response_model=WhaleSummaryResponse)
async def get_whale_summary(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (max 7 days)"),
):
    """
    Get summary statistics from QuestDB
    """
    repo: QuestDBRepository = request.app.state.questdb_repo
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        query = """
            SELECT
                COUNT(*) as total_transactions,
                SUM(btc_value) as total_btc_volume,
                AVG(urgency_score) as avg_urgency_score,
                SUM(CASE WHEN urgency_score >= 0.7 THEN 1 ELSE 0 END) as high_urgency_count,
                SUM(CASE WHEN rbf_enabled = TRUE THEN 1 ELSE 0 END) as rbf_enabled_count
            FROM mempool_predictions
            WHERE ts >= $1
        """

        result = await repo.fetchrow(query, cutoff_time)

        return WhaleSummaryResponse(
            surface_id=WHALE_SURFACE_ID,
            event_schema_version=WHALE_EVENT_SCHEMA_VERSION,
            total_transactions=result["total_transactions"] or 0,
            total_btc_volume=round(result["total_btc_volume"] or 0.0, 2),
            avg_urgency_score=round(result["avg_urgency_score"] or 0.0, 3),
            high_urgency_count=result["high_urgency_count"] or 0,
            rbf_enabled_count=result["rbf_enabled_count"] or 0,
            time_period=f"Last {hours} hours",
            entity_enrichment_mode="best_effort_optional",
            entity_policy=_whale_entity_policy(),
        )

    except Exception as e:
        logging.error(f"Whale summary query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


@router.get("/transaction/{txid}", response_model=WhaleTransactionResponse)
async def get_whale_transaction(request: Request, txid: str):
    """
    Get specific whale transaction from QuestDB
    """
    repo: QuestDBRepository = request.app.state.questdb_repo
    try:
        query = """
            SELECT
                prediction_id,
                transaction_id,
                flow_type,
                btc_value,
                fee_rate,
                urgency_score,
                rbf_enabled,
                ts as detection_timestamp,
                predicted_confirmation_block,
                confidence_score,
                exchange_addresses
            FROM mempool_predictions
            WHERE transaction_id = $1
            ORDER BY ts DESC
            LIMIT 1
        """

        result = await repo.fetchrow(query, txid)

        if not result:
            raise HTTPException(status_code=404, detail=f"Transaction {txid} not found")

        exchange_addresses = _parse_exchange_addresses(result["exchange_addresses"])
        cluster_rows_by_address = await _fetch_cluster_rows(repo, exchange_addresses)
        entity, entity_status = await _derive_entity_attribution(
            repo,
            exchange_addresses,
            cluster_rows_by_address,
        )
        return _build_whale_event(result, entity, entity_status)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Whale transaction lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
