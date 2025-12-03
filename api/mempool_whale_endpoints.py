#!/usr/bin/env python3
"""
Mempool Whale Detection REST API Endpoints
Task: T036 - Historical queries for whale transactions

Provides REST API endpoints for querying whale transaction history
from the DuckDB database with filtering and pagination.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import duckdb
import os

router = APIRouter(prefix="/api/whale", tags=["whale-detection"])

# Database path - configurable via environment variable
# Default: production database path used by whale orchestrator
DB_PATH = os.getenv(
    "WHALE_DB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)


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
    Get historical whale transactions with optional filtering

    - **hours**: Time window to query (1-168 hours)
    - **flow_type**: Filter by flow type (inflow/outflow/internal/unknown)
    - **min_btc**: Minimum BTC value threshold
    - **min_urgency**: Minimum urgency score threshold
    - **rbf_only**: Only show RBF-enabled transactions
    - **limit**: Maximum number of results
    """
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=True)

        # Build query with filters
        query = """
            SELECT
                prediction_id,
                transaction_id,
                flow_type,
                btc_value,
                fee_rate,
                urgency_score,
                rbf_enabled,
                detection_timestamp,
                predicted_confirmation_block,
                confidence_score
            FROM mempool_predictions
            WHERE detection_timestamp >= ?
        """
        params = [datetime.utcnow() - timedelta(hours=hours)]

        if flow_type:
            query += " AND flow_type = ?"
            params.append(flow_type)

        if min_btc:
            query += " AND btc_value >= ?"
            params.append(min_btc)

        if min_urgency is not None:
            query += " AND urgency_score >= ?"
            params.append(min_urgency)

        if rbf_only:
            query += " AND rbf_enabled = TRUE"

        query += " ORDER BY detection_timestamp DESC LIMIT ?"
        params.append(limit)

        result = conn.execute(query, params).fetchall()
        conn.close()

        # Convert to response models
        transactions = []
        for row in result:
            transactions.append(
                WhaleTransactionResponse(
                    prediction_id=row[0],
                    transaction_id=row[1],
                    flow_type=row[2],
                    btc_value=row[3],
                    fee_rate=row[4],
                    urgency_score=row[5],
                    rbf_enabled=row[6],
                    detection_timestamp=row[7].isoformat(),
                    predicted_confirmation_block=row[8],
                    confidence_score=row[9],
                )
            )

        return transactions

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


@router.get("/summary", response_model=WhaleSummaryResponse)
async def get_whale_summary(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (max 7 days)"),
):
    """
    Get summary statistics for whale transactions in the specified time period
    """
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=True)

        query = """
            SELECT
                COUNT(*) as total_transactions,
                SUM(btc_value) as total_btc_volume,
                AVG(urgency_score) as avg_urgency_score,
                SUM(CASE WHEN urgency_score >= 0.7 THEN 1 ELSE 0 END) as high_urgency_count,
                SUM(CASE WHEN rbf_enabled = TRUE THEN 1 ELSE 0 END) as rbf_enabled_count
            FROM mempool_predictions
            WHERE detection_timestamp >= ?
        """

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        result = conn.execute(query, [cutoff_time]).fetchone()
        conn.close()

        return WhaleSummaryResponse(
            total_transactions=result[0] or 0,
            total_btc_volume=round(result[1] or 0.0, 2),
            avg_urgency_score=round(result[2] or 0.0, 3),
            high_urgency_count=result[3] or 0,
            rbf_enabled_count=result[4] or 0,
            time_period=f"Last {hours} hours",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


@router.get("/transaction/{txid}", response_model=WhaleTransactionResponse)
async def get_whale_transaction(txid: str):
    """
    Get details for a specific whale transaction by transaction ID
    """
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=True)

        query = """
            SELECT
                prediction_id,
                transaction_id,
                flow_type,
                btc_value,
                fee_rate,
                urgency_score,
                rbf_enabled,
                detection_timestamp,
                predicted_confirmation_block,
                confidence_score
            FROM mempool_predictions
            WHERE transaction_id = ?
            ORDER BY detection_timestamp DESC
            LIMIT 1
        """

        result = conn.execute(query, [txid]).fetchone()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail=f"Transaction {txid} not found")

        return WhaleTransactionResponse(
            prediction_id=result[0],
            transaction_id=result[1],
            flow_type=result[2],
            btc_value=result[3],
            fee_rate=result[4],
            urgency_score=result[5],
            rbf_enabled=result[6],
            detection_timestamp=result[7].isoformat(),
            predicted_confirmation_block=result[8],
            confidence_score=result[9],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
