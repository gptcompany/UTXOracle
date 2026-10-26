import pytest
from unittest.mock import AsyncMock, MagicMock
import duckdb

from scripts.bootstrap.sync_clusters_to_questdb import sync_clusters
from api.questdb_repository import QuestDBRepository


@pytest.fixture(autouse=True)
def _lock_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ADDRESS_CLUSTERS_LOCK_DIR", str(tmp_path / "locks"))


def _db_with_one_cluster(path):
    import duckdb as _duckdb

    conn = _duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE address_clusters (address VARCHAR, cluster_id VARCHAR, "
        "first_seen TIMESTAMP, last_seen TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO address_clusters VALUES ('a', 'c', '2024-01-01', '2024-01-02')"
    )
    conn.close()


@pytest.fixture
def mock_repo():
    repo = QuestDBRepository()
    repo.prepare_address_clusters_refresh = AsyncMock(return_value=True)
    repo.stage_address_cluster = MagicMock(return_value=True)
    repo.commit_address_clusters_refresh = AsyncMock(return_value=True)
    repo.abort_address_clusters_refresh = AsyncMock()
    repo.reconcile_address_clusters = AsyncMock()
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


@pytest.mark.asyncio
async def test_sync_clusters_is_refused_while_another_process_holds_the_lock(
    mock_repo, test_db, tmp_path
):
    """The bootstraps call sync_clusters directly: the lock must be inside it (R2)."""
    import fcntl
    import os

    from api.questdb_repository import ConcurrentRefreshError

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    fd = os.open(lock_dir / "address_clusters.lock", os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(ConcurrentRefreshError):
            await sync_clusters(mock_repo, test_db, batch_size=2)
    finally:
        os.close(fd)

    mock_repo.prepare_address_clusters_refresh.assert_not_awaited()
    mock_repo.abort_address_clusters_refresh.assert_not_awaited()
    assert mock_repo.stage_address_cluster.call_count == 0  # staging untouched


def test_ingest_to_db_exits_6_when_live_and_old_copies_are_both_gone(monkeypatch):
    import runpy

    from api.questdb_repository import AddressClustersLostError

    class _Repo:
        async def initialize(self):
            return None

        async def save_address_clusters_bulk(self, rows):
            raise AddressClustersLostError("restore address_clusters ...")

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path("scripts/bootstrap/ingest_to_db.py", run_name="__main__")
    assert exc.value.code == 6


def test_ingest_to_db_exits_5_when_the_swap_is_ok_but_cleanup_failed(monkeypatch):
    import runpy

    from api.questdb_repository import OldCopyCleanupError

    class _Repo:
        async def initialize(self):
            return None

        async def save_address_clusters_bulk(self, rows):
            raise OldCopyCleanupError(["address_clusters_old_20260101T000000Z"])

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path("scripts/bootstrap/ingest_to_db.py", run_name="__main__")
    assert exc.value.code == 5


def test_sync_main_exits_5_when_the_swap_is_ok_but_cleanup_failed(
    monkeypatch, tmp_path
):
    import runpy
    import sys

    from api.questdb_repository import OldCopyCleanupError

    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)

    class _Repo:
        async def initialize(self):
            return None

        async def close(self):
            return None

        async def refresh_address_clusters(self, producer):
            raise OldCopyCleanupError(["address_clusters_old_20260101T000000Z"])

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    assert exc.value.code == 5


def test_ingest_to_db_exits_nonzero_when_the_bulk_save_fails(monkeypatch):
    import runpy

    class _Repo:
        async def initialize(self):
            return None

        async def save_address_clusters_bulk(self, rows):
            return False

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path("scripts/bootstrap/ingest_to_db.py", run_name="__main__")
    assert exc.value.code == 1


def test_sync_main_exits_nonzero_when_the_sync_fails(monkeypatch, tmp_path):
    import runpy
    import sys

    import duckdb as _duckdb

    db = tmp_path / "x.duckdb"
    _duckdb.connect(str(db)).close()

    class _Repo:
        async def initialize(self):
            return None

        async def close(self):
            return None

        async def prepare_address_clusters_refresh(self):
            return False

        async def refresh_address_clusters(self, producer):
            return False

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    assert exc.value.code == 1


def test_sync_main_exits_nonzero_when_another_refresh_holds_the_lock(
    monkeypatch, tmp_path
):
    import runpy
    import sys

    from api.questdb_repository import ConcurrentRefreshError

    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)

    class _Repo:
        async def initialize(self):
            return None

        async def close(self):
            return None

        async def refresh_address_clusters(self, producer):
            raise ConcurrentRefreshError("locked")

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    assert exc.value.code == 1


def test_sync_main_exits_6_when_live_and_old_copies_are_both_gone(
    monkeypatch, tmp_path
):
    import runpy
    import sys

    from api.questdb_repository import AddressClustersLostError

    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)

    class _Repo:
        async def initialize(self):
            return None

        async def close(self):
            return None

        async def refresh_address_clusters(self, producer):
            raise AddressClustersLostError("restore address_clusters ...")

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    assert exc.value.code == 6
