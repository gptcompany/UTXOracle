import pytest
from unittest.mock import AsyncMock, MagicMock
import duckdb

from scripts.bootstrap.sync_clusters_to_questdb import sync_clusters
from api.questdb_repository import QuestDBRepository

@pytest.fixture
def mock_repo():
    repo = QuestDBRepository()
    repo.prepare_address_clusters_refresh = AsyncMock(return_value=True)
    repo.stage_address_cluster = MagicMock(return_value=True)
    repo.commit_address_clusters_refresh = AsyncMock(return_value=True)
    repo.abort_address_clusters_refresh = AsyncMock()
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
            last_seen TIMESTAMP
        )
        """
    )
    
    # Insert test data
    conn.execute(
        """
        INSERT INTO address_clusters VALUES
        ('addr1', 'cluster1', '2024-01-01', '2024-01-02'),
        ('addr2', 'cluster1', '2024-01-01', '2024-01-03'),
        ('addr3', 'cluster2', '2024-02-01', '2024-02-05')
        """
    )
    yield conn
    conn.close()

@pytest.mark.asyncio
async def test_sync_clusters_truncate_and_load(mock_repo, test_db):
    """T004-T006: Verify DuckDB clusters are properly formatted and synced."""
    success = await sync_clusters(mock_repo, test_db, batch_size=2)
    
    assert success is True
    
    # Verify staged refresh lifecycle
    mock_repo.prepare_address_clusters_refresh.assert_awaited_once()
    mock_repo.commit_address_clusters_refresh.assert_awaited_once()
    
    # Verify 3 rows staged
    assert mock_repo.stage_address_cluster.call_count == 3
    
    # Check default formatting against the minimal real DuckDB schema
    # The last row inserted is addr3
    staged_row = mock_repo.stage_address_cluster.call_args_list[2].args[0]
    
    assert staged_row["address"] == "addr3"
    assert staged_row["cluster_id"] == "cluster2"
    assert staged_row["is_exchange_likely"] is False
    assert staged_row["confidence"] == 0.6
    
    # Check unlabeled row formatting
    first_row = mock_repo.stage_address_cluster.call_args_list[0].args[0]
    assert first_row["address"] == "addr1"
    assert first_row["label"] is None
    assert first_row["confidence"] == 0.6

@pytest.mark.asyncio
async def test_sync_clusters_empty_db(mock_repo):
    """T007: Handle empty DuckDB gracefully without truncating QuestDB."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE address_clusters (address VARCHAR)")
    
    success = await sync_clusters(mock_repo, conn, batch_size=100)
    
    assert success is False
    assert mock_repo.prepare_address_clusters_refresh.await_count == 0
    assert mock_repo.stage_address_cluster.call_count == 0
    conn.close()


@pytest.mark.asyncio
async def test_sync_clusters_returns_false_on_ilp_failure(mock_repo, test_db):
    """TRUNCATE must not be reported as success when ILP ingestion fails."""
    mock_repo.stage_address_cluster = MagicMock(side_effect=[True, False])

    success = await sync_clusters(mock_repo, test_db, batch_size=2)

    assert success is False
    mock_repo.prepare_address_clusters_refresh.assert_awaited_once()
    mock_repo.commit_address_clusters_refresh.assert_not_awaited()
    mock_repo.abort_address_clusters_refresh.assert_awaited_once()
