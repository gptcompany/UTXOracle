#!/usr/bin/env python3
"""
Sync Address Clusters from DuckDB to QuestDB (spec-051 Phase 2).

This script reads the `address_clusters` table from DuckDB (produced by the
clustering pipeline) and synchronizes it to the QuestDB serving plane via a 
truncate-and-load approach.

Usage:
  python3 scripts/bootstrap/sync_clusters_to_questdb.py [--batch-size 100000]
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import QuestDBRepository

logger = setup_logging("sync_clusters")


def _build_duckdb_cluster_query(conn: duckdb.DuckDBPyConnection) -> str:
    """Build a schema-tolerant SELECT for DuckDB address_clusters."""
    columns = {
        row[1] if len(row) > 1 else row[0]
        for row in conn.execute("PRAGMA table_info('address_clusters')").fetchall()
    }
    required_columns = {"address", "cluster_id", "first_seen", "last_seen"}
    missing_required = required_columns - columns
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(f"DuckDB address_clusters missing required columns: {missing}")

    select_parts = [
        "address",
        "cluster_id",
        "first_seen",
        "last_seen",
        (
            "is_exchange_likely"
            if "is_exchange_likely" in columns
            else "FALSE AS is_exchange_likely"
        ),
        ("label" if "label" in columns else "NULL AS label"),
    ]
    return f"SELECT {', '.join(select_parts)} FROM address_clusters"


async def sync_clusters(
    repo: QuestDBRepository,
    conn: duckdb.DuckDBPyConnection,
    batch_size: int,
) -> bool:
    """
    Read all clusters from DuckDB and load them into QuestDB.
    Uses TRUNCATE + ILP for a clean, full-refresh snapshot.
    """
    logger.info("Starting address_clusters sync from DuckDB to QuestDB...")
    
    # 1. Check if DuckDB table exists and has data
    try:
        count_res = conn.execute("SELECT COUNT(*) FROM address_clusters").fetchone()
        total_rows = count_res[0] if count_res else 0
        if total_rows == 0:
            logger.warning("No rows found in DuckDB address_clusters. Aborting sync.")
            return False
            
        logger.info(f"Found {total_rows:,} address clusters in DuckDB.")
    except Exception as e:
        logger.error(f"Failed to query DuckDB address_clusters: {e}")
        return False

    try:
        select_query = _build_duckdb_cluster_query(conn)
    except Exception as e:
        logger.error(f"Failed to inspect DuckDB address_clusters schema: {e}")
        return False

    # 2. Prepare DuckDB cursor before mutating QuestDB state
    try:
        cursor = conn.cursor()
        cursor.execute(select_query)
    except Exception as e:
        logger.error(f"Failed to read DuckDB address_clusters: {e}")
        return False

    # 3. Truncate QuestDB table
    try:
        await repo.execute("TRUNCATE TABLE address_clusters")
        logger.info("Truncated QuestDB address_clusters table.")
    except Exception as e:
        logger.error(f"Failed to truncate QuestDB table: {e}")
        return False

    total_synced = 0
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
            
        rows_to_insert = []
        for row in batch:
            rows_to_insert.append({
                "address": row[0],
                "cluster_id": row[1],
                "first_seen": row[2],
                "last_seen": row[3],
                "is_exchange_likely": bool(row[4]) if row[4] is not None else False,
                "label": row[5],
                # Default confidence based on spec-047 guidelines: 0.8 if labeled, 0.6 otherwise
                "confidence": 0.8 if row[5] else 0.6
            })
            
        for r in rows_to_insert:
            symbols = {}
            if r.get("label"):
                symbols["label"] = str(r["label"])

            row_success = repo._send_row(
                "address_clusters",
                symbols=symbols,
                columns={
                    "address": str(r["address"]),
                    "cluster_id": str(r["cluster_id"]),
                    "last_seen": r.get("last_seen"),
                    "is_exchange_likely": r["is_exchange_likely"],
                    "confidence": r["confidence"]
                },
                at=r.get("first_seen"),
            )
            if not row_success:
                logger.error(
                    "Failed to ingest address cluster for address=%s cluster_id=%s",
                    r["address"],
                    r["cluster_id"],
                )
                repo.abort_ingestion()
                return False

        total_synced += len(rows_to_insert)
        logger.info(f"Synced {total_synced:,} / {total_rows:,} clusters...")

    await repo.async_flush_ingestion()
    logger.info(f"✅ Successfully synchronized {total_synced:,} clusters to QuestDB.")
    return True

async def main():
    parser = argparse.ArgumentParser(description="Sync Address Clusters to QuestDB")
    parser.add_argument("--batch-size", type=int, default=100000, help="Batch size for reading from DuckDB")
    args = parser.parse_args()

    repo = QuestDBRepository()
    await repo.initialize()
    
    if not os.path.exists(DUCKDB_PATH):
        logger.error(f"DuckDB database not found at {DUCKDB_PATH}")
        return

    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    
    try:
        await sync_clusters(repo, conn, args.batch_size)
    finally:
        conn.close()
        await repo.close()

if __name__ == "__main__":
    asyncio.run(main())
