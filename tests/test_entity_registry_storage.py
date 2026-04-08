from __future__ import annotations

from pathlib import Path

import duckdb

from scripts.clustering.backfill_entity_registry_sampled import backfill
from scripts.clustering.init_entity_registry import create_entity_registry_tables
from scripts.live.flow_aggregator import aggregate_flows
from scripts.live.init_flow_artifacts import create_flow_artifact_tables


def _build_test_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE address_clusters (
            address VARCHAR,
            cluster_id VARCHAR,
            label VARCHAR,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO address_clusters VALUES
        ('addr_1', 'cluster_001', 'Binance', TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-02 00:00:00'),
        ('addr_2', 'cluster_002', NULL, TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-03 00:00:00')
        """
    )
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            txid VARCHAR,
            address VARCHAR,
            ts TIMESTAMP,
            btc_value DOUBLE,
            is_spent BOOLEAN
        )
        """
    )
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('tx_1', 'addr_1', TIMESTAMP '2026-04-02 12:00:00', 10.0, FALSE),
        ('tx_2', 'addr_2', TIMESTAMP '2026-04-03 12:00:00', 5.0, FALSE)
        """
    )
    conn.close()


def test_entity_registry_and_flow_tables_exist(tmp_path: Path):
    db_path = tmp_path / "entity_registry.duckdb"
    conn = duckdb.connect(str(db_path))
    create_entity_registry_tables(conn)
    create_flow_artifact_tables(conn)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()

    assert "entity_registry" in tables
    assert "cluster_entity_map" in tables
    assert "entity_labels" in tables
    assert "entity_label_provenance" in tables
    assert "entity_movement_events" in tables
    assert "entity_transfer_edges" in tables
    assert "entity_flows_daily" in tables
    assert "entity_balance_snapshots_daily" in tables
    assert "entity_counterparty_edges_daily" in tables


def test_backfill_uses_canonical_entity_id_and_component_confidence(tmp_path: Path):
    db_path = tmp_path / "entity_backfill.duckdb"
    _build_test_db(db_path)

    stats = backfill(sample_limit=10, db_path=str(db_path))
    conn = duckdb.connect(str(db_path))
    row = conn.execute(
        """
        SELECT entity_id, cluster_confidence, mapping_confidence
        FROM cluster_entity_map
        WHERE cluster_id = 'cluster_001'
        """
    ).fetchone()
    label_row = conn.execute(
        """
        SELECT label_kind, label_confidence, is_primary
        FROM entity_labels
        WHERE entity_id = 'btc:entity:cluster:cluster_001'
        """
    ).fetchone()
    conn.close()

    assert stats["entity_registry"] >= 2
    assert row == ("btc:entity:cluster:cluster_001", 0.8, 0.8)
    assert label_row == ("primary", 0.8, True)


def test_flow_aggregation_populates_counterparty_and_balance_artifacts(tmp_path: Path):
    db_path = tmp_path / "entity_flows.duckdb"
    _build_test_db(db_path)
    backfill(sample_limit=10, db_path=str(db_path))

    stats = aggregate_flows(db_path=str(db_path))
    conn = duckdb.connect(str(db_path))
    edge_row = conn.execute(
        """
        SELECT movement_classification, materialization_status
        FROM entity_counterparty_edges_daily
        ORDER BY window_start ASC
        LIMIT 1
        """
    ).fetchone()
    balance_row = conn.execute(
        """
        SELECT entity_id, balance_btc
        FROM entity_balance_snapshots_daily
        ORDER BY entity_id ASC
        LIMIT 1
        """
    ).fetchone()
    conn.close()

    assert stats["entity_transfer_edges"] > 0
    assert stats["entity_counterparty_edges_daily"] > 0
    assert edge_row[0] in {"unlabeled_to_entity", "ambiguous"}
    assert edge_row[1] in {"healthy", "partial_materialization"}
    assert balance_row[0].startswith("btc:entity:cluster:")
    assert balance_row[1] > 0
