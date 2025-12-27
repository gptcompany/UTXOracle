"""
UTXOracle centralized configuration package.

Exports:
    UTXORACLE_DB_PATH: Path to the main UTXOracle database
    get_connection: Helper to get DuckDB connection
"""

from scripts.config.database import UTXORACLE_DB_PATH, get_connection

__all__ = ["UTXORACLE_DB_PATH", "get_connection"]
