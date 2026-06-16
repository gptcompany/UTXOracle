from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import date as _date
from pathlib import Path

import duckdb

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH
from api.questdb_repository import save_entity_flows_daily
from scripts.live.init_flow_artifacts import create_flow_artifact_tables

logger = logging.getLogger(__name__)


def _format_date_token(dates: list[_date]) -> str:
    """Return YYYY-MM-DD if all dates equal, else min..max ISO range."""
    unique = sorted(set(dates))
    if len(unique) == 1:
        return unique[0].isoformat()
    return f"{unique[0].isoformat()}..{unique[-1].isoformat()}"


def _format_exception_summary(exc_classes: list[str]) -> str:
    """Single class name if uniform, else MultipleFailureClasses."""
    unique = set(exc_classes)
    if len(unique) == 1:
        return next(iter(unique))
    return "MultipleFailureClasses"


def _post_aggregated_webhook(
    failed_rows: list[tuple[str, _date, str]],
) -> None:
    """POST one aggregated Discord webhook per failing aggregate_flows run.

    Payload format per contracts/webhook_payload.md. Webhook errors are
    swallowed and logged at WARNING — they MUST NOT mask the underlying
    run state per spec-062 FR-012 precedent.
    """
    if not failed_rows:
        return
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook or webhook.startswith("ENC[") or webhook.startswith("encrypted:"):
        return
    date_token = _format_date_token([row[1] for row in failed_rows])
    exception_summary = _format_exception_summary([row[2] for row in failed_rows])
    payload = json.dumps(
        {
            "content": (
                ":rotating_light: entity_flows_daily QuestDB write failed for "
                f"{date_token}: {len(failed_rows)} rows failed ({exception_summary})"
            )
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read(0)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.warning(
            "entity_flows_daily Discord webhook post failed (suppressed): %s",
            exc,
        )


def _should_write_questdb() -> bool:
    """Return False iff SPEC063_QUESTDB_WRITE uses a canonical OFF token."""
    raw = os.environ.get("SPEC063_QUESTDB_WRITE")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no"}


def _has_column(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    rows = conn.execute("SHOW TABLES").fetchall()
    return any(row[0] == table for row in rows)


def _timestamp_expr(conn: duckdb.DuckDBPyConnection) -> str:
    for candidate in ("ts", "created_at", "spent_timestamp"):
        if _has_column(conn, "utxo_lifecycle", candidate):
            return f"u.{candidate}"
    return "CURRENT_TIMESTAMP"


def _btc_amount_expr(conn: duckdb.DuckDBPyConnection) -> str:
    if _has_column(conn, "utxo_lifecycle", "btc_value"):
        return "u.btc_value"
    if _has_column(conn, "utxo_lifecycle", "amount"):
        return "CAST(u.amount AS DOUBLE) / 100000000.0"
    return "0.0"


def _unspent_filter(conn: duckdb.DuckDBPyConnection) -> str:
    if _has_column(conn, "utxo_lifecycle", "is_spent"):
        return "WHERE u.is_spent = FALSE OR u.is_spent IS NULL"
    return ""


def aggregate_flows(db_path: str | None = None, sample_limit: int | None = None) -> dict[str, int]:
    target_path = db_path or DUCKDB_PATH
    print(f"Aggregating flows in {target_path}...")

    with duckdb.connect(target_path) as conn:
        create_flow_artifact_tables(conn)

        ts_expr = _timestamp_expr(conn)
        btc_expr = _btc_amount_expr(conn)
        unspent_filter = _unspent_filter(conn)
        limit_clause = f"LIMIT {int(sample_limit)}" if sample_limit is not None else ""
        has_entity_map = _table_exists(conn, "cluster_entity_map")
        entity_map_join = (
            "LEFT JOIN cluster_entity_map m ON c.cluster_id = m.cluster_id"
            if has_entity_map
            else ""
        )
        mapped_entity_id_expr = (
            "COALESCE(m.entity_id, 'btc:entity:cluster:' || c.cluster_id)"
            if has_entity_map
            else "'btc:entity:cluster:' || c.cluster_id"
        )

        print("Identifying movement events...")
        conn.execute(
            f"""
            INSERT OR REPLACE INTO entity_movement_events
            SELECT
                u.txid,
                {ts_expr} AS ts,
                'btc:entity:cluster:unknown' AS source_entity_id,
                CASE
                    WHEN c.cluster_id IS NOT NULL THEN {mapped_entity_id_expr}
                    ELSE 'btc:entity:cluster:unknown'
                END AS target_entity_id,
                {btc_expr} AS btc_amount,
                CASE
                    WHEN c.cluster_id IS NULL THEN 'ambiguous'
                    ELSE 'unlabeled_to_entity'
                END AS classification,
                CASE
                    WHEN c.cluster_id IS NULL THEN 0.0
                    ELSE 0.6
                END AS confidence
            FROM utxo_lifecycle u
            LEFT JOIN address_clusters c ON u.address = c.address
            {entity_map_join}
            WHERE {btc_expr} IS NOT NULL
            {limit_clause}
            """
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO entity_transfer_edges
            SELECT
                txid,
                ts,
                source_entity_id,
                target_entity_id,
                btc_amount,
                CASE
                    WHEN source_entity_id = target_entity_id
                        AND source_entity_id <> 'btc:entity:cluster:unknown'
                        THEN 'internal_entity_reshuffle'
                    ELSE classification
                END AS movement_classification,
                confidence,
                source_entity_id = target_entity_id
                    AND source_entity_id <> 'btc:entity:cluster:unknown' AS is_internal
            FROM entity_movement_events
            """
        )

        print("Calculating daily flow aggregates...")
        conn.execute(
            """
            INSERT OR REPLACE INTO entity_flows_daily
            SELECT
                target_entity_id AS entity_id,
                CAST(ts AS DATE) AS date,
                SUM(
                    CASE
                        WHEN movement_classification IN ('exchange_inflow', 'entity_to_entity', 'unlabeled_to_entity')
                            THEN btc_amount
                        ELSE 0.0
                    END
                ) AS inflow_btc,
                SUM(
                    CASE
                        WHEN movement_classification IN ('exchange_outflow', 'entity_to_unlabeled')
                            THEN btc_amount
                        ELSE 0.0
                    END
                ) AS outflow_btc,
                SUM(
                    CASE
                        WHEN movement_classification IN ('exchange_inflow', 'entity_to_entity', 'unlabeled_to_entity')
                            THEN btc_amount
                        WHEN movement_classification IN ('exchange_outflow', 'entity_to_unlabeled')
                            THEN -btc_amount
                        ELSE 0.0
                    END
                ) AS netflow_btc,
                FALSE AS is_exchange
            FROM entity_transfer_edges
            GROUP BY entity_id, date
            """
        )

        if _should_write_questdb():
            rows = conn.execute(
                """
                SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange
                FROM entity_flows_daily
                ORDER BY date, entity_id
                """
            ).fetchall()
            failed_rows: list[tuple[str, _date, str]] = []
            for row in rows:
                try:
                    save_entity_flows_daily(
                        entity_id=row[0],
                        date=row[1],
                        inflow_btc=row[2],
                        outflow_btc=row[3],
                        netflow_btc=row[4],
                        is_exchange=row[5],
                    )
                except Exception as exc:
                    failed_rows.append((row[0], row[1], type(exc).__name__))
                    logger.error(
                        "entity_flows_daily QuestDB save failed: entity_id=%s date=%s exc=%s",
                        row[0],
                        row[1],
                        exc,
                        exc_info=True,
                    )
            if failed_rows:
                try:
                    _post_aggregated_webhook(failed_rows)
                except Exception as webhook_exc:
                    logger.warning(
                        "entity_flows_daily aggregated webhook failed "
                        "(suppressed): %s",
                        webhook_exc,
                    )
        else:
            logger.info(
                "spec-063 entity_flows_daily QuestDB write half disabled by SPEC063_QUESTDB_WRITE=%s",
                os.environ.get("SPEC063_QUESTDB_WRITE", ""),
            )

        print("Calculating daily balance snapshots...")
        conn.execute(
            f"""
            INSERT OR REPLACE INTO entity_balance_snapshots_daily
            SELECT
                {mapped_entity_id_expr} AS entity_id,
                CAST({ts_expr} AS DATE) AS date,
                SUM({btc_expr}) AS balance_btc
            FROM utxo_lifecycle u
            JOIN address_clusters c ON u.address = c.address
            {entity_map_join}
            {unspent_filter}
            GROUP BY {mapped_entity_id_expr}, CAST({ts_expr} AS DATE)
            """
        )

        print("Calculating daily counterparty edges...")
        conn.execute(
            """
            INSERT OR REPLACE INTO entity_counterparty_edges_daily
            SELECT
                CAST(CAST(ts AS DATE) AS TIMESTAMP) AS window_start,
                CAST(CAST(ts AS DATE) AS TIMESTAMP) + INTERVAL 1 DAY AS window_end,
                source_entity_id,
                target_entity_id,
                movement_classification,
                SUM(btc_amount) AS btc_amount,
                MIN(attribution_confidence) AS attribution_confidence,
                BOOL_OR(is_internal) AS is_internal,
                CASE
                    WHEN SUM(CASE WHEN movement_classification = 'ambiguous' THEN 1 ELSE 0 END) > 0
                        THEN 'partial_materialization'
                    ELSE 'healthy'
                END AS materialization_status
            FROM entity_transfer_edges
            GROUP BY
                window_start,
                window_end,
                source_entity_id,
                target_entity_id,
                movement_classification
            """
        )

        return {
            "entity_movement_events": int(conn.execute("SELECT COUNT(*) FROM entity_movement_events").fetchone()[0]),
            "entity_transfer_edges": int(conn.execute("SELECT COUNT(*) FROM entity_transfer_edges").fetchone()[0]),
            "entity_flows_daily": int(conn.execute("SELECT COUNT(*) FROM entity_flows_daily").fetchone()[0]),
            "entity_balance_snapshots_daily": int(conn.execute("SELECT COUNT(*) FROM entity_balance_snapshots_daily").fetchone()[0]),
            "entity_counterparty_edges_daily": int(conn.execute("SELECT COUNT(*) FROM entity_counterparty_edges_daily").fetchone()[0]),
        }


if __name__ == "__main__":
    aggregate_flows()
