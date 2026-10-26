#!/usr/bin/env python3
"""
Sync Address Clusters from DuckDB to QuestDB (spec-051 Phase 2).

This script reads the `address_clusters` table from DuckDB (produced by the
clustering pipeline) and synchronizes it to the QuestDB serving plane via a
staged full-refresh cutover.

Usage:
  python3 scripts/bootstrap/sync_clusters_to_questdb.py [--batch-size 100000]

The whole refresh runs under the host-local address_clusters lock (see
QuestDBRepository.refresh_address_clusters, the only place that takes it); if another
refresh holds it the script exits non-zero.
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import (
    AddressClustersLostError,
    ConcurrentRefreshError,
    OldCopyCleanupError,
    QuestDBRepository,
)

# Exit codes: 0 synced; 1 failed, DuckDB missing or concurrent refresh; 2 usage error
# (argparse); 5 swap ok but cleanup of an older _old copy failed (see the ERROR);
# 6 neither address_clusters nor an _old copy exists after a failed cutover.
EXIT_CLEANUP_FAILED = 5
EXIT_CLUSTERS_LOST = 6

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
    Uses a staging table so the live snapshot is only replaced after the ILP
    load completes successfully.
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

    # 3. Stage the rows and publish them; the refresh lock is taken inside the repository
    async def producer() -> Optional[int]:
        total_synced = 0
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                return total_synced

            rows_to_insert = []
            for row in batch:
                rows_to_insert.append(
                    {
                        "address": row[0],
                        "cluster_id": row[1],
                        "first_seen": row[2],
                        "last_seen": row[3],
                        "is_exchange_likely": bool(row[4])
                        if row[4] is not None
                        else False,
                        "label": row[5],
                        # Default confidence based on spec-047 guidelines: 0.8 if labeled, 0.6 otherwise
                        "confidence": 0.8 if row[5] else 0.6,
                    }
                )

            for r in rows_to_insert:
                if not repo.stage_address_cluster(r):
                    logger.error(
                        "Failed to ingest address cluster for address=%s cluster_id=%s",
                        r["address"],
                        r["cluster_id"],
                    )
                    return None

            total_synced += len(rows_to_insert)
            logger.info(f"Synced {total_synced:,} / {total_rows:,} clusters...")

    if not await repo.refresh_address_clusters(producer):
        return False

    logger.info(f"✅ Successfully synchronized {total_rows:,} clusters to QuestDB.")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Address Clusters to QuestDB")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100000,
        help="Batch size for reading from DuckDB",
    )
    args = parser.parse_args()

    repo = QuestDBRepository()
    await repo.initialize()

    if not os.path.exists(DUCKDB_PATH):
        logger.error(f"DuckDB database not found at {DUCKDB_PATH}")
        return 1

    conn = duckdb.connect(DUCKDB_PATH, read_only=True)

    try:
        ok = await sync_clusters(repo, conn, args.batch_size)
        return 0 if ok else 1
    except ConcurrentRefreshError:
        return 1  # already logged as concurrent_refresh
    except OldCopyCleanupError as e:
        logger.error("%s", e)
        return EXIT_CLEANUP_FAILED
    except AddressClustersLostError as e:
        logger.error("%s", e)
        return EXIT_CLUSTERS_LOST
    finally:
        conn.close()
        await repo.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
