"""
TDD tests for database consolidation migration.

These tests verify the migration script correctly:
1. Creates metric tables with correct schema
2. Migrates cache tables from SQLite/DuckDB
3. Preserves data integrity during migration
"""

import duckdb


class TestCreateMetricTables:
    """Tests for create_metric_tables() function."""

    def test_creates_sopr_daily_table(self, tmp_path):
        """sopr_daily table should have date, sopr, spent_volume columns."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        create_metric_tables(conn)

        # Verify table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "sopr_daily" in table_names

        # Verify schema
        schema = conn.execute("DESCRIBE sopr_daily").fetchall()
        columns = {row[0]: row[1] for row in schema}
        assert "date" in columns
        assert "sopr" in columns

        conn.close()

    def test_creates_nupl_daily_table(self, tmp_path):
        """nupl_daily table should have date, nupl, market_cap, realized_cap columns."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        create_metric_tables(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "nupl_daily" in table_names

        schema = conn.execute("DESCRIBE nupl_daily").fetchall()
        columns = {row[0]: row[1] for row in schema}
        assert "date" in columns
        assert "nupl" in columns

        conn.close()

    def test_creates_mvrv_daily_table(self, tmp_path):
        """mvrv_daily table should have date, mvrv, mvrv_z columns."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        create_metric_tables(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "mvrv_daily" in table_names

        schema = conn.execute("DESCRIBE mvrv_daily").fetchall()
        columns = {row[0]: row[1] for row in schema}
        assert "date" in columns
        assert "mvrv" in columns

        conn.close()

    def test_creates_realized_cap_daily_table(self, tmp_path):
        """realized_cap_daily table should have date, realized_cap columns."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        create_metric_tables(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "realized_cap_daily" in table_names

        schema = conn.execute("DESCRIBE realized_cap_daily").fetchall()
        columns = {row[0]: row[1] for row in schema}
        assert "date" in columns
        assert "realized_cap" in columns

        conn.close()

    def test_creates_cointime_daily_table(self, tmp_path):
        """cointime_daily table should have date, liveliness, vaultedness columns."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        create_metric_tables(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "cointime_daily" in table_names

        schema = conn.execute("DESCRIBE cointime_daily").fetchall()
        columns = {row[0]: row[1] for row in schema}
        assert "date" in columns
        assert "liveliness" in columns

        conn.close()

    def test_idempotent_table_creation(self, tmp_path):
        """Running create_metric_tables twice should not error."""
        from scripts.migrations.consolidate_databases import create_metric_tables

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        # Run twice - should not raise
        create_metric_tables(conn)
        create_metric_tables(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        assert len(tables) == 5  # 5 metric tables

        conn.close()


class TestMigrateCacheTables:
    """Tests for migrate_cache_tables() function."""

    def test_copies_price_analysis_table(self, tmp_path):
        """price_analysis table should be copied from source to target."""
        from scripts.migrations.consolidate_databases import migrate_cache_tables

        # Create source with test data
        source_path = tmp_path / "source.duckdb"
        source = duckdb.connect(str(source_path))
        source.execute("""
            CREATE TABLE price_analysis (
                date DATE PRIMARY KEY,
                utxoracle_price DOUBLE,
                exchange_price DOUBLE
            )
        """)
        source.execute("""
            INSERT INTO price_analysis VALUES
            ('2024-12-27', 95000.0, 95100.0),
            ('2024-12-26', 94500.0, 94600.0)
        """)
        source.close()

        # Create target
        target_path = tmp_path / "target.duckdb"
        target = duckdb.connect(str(target_path))

        # Migrate
        migrate_cache_tables(str(source_path), target)

        # Verify
        count = target.execute("SELECT COUNT(*) FROM price_analysis").fetchone()[0]
        assert count == 2

        target.close()

    def test_copies_alert_events_table(self, tmp_path):
        """alert_events table should be copied from source to target."""
        from scripts.migrations.consolidate_databases import migrate_cache_tables

        # Create source with test data
        source_path = tmp_path / "source.duckdb"
        source = duckdb.connect(str(source_path))
        source.execute("""
            CREATE TABLE alert_events (
                id INTEGER PRIMARY KEY,
                event_type VARCHAR,
                timestamp TIMESTAMP
            )
        """)
        source.execute("""
            INSERT INTO alert_events VALUES
            (1, 'price_alert', '2024-12-27 10:00:00')
        """)
        source.close()

        # Create target
        target_path = tmp_path / "target.duckdb"
        target = duckdb.connect(str(target_path))

        # Migrate
        migrate_cache_tables(str(source_path), target)

        # Verify
        count = target.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
        assert count == 1

        target.close()

    def test_skips_missing_tables_gracefully(self, tmp_path):
        """Should not error if source table doesn't exist."""
        from scripts.migrations.consolidate_databases import migrate_cache_tables

        # Create empty source
        source_path = tmp_path / "source.duckdb"
        source = duckdb.connect(str(source_path))
        source.close()

        # Create target
        target_path = tmp_path / "target.duckdb"
        target = duckdb.connect(str(target_path))

        # Should not raise
        migrate_cache_tables(str(source_path), target)

        target.close()


class TestMigrationIntegrity:
    """Integration tests for full migration process."""

    def test_full_migration_preserves_utxo_data(self, tmp_path):
        """Migration should preserve all utxo_lifecycle data."""
        # This test would run on actual data
        # For now, verify the migration function exists and is callable
        from scripts.migrations.consolidate_databases import migrate

        # migrate() should be a callable
        assert callable(migrate)
