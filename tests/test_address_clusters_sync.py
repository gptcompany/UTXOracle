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


def _restart_with_a_broken_recovery(monkeypatch, tmp_path, *, observation_fails):
    """Runs the real sync main with a repository that cannot restore (or observe) at
    restart; returns the exit code. Only the database access is faked."""
    import runpy
    import sys

    import api.questdb_repository as qr

    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)
    old = "address_clusters_old_20260101T000000Z"

    class _Conn:
        async def execute(self, query, *args):
            raise RuntimeError("cannot rename")

        async def close(self):
            return None

    class _Repo(qr.QuestDBRepository):
        async def initialize(self):
            return None

        async def close(self):
            return None

        async def fetch(self, query, *args):
            if observation_fails:
                raise ConnectionError("pool down")
            if "LIKE" in query:
                return [(old,)]
            return []  # the live table is absent

        async def _open_dedicated_connection(self):
            return _Conn()

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    return exc.value.code


@pytest.mark.parametrize("observation_fails", [False, True])
def test_sync_main_exits_6_with_the_manual_command_when_the_restart_recovery_fails(
    monkeypatch, tmp_path, capsys, observation_fails
):
    code = _restart_with_a_broken_recovery(
        monkeypatch, tmp_path, observation_fails=observation_fails
    )

    assert code == 6
    assert "sync_clusters_to_questdb" in capsys.readouterr().err


class _CatalogConn:
    """DDL connection over a fake catalog {table: data}; the RENAME of the staging table
    can lose its acknowledgement (applied, then raised)."""

    def __init__(self, catalog, ack_lost=False, close_fails=False):
        self.catalog, self.ack_lost, self.close_fails = catalog, ack_lost, close_fails
        self.executed: list[str] = []
        self.renames_done = 0

    async def execute(self, query, *args):
        import re

        q = " ".join(query.split())
        self.executed.append(q)
        m = re.fullmatch(r"RENAME TABLE (\S+) TO (\S+)", q)
        if m:
            src, dst = m.groups()
            if src not in self.catalog:
                raise RuntimeError(f"table does not exist [table={src}]")
            self.catalog[dst] = self.catalog.pop(src)
            self.renames_done += 1
            if self.ack_lost and src == "address_clusters_staging":
                raise ConnectionError("connection lost before the acknowledgement")
        elif q.startswith("CREATE TABLE IF NOT EXISTS address_clusters_staging"):
            self.catalog.setdefault("address_clusters_staging", "empty")

    async def close(self):
        if self.close_fails and self.renames_done >= 2:
            raise RuntimeError("close boom")  # after the swap, as the r6 case


def _run_sync_main_with_a_failing_catalog_read(
    monkeypatch, tmp_path, scenario, close_fails=False
):
    """The real sync main over a fake database whose tables() listing fails at one point
    of the refresh; returns (exit code, catalog, DDL connection)."""
    import re
    import runpy
    import sys

    import api.questdb_repository as qr

    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)
    catalog = {"address_clusters": "old data", "address_clusters_staging": "new data"}
    conn = _CatalogConn(
        catalog, ack_lost=scenario == "post_reconcile_staging", close_fails=close_fails
    )

    failed_once: list[bool] = []

    def tables_read_fails(query):
        if scenario == "pre_swap_catalog":  # after prepare, before any RENAME
            return any("TRUNCATE" in q for q in conn.executed) and not conn.renames_done
        if scenario == "post_reconcile_staging":  # the check of the staging table
            return "address_clusters_staging" in query
        # post_swap_old_listing: the first read after the swap fails, then recovers
        if conn.renames_done >= 2 and not failed_once:
            failed_once.append(True)
            return True
        return False

    class _Repo(qr.QuestDBRepository):
        async def initialize(self):
            return None

        async def close(self):
            return None

        def stage_address_cluster(self, row, **kwargs):
            return True

        async def fetch(self, query, *args):
            if "FROM tables()" in query:
                if tables_read_fails(query):
                    raise ConnectionError("pool down")
                exact = re.search(r"table_name = '(\w+)'", query)
                like = re.search(r"LIKE '(\w+)%'", query)
                if exact:
                    return [(exact.group(1),)] if exact.group(1) in catalog else []
                return [(n,) for n in sorted(catalog) if n.startswith(like.group(1))]
            if "wal_tables" in query:
                return [
                    {
                        "suspended": False,
                        "writerTxn": 1,
                        "sequencerTxn": 1,
                        "errorTag": "",
                        "errorMessage": "",
                    }
                ]
            if "table_columns" in query:
                return list(qr.ADDRESS_CLUSTERS_SCHEMA)
            raise AssertionError(query)

        async def fetchrow(self, query, *args):
            return (1,)

        async def _open_dedicated_connection(self):
            return conn

    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", _Repo)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    return exc.value.code, catalog, conn


@pytest.mark.parametrize(
    "scenario", ["pre_swap_catalog", "post_reconcile_staging", "post_swap_old_listing"]
)
def test_a_failed_catalog_read_anywhere_in_the_refresh_is_exit_6_and_keeps_the_data(
    monkeypatch, tmp_path, capsys, scenario
):
    code, catalog, conn = _run_sync_main_with_a_failing_catalog_read(
        monkeypatch, tmp_path, scenario
    )

    assert code == 6
    assert "sync_clusters_to_questdb" in capsys.readouterr().err  # the manual command
    if scenario == "pre_swap_catalog":
        assert catalog["address_clusters"] == "old data"  # nothing swapped
        assert catalog["address_clusters_staging"] == "new data"  # verified, kept
        assert conn.renames_done == 0
    else:
        assert catalog["address_clusters"] == "new data"  # published
        olds = [n for n in catalog if n.startswith("address_clusters_old_")]
        assert [catalog[n] for n in olds] == ["old data"]  # recoverable copy kept


def test_a_failing_close_never_replaces_the_primary_error_and_the_lock_is_released(
    monkeypatch, tmp_path, capsys, caplog
):
    """r6: the old listing fails after the swap AND closing the DDL connection fails."""
    import api.questdb_repository as qr

    with caplog.at_level("ERROR"):
        code, catalog, conn = _run_sync_main_with_a_failing_catalog_read(
            monkeypatch, tmp_path, "post_swap_old_listing", close_fails=True
        )

    assert code == 6
    assert "sync_clusters_to_questdb" in capsys.readouterr().err
    assert any("close boom" in r.getMessage() for r in caplog.records)  # logged
    assert catalog["address_clusters"] == "new data"  # B is live
    olds = [n for n in catalog if n.startswith("address_clusters_old_")]
    assert [catalog[n] for n in olds] == ["old data"]  # A kept as the rollback
    qr.RefreshLock.acquire().release()  # the lock was released


# --- r7: the exit classification survives every cleanup, for the CLI and the bootstraps


class _SyncRepo:
    """Stub QuestDBRepository for run_sync: refresh raises/returns what the test wants and
    close() can fail. Shared by the CLI and the two bootstrap callers."""

    events: list[str] = []
    refresh_raises: BaseException | None = None
    refresh_result = True
    close_fails = False

    async def initialize(self):
        self.events.append("initialized")

    async def refresh_address_clusters(self, producer):
        if self.refresh_raises is not None:
            raise self.refresh_raises
        return self.refresh_result

    async def close(self):
        self.events.append("repo_close")
        if self.close_fails:
            raise ConnectionError("repo close boom")


def _stub_sync_environment(
    monkeypatch, tmp_path, *, duck_close_fails=False, duck_close_error=None, **repo
):
    """Patch the repository (both import paths) and DuckDB's read-only connection."""
    import duckdb as _duckdb

    events: list[str] = []
    attrs = {
        "events": events,
        "refresh_raises": None,
        "refresh_result": True,
        "close_fails": False,
    }
    attrs.update(repo)
    stub = type("Repo", (_SyncRepo,), attrs)
    monkeypatch.setattr("api.questdb_repository.QuestDBRepository", stub)
    # the bootstraps import the already-loaded sync module: patch its bound name too
    monkeypatch.setattr(
        "scripts.bootstrap.sync_clusters_to_questdb.QuestDBRepository", stub
    )
    real_connect = _duckdb.connect

    class _Proxy:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def close(self):
            events.append("duckdb_close")
            self._conn.close()
            if duck_close_fails:
                raise duck_close_error or ConnectionError("duckdb close boom")

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        return _Proxy(conn) if kwargs.get("read_only") else conn

    monkeypatch.setattr(_duckdb, "connect", connect)
    return events, stub


def _lost(
    message="run `RENAME TABLE x TO y`, or rebuild it with `uv run python -m scripts.bootstrap.sync_clusters_to_questdb`",
):
    from api.questdb_repository import AddressClustersLostError

    return AddressClustersLostError(message)


def _run_cli(monkeypatch, tmp_path, *, db_exists=True, **kwargs):
    import runpy
    import sys

    events, stub = _stub_sync_environment(monkeypatch, tmp_path, **kwargs)
    db = tmp_path / "x.duckdb"
    if db_exists:
        _db_with_one_cluster(db)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )
    return exc.value.code, events


def test_cli_lost_error_survives_a_failing_duckdb_close_and_the_repo_is_still_closed(
    monkeypatch, tmp_path, caplog
):
    with caplog.at_level("ERROR"):
        code, events = _run_cli(
            monkeypatch, tmp_path, duck_close_fails=True, refresh_raises=_lost()
        )

    assert code == 6
    assert "repo_close" in events  # the second closer still ran
    log = " ".join(r.getMessage() for r in caplog.records)
    assert "duckdb close boom" in log and "RENAME TABLE x TO y" in log


def test_cli_both_closes_failing_never_lowers_exit_6(monkeypatch, tmp_path, caplog):
    with caplog.at_level("ERROR"):
        code, _ = _run_cli(
            monkeypatch,
            tmp_path,
            duck_close_fails=True,
            close_fails=True,
            refresh_raises=_lost(),
        )

    assert code == 6
    log = " ".join(r.getMessage() for r in caplog.records)
    assert "duckdb close boom" in log and "repo close boom" in log


def test_cli_a_failing_close_turns_a_success_into_exit_1(monkeypatch, tmp_path):
    code, events = _run_cli(monkeypatch, tmp_path, close_fails=True)

    assert code == 1
    assert "duckdb_close" in events and "repo_close" in events


def test_cli_missing_duckdb_is_exit_1_with_the_repository_closed(monkeypatch, tmp_path):
    code, events = _run_cli(monkeypatch, tmp_path, db_exists=False)

    assert code == 1
    assert "repo_close" in events


def test_cli_an_unclassified_error_is_logged_and_exit_1(monkeypatch, tmp_path, caplog):
    with caplog.at_level("ERROR"):
        code, events = _run_cli(
            monkeypatch, tmp_path, refresh_raises=RuntimeError("unexpected")
        )

    assert code == 1
    assert "repo_close" in events
    assert any(r.exc_info for r in caplog.records)  # logger.exception, not a bare raise


def _bootstrap_run(monkeypatch, tmp_path, which, capsys):
    """Run the real main() of one of the two bootstraps with the heavy work patched out;
    returns its return value. Only the optional QuestDB sync is real."""
    import importlib
    import sys

    db = tmp_path / "utxo.duckdb"
    _db_with_one_cluster(db)
    if which == "run_combined_bootstrap":
        module = importlib.import_module("scripts.bootstrap.run_combined_bootstrap")
        stats = {
            "start_block": 0,
            "end_block": 1,
            "blocks_processed": 1,
            "txs_clustered": 1,
            "addresses_clustered": 1,
            "clusters_created": 1,
            "utxos_spent": 1,
            "duration_seconds": 1.0,
        }
        monkeypatch.setattr(module, "run_combined_bootstrap", lambda **kwargs: stats)
        argv = [
            "x", "--sync-questdb", "--start-block", "0", "--end-block", "1",
            "--utxo-db-path", str(db),
        ]  # fmt: skip
    else:
        module = importlib.import_module(
            "scripts.bootstrap.complete_clustering_v3_fast"
        )
        out = tmp_path / "pairs"
        out.mkdir()
        (out / "pairs_0.csv.gz").write_bytes(b"x")

        class _UF:
            def memory_usage_gb(self):
                return 0.0

        monkeypatch.setattr(module, "CYTHON_AVAILABLE", True, raising=False)
        monkeypatch.setattr(module, "OUTPUT_DIR", out)
        monkeypatch.setattr(module, "UTXO_DB_PATH", db)
        monkeypatch.setattr(module, "build_address_mapping_fast", lambda *a, **k: {})
        monkeypatch.setattr(module, "run_cython_clustering", lambda *a, **k: _UF())
        monkeypatch.setattr(module, "save_clusters_bulk", lambda *a, **k: 0)
        monkeypatch.setattr(module, "count_clusters", lambda *a, **k: 0)
        argv = ["x", "--sync-questdb"]
    monkeypatch.setattr(sys, "argv", argv)
    return module.main()


BOOTSTRAPS = ["run_combined_bootstrap", "complete_clustering_v3_fast"]


@pytest.mark.parametrize("which", BOOTSTRAPS)
def test_bootstrap_lost_error_is_exit_6_after_the_summary(
    monkeypatch, tmp_path, capsys, caplog, which
):
    _stub_sync_environment(monkeypatch, tmp_path, refresh_raises=_lost())

    with caplog.at_level("ERROR"):
        code = _bootstrap_run(monkeypatch, tmp_path, which, capsys)

    out = capsys.readouterr().out
    assert code == 6
    assert "COMPLETE" in out  # the summary was printed first
    assert any("RENAME TABLE x TO y" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("which", BOOTSTRAPS)
def test_bootstrap_lost_error_plus_failing_close_keeps_exit_6_and_the_command(
    monkeypatch, tmp_path, capsys, caplog, which
):
    _stub_sync_environment(
        monkeypatch, tmp_path, duck_close_fails=True, refresh_raises=_lost()
    )

    with caplog.at_level("ERROR"):
        code = _bootstrap_run(monkeypatch, tmp_path, which, capsys)

    assert code == 6
    log = " ".join(r.getMessage() for r in caplog.records)
    assert "RENAME TABLE x TO y" in log and "duckdb close boom" in log


@pytest.mark.parametrize("which", BOOTSTRAPS)
def test_bootstrap_unclassified_sync_error_is_a_warning_and_exit_0(
    monkeypatch, tmp_path, capsys, which
):
    _stub_sync_environment(monkeypatch, tmp_path, refresh_raises=RuntimeError("boom"))

    code = _bootstrap_run(monkeypatch, tmp_path, which, capsys)

    out = capsys.readouterr().out
    assert code in (0, None) and not code
    assert "DuckDB analytical plane remains the source of truth" in out


@pytest.mark.parametrize("which", BOOTSTRAPS)
def test_bootstrap_successful_sync_prints_the_success_message_and_exit_0(
    monkeypatch, tmp_path, capsys, which
):
    _stub_sync_environment(monkeypatch, tmp_path)

    code = _bootstrap_run(monkeypatch, tmp_path, which, capsys)

    assert not code
    assert "QuestDB sync completed successfully" in capsys.readouterr().out


def test_cli_cancelled_error_from_a_close_never_replaces_lost(
    monkeypatch, tmp_path, caplog
):
    import asyncio

    with caplog.at_level("ERROR"):
        code, events = _run_cli(
            monkeypatch,
            tmp_path,
            duck_close_fails=True,
            duck_close_error=asyncio.CancelledError("duckdb close cancelled"),
            refresh_raises=_lost(),
        )

    assert code == 6
    assert "repo_close" in events


def test_cli_a_cancelled_error_without_lost_is_raised_after_the_closes(
    monkeypatch, tmp_path
):
    import asyncio
    import runpy
    import sys

    events, _ = _stub_sync_environment(
        monkeypatch, tmp_path, refresh_raises=asyncio.CancelledError("cancelled")
    )
    db = tmp_path / "x.duckdb"
    _db_with_one_cluster(db)
    monkeypatch.setattr("api.config.DUCKDB_PATH", str(db))
    monkeypatch.setattr(sys, "argv", ["sync"])

    with pytest.raises(asyncio.CancelledError):
        runpy.run_path(
            "scripts/bootstrap/sync_clusters_to_questdb.py", run_name="__main__"
        )

    assert (
        "duckdb_close" in events and "repo_close" in events
    )  # closed BEFORE re-raising
