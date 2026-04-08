import asyncio
import logging
import os
import sys
import duckdb
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import QuestDBRepository

logger = setup_logging("sync_entities")

async def sync_entities(repo: QuestDBRepository, conn: duckdb.DuckDBPyConnection):
    logger.info("Syncing entities to QuestDB...")
    
    # 1. Sync registry
    rows = conn.execute("SELECT * FROM entity_registry").fetchall()
    now = datetime.now(timezone.utc)
    
    for row in rows:
        # row: entity_id, entity_kind, registry_status, display_label, confidence_overall, first_seen, last_seen
        symbols = {
            "entity_id": row[0],
            "entity_kind": row[1] or "unknown",
            "registry_status": row[2] or "active",
            "display_label": row[3] or "unknown",
        }
        columns = {
            "confidence_overall": float(row[4]) if row[4] is not None else 0.0,
            "last_seen": row[6] if isinstance(row[6], datetime) else now,
            "ts": now,
        }
        await repo.async_send_row("entity_registry_serving", symbols, columns, now)
    
    await repo.async_flush_ingestion()
    logger.info(f"✅ Synced {len(rows)} entities.")

async def main():
    repo = QuestDBRepository()
    await repo.initialize()
    
    if not os.path.exists(DUCKDB_PATH):
        logger.error(f"DuckDB database not found at {DUCKDB_PATH}")
        return

    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        await sync_entities(repo, conn)
    finally:
        conn.close()
        await repo.close()

if __name__ == "__main__":
    asyncio.run(main())
