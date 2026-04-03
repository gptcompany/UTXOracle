#!/usr/bin/env python3
"""
Sync Address Clusters from DuckDB to QuestDB (spec-051 Phase 2).

This script reads the `address_clusters` table from DuckDB (produced by the
clustering pipeline) and synchronizes it to the QuestDB serving plane via a 
truncate-and-load approach.

Usage:
  python3 scripts/bootstrap/sync_clusters_to_questdb.py [--batch-size 100000]
"""

import asyncio
import logging
import os
import sys
import argparse
from typing import List, Dict, Any

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import QuestDBRepository

logger = setup_logging("sync_clusters")

async def sync_clusters(repo: QuestDBRepository, conn: duckdb.DuckDBPyConnection, batch_size: int):
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

    # 2. Truncate QuestDB table
    try:
        await repo.execute("TRUNCATE TABLE address_clusters")
        logger.info("Truncated QuestDB address_clusters table.")
    except Exception as e:
        logger.error(f"Failed to truncate QuestDB table: {e}")
        return False

    # 3. Read from DuckDB and insert in batches
    # Use a cursor to fetch in chunks
    cursor = conn.cursor()
    # Ensure DuckDB schema matches our expectations (it may lack confidence, so we default it)
    cursor.execute("""
        SELECT address, cluster_id, first_seen, last_seen, is_exchange_likely, label 
        FROM address_clusters
    """)
    
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
            
        # We don't use save_address_clusters_bulk because it truncates.
        # We will loop _send_row directly here since we already truncated.
        # Actually, let's just do it directly to avoid multiple truncates.
        for r in rows_to_insert:
            symbols = {}
            if r.get("label"):
                symbols["label"] = str(r["label"])
                
            repo._send_row(
                "address_clusters",
                symbols=symbols,
                columns={
                    "address": str(r["address"]),
                    "cluster_id": str(r["cluster_id"]),
                    "last_seen": r.get("last_seen"),
                    "is_exchange_likely": r["is_exchange_likely"],
                    "confidence": r["confidence"]
                },
                at=r.get("first_seen")
            )
            
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
