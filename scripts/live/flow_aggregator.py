import duckdb
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH

def aggregate_flows():
    print(f"Aggregating flows in {DUCKDB_PATH}...")
    conn = duckdb.connect(DUCKDB_PATH)
    
    # 1. Identify cross-cluster movements (Simplified for T036 proof-of-concept)
    print("Identifying movement events...")
    conn.execute("""
    INSERT OR IGNORE INTO entity_movement_events (txid, ts, source_entity_id, target_entity_id, btc_amount, classification, confidence)
    SELECT 
        u.txid,
        u.created_at as ts,
        'btc:entity:cluster:unknown' as source_entity_id,
        'btc:entity:cluster:' || COALESCE(c.cluster_id, 'unknown') as target_entity_id,
        u.amount / 100000000.0 as btc_amount,
        'entity_to_entity' as classification,
        0.9 as confidence
    FROM utxo_lifecycle u
    LEFT JOIN address_clusters c ON u.address = c.address
    LIMIT 1000
    """)
    
    # 2. Daily aggregates
    print("Calculating daily flows...")
    conn.execute("""
    INSERT OR IGNORE INTO entity_flows_daily (entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange)
    SELECT 
        target_entity_id as entity_id,
        CAST(ts AS DATE) as date,
        sum(btc_amount) as inflow_btc,
        0.0 as outflow_btc,
        sum(btc_amount) as netflow_btc,
        FALSE as is_exchange
    FROM entity_movement_events
    GROUP BY entity_id, date
    """)
    
    print("✅ Flow aggregation complete.")
    conn.close()

if __name__ == "__main__":
    aggregate_flows()
