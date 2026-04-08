from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import QuestDBRepository

logger = setup_logging("sync_entities")

ENTITY_REFRESH_TABLES = [
    "entity_registry_serving",
    "entity_provenance_serving",
    "entity_flows_daily",
    "entity_balance_snapshots_daily",
    "entity_counterparty_edges_daily",
]


async def _truncate_entity_serving_tables(repo: QuestDBRepository) -> None:
    for table in ENTITY_REFRESH_TABLES:
        await repo.execute(f"TRUNCATE TABLE {table}")


async def sync_entities(repo: QuestDBRepository, conn: duckdb.DuckDBPyConnection):
    logger.info("Syncing entities to QuestDB...")
    now = datetime.now(timezone.utc)

    await _truncate_entity_serving_tables(repo)

    registry_rows = conn.execute(
        """
        SELECT
            r.entity_id,
            r.entity_kind,
            r.registry_status,
            r.display_label,
            r.confidence_overall,
            r.first_seen,
            r.last_seen,
            MIN(m.cluster_confidence) AS cluster_confidence,
            MIN(m.mapping_confidence) AS mapping_confidence,
            MAX(CASE WHEN l.is_primary THEN l.label_confidence ELSE NULL END) AS label_confidence
        FROM entity_registry r
        LEFT JOIN cluster_entity_map m ON r.entity_id = m.entity_id
        LEFT JOIN entity_labels l ON r.entity_id = l.entity_id
        GROUP BY
            r.entity_id,
            r.entity_kind,
            r.registry_status,
            r.display_label,
            r.confidence_overall,
            r.first_seen,
            r.last_seen
        """
    ).fetchall()

    for row in registry_rows:
        cluster_confidence = float(row[7]) if row[7] is not None else None
        mapping_confidence = float(row[8]) if row[8] is not None else None
        label_confidence = float(row[9]) if row[9] is not None else None
        is_incomplete = (
            not row[3]
            or cluster_confidence is None
            or mapping_confidence is None
            or label_confidence is None
        )
        await repo.async_send_row(
            "entity_registry_serving",
            symbols={
                "entity_id": row[0],
                "entity_kind": row[1] or "unknown",
                "registry_status": row[2] or "active",
                "display_label": row[3] or "unknown",
                "source_status": "degraded" if is_incomplete else "healthy",
            },
            columns={
                "cluster_confidence": cluster_confidence,
                "mapping_confidence": mapping_confidence,
                "label_confidence": label_confidence,
                "confidence_overall": float(row[4]) if row[4] is not None else 0.0,
                "first_seen": row[5] if isinstance(row[5], datetime) else now,
                "last_seen": row[6] if isinstance(row[6], datetime) else now,
                "ts": now,
            },
            at=now,
        )

    provenance_rows = conn.execute(
        """
        SELECT
            entity_id,
            label,
            source_kind,
            source_name,
            source_ref,
            review_status,
            method_version
        FROM entity_label_provenance
        ORDER BY entity_id, label, source_name
        """
    ).fetchall()
    provenance_by_entity: dict[str, list[dict[str, str | None]]] = {}
    for row in provenance_rows:
        provenance_by_entity.setdefault(row[0], []).append(
            {
                "label": row[1],
                "source_kind": row[2],
                "source_name": row[3],
                "source_ref": row[4],
                "review_status": row[5],
                "method_version": row[6],
            }
        )

    for entity_id, entries in provenance_by_entity.items():
        await repo.async_send_row(
            "entity_provenance_serving",
            symbols={
                "entity_id": entity_id,
                "primary_source_kind": entries[0]["source_kind"] or "unknown",
                "review_status": entries[0]["review_status"] or "unreviewed",
            },
            columns={
                "provenance_summary_json": json.dumps(entries),
                "ts": now,
            },
            at=now,
        )

    flow_rows = conn.execute(
        "SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange FROM entity_flows_daily"
    ).fetchall()
    for row in flow_rows:
        await repo.async_send_row(
            "entity_flows_daily",
            symbols={"entity_id": row[0]},
            columns={
                "date": row[1],
                "inflow_btc": float(row[2]) if row[2] is not None else 0.0,
                "outflow_btc": float(row[3]) if row[3] is not None else 0.0,
                "netflow_btc": float(row[4]) if row[4] is not None else 0.0,
                "is_exchange": bool(row[5]),
                "ts": now,
            },
            at=row[1] or now,
        )

    balance_rows = conn.execute(
        "SELECT entity_id, date, balance_btc FROM entity_balance_snapshots_daily"
    ).fetchall()
    for row in balance_rows:
        await repo.async_send_row(
            "entity_balance_snapshots_daily",
            symbols={"entity_id": row[0]},
            columns={
                "date": row[1],
                "balance_btc": float(row[2]) if row[2] is not None else 0.0,
                "ts": now,
            },
            at=row[1] or now,
        )

    counterparty_rows = conn.execute(
        """
        SELECT
            window_start,
            window_end,
            source_entity_id,
            target_entity_id,
            movement_classification,
            btc_amount,
            attribution_confidence,
            is_internal,
            materialization_status
        FROM entity_counterparty_edges_daily
        """
    ).fetchall()
    for row in counterparty_rows:
        await repo.async_send_row(
            "entity_counterparty_edges_daily",
            symbols={
                "source_entity_id": row[2],
                "target_entity_id": row[3],
                "movement_classification": row[4],
                "materialization_status": row[8] or "healthy",
            },
            columns={
                "window_start": row[0],
                "window_end": row[1],
                "btc_amount": float(row[5]) if row[5] is not None else 0.0,
                "attribution_confidence": float(row[6]) if row[6] is not None else 0.0,
                "is_internal": bool(row[7]),
                "ts": now,
            },
            at=row[0] or now,
        )

    await repo.async_flush_ingestion()
    logger.info(
        "✅ Synced %s entities, %s provenance groups, %s flow rows, %s balance rows, %s counterparty rows.",
        len(registry_rows),
        len(provenance_by_entity),
        len(flow_rows),
        len(balance_rows),
        len(counterparty_rows),
    )


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
