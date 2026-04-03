import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import duckdb
from datetime import datetime, timezone

from scripts.bootstrap.sync_clusters_to_questdb import sync_clusters
from api.questdb_repository import QuestDBRepository

@pytest.fixture
def mock_repo():
    repo = QuestDBRepository()
    repo._send_row = MagicMock(return_value=True)
    repo.execute = AsyncMock(return_value="TRUNCATE")
    repo.async_flush_ingestion = AsyncMock()
    return repo

@pytest.fixture
def test_db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE address_clusters (
            address VARCHAR PRIMARY KEY,
            cluster_id VARCHAR NOT NULL,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            is_exchange_likely BOOLEAN DEFAULT FALSE,
            label VARCHAR
        )
        """
    )
    
    # Insert test data
    conn.execute(
        """
        INSERT INTO address_clusters VALUES
        ('addr1', 'cluster1', '2024-01-01', '2024-01-02', FALSE, NULL),
        ('addr2', 'cluster1', '2024-01-01', '2024-01-03', FALSE, NULL),
        ('addr3', 'cluster2', '2024-02-01', '2024-02-05', TRUE, 'Binance')
        """
    )
    yield conn
    conn.close()

@pytest.mark.asyncio
async def test_sync_clusters_truncate_and_load(mock_repo, test_db):
    """T004-T006: Verify DuckDB clusters are properly formatted and synced."""
    success = await sync_clusters(mock_repo, test_db, batch_size=2)
    
    assert success is True
    
    # Verify truncate called
    mock_repo.execute.assert_called_once_with("TRUNCATE TABLE address_clusters")
    
    # Verify 3 rows sent
    assert mock_repo._send_row.call_count == 3
    
    # Check specific row formatting (Binance exchange)
    # The last row inserted is addr3 (Binance)
    args, kwargs = mock_repo._send_row.call_args_list[2]
    
    assert args[0] == "address_clusters"
    assert kwargs["symbols"]["label"] == "Binance"
    assert kwargs["columns"]["address"] == "addr3"
    assert kwargs["columns"]["cluster_id"] == "cluster2"
    assert kwargs["columns"]["is_exchange_likely"] is True
    # Should get 0.8 confidence because it has a label
    assert kwargs["columns"]["confidence"] == 0.8
    
    # Check unlabeled row formatting
    args, kwargs = mock_repo._send_row.call_args_list[0]
    assert kwargs["columns"]["address"] == "addr1"
    assert "label" not in kwargs["symbols"]  # Optional symbol omitted
    assert kwargs["columns"]["confidence"] == 0.6  # Default confidence

@pytest.mark.asyncio
async def test_sync_clusters_empty_db(mock_repo):
    """T007: Handle empty DuckDB gracefully without truncating QuestDB."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE address_clusters (address VARCHAR)")
    
    success = await sync_clusters(mock_repo, conn, batch_size=100)
    
    assert success is False
    assert mock_repo.execute.call_count == 0  # Should NOT truncate
    assert mock_repo._send_row.call_count == 0
    conn.close()
