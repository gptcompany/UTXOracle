from __future__ import annotations

import duckdb
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH


def create_entity_registry_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_registry (
            entity_id VARCHAR PRIMARY KEY,
            entity_kind VARCHAR,
            registry_status VARCHAR,
            display_label VARCHAR,
            confidence_overall DOUBLE,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_entity_map (
            cluster_id VARCHAR PRIMARY KEY,
            entity_id VARCHAR,
            cluster_confidence DOUBLE,
            mapping_confidence DOUBLE,
            mapping_method VARCHAR,
            mapping_version VARCHAR,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_labels (
            entity_id VARCHAR,
            label VARCHAR,
            label_kind VARCHAR,
            label_confidence DOUBLE,
            is_primary BOOLEAN,
            PRIMARY KEY (entity_id, label)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_label_provenance (
            entity_id VARCHAR,
            label VARCHAR,
            source_kind VARCHAR,
            source_name VARCHAR,
            source_ref VARCHAR,
            ingested_at TIMESTAMP,
            review_status VARCHAR,
            method_version VARCHAR,
            PRIMARY KEY (entity_id, label, source_name)
        )
        """
    )


def init_registry(db_path: str | None = None) -> None:
    target_path = db_path or DUCKDB_PATH
    print(f"Initializing Entity Registry in {target_path}...")
    with duckdb.connect(target_path) as conn:
        create_entity_registry_tables(conn)
    print("✅ Entity Registry tables initialized.")


if __name__ == "__main__":
    init_registry()
