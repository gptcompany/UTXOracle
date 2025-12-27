"""
TDD tests for scripts/config.py module.

Tests verify:
1. UTXORACLE_DB_PATH path resolution
2. get_connection() helper returns valid DuckDB connection
3. Environment variable override works
"""

import os
import pytest
import duckdb
from pathlib import Path
from unittest.mock import patch


class TestUTXOracleDBPath:
    """Tests for UTXORACLE_DB_PATH configuration."""

    def test_default_path_is_data_utxoracle_duckdb(self):
        """Default path should be data/utxoracle.duckdb."""
        # Clear any existing env var
        with patch.dict(os.environ, {}, clear=True):
            # Need to reimport to get fresh value
            import importlib
            import scripts.config as config_module

            importlib.reload(config_module)

            assert config_module.UTXORACLE_DB_PATH == Path("data/utxoracle.duckdb")

    def test_env_var_overrides_default(self, tmp_path):
        """UTXORACLE_DB_PATH env var should override default."""
        custom_path = str(tmp_path / "custom.duckdb")

        with patch.dict(os.environ, {"UTXORACLE_DB_PATH": custom_path}):
            import importlib
            import scripts.config.database as db_module
            import scripts.config as config_module

            importlib.reload(db_module)
            importlib.reload(config_module)

            assert config_module.UTXORACLE_DB_PATH == Path(custom_path)

    def test_path_is_pathlib_path(self):
        """UTXORACLE_DB_PATH should be a pathlib.Path object."""
        from scripts.config import UTXORACLE_DB_PATH

        assert isinstance(UTXORACLE_DB_PATH, Path)


class TestGetConnection:
    """Tests for get_connection() helper."""

    def test_returns_duckdb_connection(self, tmp_path):
        """get_connection() should return a DuckDB connection."""
        db_path = tmp_path / "test.duckdb"

        with patch.dict(os.environ, {"UTXORACLE_DB_PATH": str(db_path)}):
            import importlib
            import scripts.config as config_module

            importlib.reload(config_module)

            conn = config_module.get_connection()
            assert isinstance(conn, duckdb.DuckDBPyConnection)
            conn.close()

    def test_read_only_mode(self, tmp_path):
        """get_connection(read_only=True) should open in read-only mode."""
        db_path = tmp_path / "test_ro.duckdb"

        # Create the database first
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        with patch.dict(os.environ, {"UTXORACLE_DB_PATH": str(db_path)}):
            import importlib
            import scripts.config.database as db_module
            import scripts.config as config_module

            importlib.reload(db_module)
            importlib.reload(config_module)

            conn = config_module.get_connection(read_only=True)

            # Should be able to read
            conn.execute("SELECT * FROM test")

            # Should not be able to write
            with pytest.raises(duckdb.InvalidInputException):
                conn.execute("INSERT INTO test VALUES (1)")

            conn.close()

    def test_connection_uses_configured_path(self, tmp_path):
        """Connection should use the configured UTXORACLE_DB_PATH."""
        db_path = tmp_path / "configured.duckdb"

        with patch.dict(os.environ, {"UTXORACLE_DB_PATH": str(db_path)}):
            import importlib
            import scripts.config.database as db_module
            import scripts.config as config_module

            importlib.reload(db_module)
            importlib.reload(config_module)

            conn = config_module.get_connection()
            conn.execute("CREATE TABLE marker (id INTEGER)")
            conn.close()

            # Verify the file was created at the configured path
            assert db_path.exists()


class TestConfigModuleExports:
    """Tests for module exports."""

    def test_exports_utxoracle_db_path(self):
        """Module should export UTXORACLE_DB_PATH."""
        from scripts.config import UTXORACLE_DB_PATH

        assert UTXORACLE_DB_PATH is not None

    def test_exports_get_connection(self):
        """Module should export get_connection function."""
        from scripts.config import get_connection

        assert callable(get_connection)
