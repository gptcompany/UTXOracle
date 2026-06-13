from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from scripts.metrics.materialize_urpd_features import (
    REQUIRED_URPD_FEATURE_FIELDS,
    URPD_FEATURE_SCHEMA_VERSION,
    materialize_urpd_features_row,
)


class FakeRepo:
    def __init__(self):
        self.rows = []
        self.aborted = False

    def save_urpd_features(self, result):
        self.rows.append(result)
        return True

    def abort_ingestion(self):
        self.aborted = True


def _conn_with_supporting_tables() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE block_heights (
            height INTEGER,
            timestamp BIGINT,
            block_hash VARCHAR
        )
        """
    )
    conn.execute(
        """
        INSERT INTO block_heights VALUES
        (90, 900, 'h90'),
        (100, 1000, 'h100'),
        (110, 1100, 'h110')
        """
    )
    conn.execute("CREATE TABLE daily_prices (date DATE, price_usd DOUBLE)")
    conn.execute("INSERT INTO daily_prices VALUES ('1970-01-01', 80000.0)")
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle_full (
            txid VARCHAR,
            vout_index INTEGER,
            creation_block INTEGER,
            btc_value DOUBLE,
            creation_price_usd DOUBLE,
            realized_value_usd DOUBLE,
            is_spent BOOLEAN,
            spent_block INTEGER
        )
        """
    )
    return conn


@pytest.mark.asyncio
async def test_empty_utxo_set_materializes_null_scalar_metrics():
    conn = _conn_with_supporting_tables()

    result = await materialize_urpd_features_row(
        FakeRepo(),
        conn,
        datetime.fromtimestamp(1000, tz=timezone.utc),
        bucket_size_usd=10000.0,
        dry_run=True,
    )

    conn.close()

    assert result.total_supply_btc == pytest.approx(0.0)
    assert result.supply_below_price_pct is None
    assert result.supply_above_price_pct is None
    assert result.top_bucket_concentration is None
    assert result.dominant_bucket_distance_pct is None
    assert result.distribution_entropy is None
    assert result.confidence == pytest.approx(0.0)
    assert result.source_health["status"] == "empty"


@pytest.mark.asyncio
async def test_missing_creation_price_is_excluded_and_reported_in_source_health():
    conn = _conn_with_supporting_tables()
    conn.execute(
        """
        INSERT INTO utxo_lifecycle_full VALUES
        ('priced', 0, 95, 2.0, 60000.0, 120000.0, FALSE, NULL),
        ('missing', 0, 95, 3.0, NULL, NULL, FALSE, NULL)
        """
    )

    result = await materialize_urpd_features_row(
        FakeRepo(),
        conn,
        datetime.fromtimestamp(1000, tz=timezone.utc),
        bucket_size_usd=10000.0,
        dry_run=True,
    )

    conn.close()

    assert result.total_supply_btc == pytest.approx(2.0)
    assert result.top_bucket_concentration == pytest.approx(100.0)
    assert result.source_health["status"] == "degraded"
    assert result.source_health["visible_utxos"] == 2
    assert result.source_health["priced_utxos"] == 1
    assert result.source_health["missing_creation_price_utxos"] == 1
    assert result.source_health["creation_price_coverage_pct"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_all_missing_creation_prices_emit_null_distribution_supply_not_zero():
    conn = _conn_with_supporting_tables()
    conn.execute(
        """
        INSERT INTO utxo_lifecycle_full VALUES
        ('missing_a', 0, 95, 2.0, NULL, NULL, FALSE, NULL),
        ('missing_b', 0, 95, 3.0, NULL, NULL, FALSE, NULL)
        """
    )

    result = await materialize_urpd_features_row(
        FakeRepo(),
        conn,
        datetime.fromtimestamp(1000, tz=timezone.utc),
        bucket_size_usd=10000.0,
        dry_run=True,
    )

    conn.close()

    assert result.total_supply_btc is None
    assert result.top_bucket_concentration is None
    assert result.distribution_entropy is None
    assert result.confidence == pytest.approx(0.0)
    assert result.source_health["status"] == "degraded"
    assert result.source_health["visible_supply_btc"] == pytest.approx(5.0)
    assert result.source_health["priced_supply_btc"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_spent_utxo_exclusion_is_point_in_time_by_block_height():
    conn = _conn_with_supporting_tables()
    conn.execute(
        """
        INSERT INTO utxo_lifecycle_full VALUES
        ('live', 0, 95, 1.0, 40000.0, 40000.0, FALSE, NULL),
        ('spent_after_target', 0, 95, 2.0, 60000.0, 120000.0, TRUE, 110),
        ('spent_before_target', 0, 95, 4.0, 70000.0, 280000.0, TRUE, 99),
        ('created_after_target', 0, 105, 8.0, 50000.0, 400000.0, FALSE, NULL)
        """
    )

    result = await materialize_urpd_features_row(
        FakeRepo(),
        conn,
        datetime.fromtimestamp(1000, tz=timezone.utc),
        bucket_size_usd=10000.0,
        dry_run=True,
    )

    conn.close()

    assert result.block_height == 100
    assert result.total_supply_btc == pytest.approx(3.0)
    assert result.supply_below_price_pct == pytest.approx(100.0)
    assert result.top_bucket_concentration == pytest.approx(66.666666, rel=0.01)


@pytest.mark.asyncio
async def test_dominant_bucket_distance_and_entropy_are_stable():
    conn = _conn_with_supporting_tables()
    conn.execute(
        """
        INSERT INTO utxo_lifecycle_full VALUES
        ('a', 0, 95, 1.0, 40000.0, 40000.0, FALSE, NULL),
        ('b', 0, 95, 3.0, 90000.0, 270000.0, FALSE, NULL)
        """
    )

    result = await materialize_urpd_features_row(
        FakeRepo(),
        conn,
        datetime.fromtimestamp(1000, tz=timezone.utc),
        bucket_size_usd=10000.0,
        dry_run=True,
    )

    conn.close()

    assert result.top_bucket_concentration == pytest.approx(75.0)
    assert result.dominant_bucket_distance_pct == pytest.approx(18.75)
    assert result.distribution_entropy == pytest.approx(0.811278, rel=0.01)


def test_urpd_feature_schema_contract_is_stable():
    assert REQUIRED_URPD_FEATURE_FIELDS == (
        "ts",
        "availability_timestamp",
        "block_height",
        "current_price_usd",
        "bucket_size_usd",
        "total_supply_btc",
        "supply_below_price_pct",
        "supply_above_price_pct",
        "top_bucket_concentration",
        "dominant_bucket_distance_pct",
        "distribution_entropy",
        "confidence",
        "schema_version",
    )
    assert URPD_FEATURE_SCHEMA_VERSION == "urpd_features_daily.v1"
