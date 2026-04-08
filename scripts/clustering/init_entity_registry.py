import duckdb
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH

def init_registry():
    print(f"Initializing Entity Registry in {DUCKDB_PATH}...")
    conn = duckdb.connect(DUCKDB_PATH)
    
    # 1. entity_registry
    conn.execute("""
    CREATE TABLE IF NOT EXISTS entity_registry (
        entity_id VARCHAR PRIMARY KEY,
        entity_kind VARCHAR,
        registry_status VARCHAR,
        display_label VARCHAR,
        confidence_overall DOUBLE,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP
    )
    """)
    
    # 2. cluster_entity_map
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cluster_entity_map (
        cluster_id VARCHAR PRIMARY KEY,
        entity_id VARCHAR,
        mapping_confidence DOUBLE,
        mapping_method VARCHAR,
        mapping_version VARCHAR,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP
    )
    """)
    
    # 3. entity_labels
    conn.execute("""
    CREATE TABLE IF NOT EXISTS entity_labels (
        entity_id VARCHAR,
        label VARCHAR,
        label_kind VARCHAR,
        label_confidence DOUBLE,
        is_primary BOOLEAN,
        PRIMARY KEY (entity_id, label)
    )
    """)
    
    # 4. entity_label_provenance
    conn.execute("""
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
    """)
    
    print("✅ Entity Registry tables initialized.")
    conn.close()

if __name__ == "__main__":
    init_registry()
