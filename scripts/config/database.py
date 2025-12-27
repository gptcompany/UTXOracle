"""
UTXOracle centralized configuration module.

Provides database path configuration and connection helpers.
All scripts should import from here instead of hardcoding paths.

Usage:
    from scripts.config import UTXORACLE_DB_PATH, get_connection

    # Read-only access
    conn = get_connection(read_only=True)

    # Read-write access
    conn = get_connection()
"""

import os
from pathlib import Path

import duckdb


# Default database path - can be overridden via environment variable
UTXORACLE_DB_PATH = Path(os.getenv("UTXORACLE_DB_PATH", "data/utxoracle.duckdb"))


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Get a DuckDB connection to the UTXOracle database.

    Args:
        read_only: If True, open connection in read-only mode

    Returns:
        DuckDB connection object

    Example:
        >>> conn = get_connection(read_only=True)
        >>> result = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()
        >>> conn.close()
    """
    return duckdb.connect(str(UTXORACLE_DB_PATH), read_only=read_only)
