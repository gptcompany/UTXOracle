from datetime import datetime, timezone

import duckdb
import pytest

from scripts.metrics.urpd_features import calculate_urpd_features_signal


def test_calculate_urpd_features_signal_derives_scalar_metrics():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            txid VARCHAR,
            vout_index INTEGER,
            creation_block INTEGER,
            btc_value DOUBLE,
            creation_price_usd DOUBLE,
            realized_value_usd DOUBLE,
            is_spent BOOLEAN
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('a', 0, 880000, 1.0, 40000.0, 40000.0, FALSE),
        ('b', 0, 870000, 2.0, 60000.0, 120000.0, FALSE),
        ('c', 0, 860000, 3.0, 90000.0, 270000.0, FALSE),
        ('d', 0, 850000, 4.0, 95000.0, 380000.0, FALSE)
        """
    )

    result = calculate_urpd_features_signal(
        conn=conn,
        current_price_usd=80000.0,
        current_block=900000,
        bucket_size_usd=10000.0,
        timestamp=datetime(2026, 4, 17, tzinfo=timezone.utc),
    )

    conn.close()

    assert result.block_height == 900000
    assert result.total_supply_btc == pytest.approx(10.0)
    assert result.supply_below_price_pct == pytest.approx(30.0)
    assert result.supply_above_price_pct == pytest.approx(70.0)
    assert result.top_cluster_concentration == pytest.approx(70.0)
    assert result.dominant_bucket_distance_pct == pytest.approx(18.75)
    assert 0.0 <= result.distribution_entropy <= 1.0
    assert result.confidence == pytest.approx(0.85)
