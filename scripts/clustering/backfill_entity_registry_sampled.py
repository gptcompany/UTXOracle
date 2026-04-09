from __future__ import annotations

import duckdb
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.config import DUCKDB_PATH
from scripts.clustering.init_entity_registry import create_entity_registry_tables


def backfill(sample_limit: int | None = None, db_path: str | None = None) -> dict[str, int]:
    target_path = db_path or DUCKDB_PATH
    mode = "full" if sample_limit is None else f"sampled({sample_limit})"
    print(f"Backfilling Entity Registry from {target_path} [{mode}]...")
    start_time = time.time()

    with duckdb.connect(target_path) as conn:
        create_entity_registry_tables(conn)

        print("Extracting labeled clusters...")
        conn.execute("DROP TABLE IF EXISTS source_clusters")
        conn.execute(
            """
            CREATE TEMP TABLE source_clusters AS
            SELECT
                cluster_id,
                max(label) AS label,
                min(first_seen) AS first_seen,
                max(last_seen) AS last_seen
            FROM address_clusters
            WHERE label IS NOT NULL
            GROUP BY cluster_id
            """
        )

        if sample_limit is None:
            print("Adding all unlabeled clusters...")
            unlabeled_limit_clause = ""
        else:
            print(f"Adding sample of {sample_limit} unlabeled clusters...")
            unlabeled_limit_clause = f"LIMIT {int(sample_limit)}"
        conn.execute(
            f"""
            INSERT INTO source_clusters
            SELECT
                cluster_id,
                NULL AS label,
                min(first_seen) AS first_seen,
                max(last_seen) AS last_seen
            FROM address_clusters
            WHERE label IS NULL
            GROUP BY cluster_id
            ORDER BY cluster_id
            {unlabeled_limit_clause}
            """
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO entity_registry
            SELECT
                'btc:entity:cluster:' || cluster_id,
                'unknown',
                'active',
                label,
                CASE WHEN label IS NOT NULL THEN 0.8 ELSE 0.6 END,
                first_seen,
                last_seen
            FROM source_clusters
            """
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO cluster_entity_map
            SELECT
                cluster_id,
                'btc:entity:cluster:' || cluster_id,
                0.8,
                CASE WHEN label IS NOT NULL THEN 0.8 ELSE 0.6 END,
                'direct_cluster_backfill',
                'v1',
                first_seen,
                last_seen
            FROM source_clusters
            """
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO entity_labels
            SELECT
                'btc:entity:cluster:' || cluster_id,
                label,
                'primary',
                0.8,
                TRUE
            FROM source_clusters
            WHERE label IS NOT NULL
            """
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO entity_label_provenance
            SELECT
                'btc:entity:cluster:' || cluster_id,
                label,
                'inherited_cluster_label',
                'address_clusters_table',
                'spec-013',
                now(),
                'unreviewed',
                'v1'
            FROM source_clusters
            WHERE label IS NOT NULL
            """
        )

        entity_count = int(conn.execute("SELECT COUNT(*) FROM entity_registry").fetchone()[0])
        mapping_count = int(conn.execute("SELECT COUNT(*) FROM cluster_entity_map").fetchone()[0])

    print(f"✅ Sampled Entity Registry backfill complete in {time.time() - start_time:.2f}s.")
    return {"entity_registry": entity_count, "cluster_entity_map": mapping_count}


if __name__ == "__main__":
    backfill()
