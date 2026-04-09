from __future__ import annotations

import duckdb
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH
from scripts.live.init_flow_artifacts import create_flow_artifact_tables


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
