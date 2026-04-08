import duckdb
import os
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH

def backfill():
    print(f"Sampled Backfilling Entity Registry from {DUCKDB_PATH}...")
    conn = duckdb.connect(DUCKDB_PATH)
    
    start_time = time.time()
    
    # 1. Extract labeled clusters
    print("Extracting labeled clusters...")
    conn.execute("""
    CREATE TEMP TABLE source_clusters AS
    SELECT 
        cluster_id, 
        max(label) as label,
        min(first_seen) as first_seen,
        max(last_seen) as last_seen
    FROM address_clusters
    WHERE label IS NOT NULL
    GROUP BY cluster_id
    """)
    
    # 2. Add some unlabeled ones (sample 1000)
    print("Adding sample of unlabeled clusters...")
    conn.execute("""
    INSERT INTO source_clusters
    SELECT 
        cluster_id, 
        NULL as label,
        min(first_seen) as first_seen,
        max(last_seen) as last_seen
    FROM address_clusters
    WHERE label IS NULL
    GROUP BY cluster_id
    LIMIT 1000
    """)
    
    print(f"Source clusters (labeled + 1000 sample) extracted in {time.time() - start_time:.2f}s")
    
    # 3. Populate tables
    conn.execute("""
    INSERT OR IGNORE INTO entity_registry 
    SELECT 'btc:entity:cluster:' || cluster_id, 'unknown', 'active', label, 
           CASE WHEN label IS NOT NULL THEN 0.8 ELSE 0.6 END, first_seen, last_seen
    FROM source_clusters
    """)
    
    conn.execute("""
    INSERT OR IGNORE INTO cluster_entity_map
    SELECT cluster_id, 'btc:entity:cluster:' || cluster_id, 1.0, 'direct_mih_inheritance', 'v1', first_seen, last_seen
    FROM source_clusters
    """)
    
    conn.execute("""
    INSERT OR IGNORE INTO entity_labels 
    SELECT 'btc:entity:cluster:' || cluster_id, label, 'inherited', 0.8, TRUE
    FROM source_clusters WHERE label IS NOT NULL
    """)
    
    conn.execute("""
    INSERT OR IGNORE INTO entity_label_provenance 
    SELECT 'btc:entity:cluster:' || cluster_id, label, 'inherited_cluster_label', 'address_clusters_table', 'spec-013', now(), 'unreviewed', 'v1'
    FROM source_clusters WHERE label IS NOT NULL
    """)
    
    print(f"✅ Sampled Entity Registry backfill complete in {time.time() - start_time:.2f}s.")
    conn.close()

if __name__ == "__main__":
    backfill()
