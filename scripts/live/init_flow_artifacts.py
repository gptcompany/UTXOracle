from __future__ import annotations

import duckdb
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH


def create_flow_artifact_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_movement_events (
            txid VARCHAR,
            ts TIMESTAMP,
            source_entity_id VARCHAR,
            target_entity_id VARCHAR,
            btc_amount DOUBLE,
            classification VARCHAR,
            confidence DOUBLE,
            PRIMARY KEY (txid, source_entity_id, target_entity_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_transfer_edges (
            txid VARCHAR,
            ts TIMESTAMP,
            source_entity_id VARCHAR,
            target_entity_id VARCHAR,
            btc_amount DOUBLE,
            movement_classification VARCHAR,
            attribution_confidence DOUBLE,
            is_internal BOOLEAN,
            PRIMARY KEY (txid, source_entity_id, target_entity_id, movement_classification)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_flows_daily (
            entity_id VARCHAR,
            date DATE,
            inflow_btc DOUBLE,
            outflow_btc DOUBLE,
            netflow_btc DOUBLE,
            is_exchange BOOLEAN,
            PRIMARY KEY (entity_id, date)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_balance_snapshots_daily (
            entity_id VARCHAR,
            date DATE,
            balance_btc DOUBLE,
            PRIMARY KEY (entity_id, date)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_counterparty_edges_daily (
            window_start TIMESTAMP,
            window_end TIMESTAMP,
            source_entity_id VARCHAR,
            target_entity_id VARCHAR,
            movement_classification VARCHAR,
            btc_amount DOUBLE,
            attribution_confidence DOUBLE,
            is_internal BOOLEAN,
            materialization_status VARCHAR,
            PRIMARY KEY (
                window_start,
                source_entity_id,
                target_entity_id,
                movement_classification
            )
        )
        """
    )


def init_flow(db_path: str | None = None) -> None:
    target_path = db_path or DUCKDB_PATH
    print(f"Initializing Flow Artifacts in {target_path}...")
    with duckdb.connect(target_path) as conn:
        create_flow_artifact_tables(conn)
    print("✅ Flow Artifacts tables initialized.")


if __name__ == "__main__":
    init_flow()
