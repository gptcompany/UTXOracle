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
from pydantic import BaseModel
import logging
from api.questdb_repository import QuestDBRepository

router = APIRouter(prefix="/api/whale", tags=["whale-detection"])

class WhaleTransactionResponse(BaseModel):
    """Whale transaction response model"""

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


class WhaleSummaryResponse(BaseModel):
    """Summary statistics for whale transactions"""

    total_transactions: int
    total_btc_volume: float
    avg_urgency_score: float
    high_urgency_count: int
    rbf_enabled_count: int
    time_period: str


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
                confidence_score
            FROM mempool_predictions
            WHERE ts >= now() - interval '$1 hours'
        """
        params = [hours]

        if flow_type:
            query += f" AND flow_type = '{flow_type}'" # simplified for QuestDB

        if min_btc:
            query += f" AND btc_value >= {min_btc}"

        if min_urgency is not None:
            query += f" AND urgency_score >= {min_urgency}"

        if rbf_only:
            query += " AND rbf_enabled = TRUE"

        query += " ORDER BY ts DESC LIMIT $2"
        params.append(limit)

        result = await repo.fetch(query, *params)

        return [
            WhaleTransactionResponse(
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
            )
            for row in result
        ]

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
        query = """
            SELECT
                COUNT(*) as total_transactions,
                SUM(btc_value) as total_btc_volume,
                AVG(urgency_score) as avg_urgency_score,
                SUM(CASE WHEN urgency_score >= 0.7 THEN 1 ELSE 0 END) as high_urgency_count,
                SUM(CASE WHEN rbf_enabled = TRUE THEN 1 ELSE 0 END) as rbf_enabled_count
            FROM mempool_predictions
            WHERE ts >= now() - interval '$1 hours'
        """

        result = await repo.fetchrow(query, hours)

        return WhaleSummaryResponse(
            total_transactions=result["total_transactions"] or 0,
            total_btc_volume=round(result["total_btc_volume"] or 0.0, 2),
            avg_urgency_score=round(result["avg_urgency_score"] or 0.0, 3),
            high_urgency_count=result["high_urgency_count"] or 0,
            rbf_enabled_count=result["rbf_enabled_count"] or 0,
            time_period=f"Last {hours} hours",
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
                confidence_score
            FROM mempool_predictions
            WHERE transaction_id = $1
            ORDER BY ts DESC
            LIMIT 1
        """

        result = await repo.fetchrow(query, txid)

        if not result:
            raise HTTPException(status_code=404, detail=f"Transaction {txid} not found")

        return WhaleTransactionResponse(
            prediction_id=result["prediction_id"],
            transaction_id=result["transaction_id"],
            flow_type=result["flow_type"],
            btc_value=result["btc_value"],
            fee_rate=result["fee_rate"],
            urgency_score=result["urgency_score"],
            rbf_enabled=result["rbf_enabled"],
            detection_timestamp=result["detection_timestamp"].isoformat(),
            predicted_confirmation_block=result["predicted_confirmation_block"],
            confidence_score=result["confidence_score"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Whale transaction lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
