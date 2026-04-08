import pytest
import duckdb
import os
from pathlib import Path
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from api.config import DUCKDB_PATH

@pytest.fixture
def db_conn():
    conn = duckdb.connect(DUCKDB_PATH)
    yield conn
    conn.close()

def test_entity_registry_tables_exist(db_conn):
    """Verify that all spec-053 registry tables exist in DuckDB."""
    tables = db_conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    assert "entity_registry" in table_names
    assert "cluster_entity_map" in table_names
    assert "entity_labels" in table_names
    assert "entity_label_provenance" in table_names

def test_entity_id_format(db_conn):
    """Verify that entity_id follows the canonical format."""
    rows = db_conn.execute("SELECT entity_id FROM entity_registry LIMIT 10").fetchall()
    for row in rows:
        assert row[0].startswith("btc:entity:")

def test_registry_backfill_integrity(db_conn):
    """Verify that cluster_entity_map correctly links clusters to entities."""
    row = db_conn.execute("""
        SELECT c.cluster_id, m.entity_id 
        FROM address_clusters c
        JOIN cluster_entity_map m ON c.cluster_id = m.cluster_id
        LIMIT 1
    """).fetchone()
    
    assert row is not None
    assert f"btc:entity:cluster:{row[0]}" == row[1]
