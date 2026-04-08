import duckdb
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH

def init_flow():
    print(f"Initializing Flow Artifacts in {DUCKDB_PATH}...")
    conn = duckdb.connect(DUCKDB_PATH)
    
    # 1. entity_movement_events
    conn.execute("""
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
    """)
    
    # 2. entity_flows_daily
    conn.execute("""
    CREATE TABLE IF NOT EXISTS entity_flows_daily (
        entity_id VARCHAR,
        date DATE,
        inflow_btc DOUBLE,
        outflow_btc DOUBLE,
        netflow_btc DOUBLE,
        is_exchange BOOLEAN,
        PRIMARY KEY (entity_id, date)
    )
    """)
    
    # 3. entity_balance_snapshots_daily
    conn.execute("""
    CREATE TABLE IF NOT EXISTS entity_balance_snapshots_daily (
        entity_id VARCHAR,
        date DATE,
        balance_btc DOUBLE,
        PRIMARY KEY (entity_id, date)
    )
    """)
    
    print("✅ Flow Artifacts tables initialized.")
    conn.close()

if __name__ == "__main__":
    init_flow()
