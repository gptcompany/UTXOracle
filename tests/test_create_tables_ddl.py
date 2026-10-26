"""DDL coverage test (spec-061 US2 T022a).

Asserts that create_tables_if_not_exist registers every table the
public contract surface depends on: the 11 contractual streams that
predate spec-061 PLUS the 2 new tables added by T022 (realized_cap_daily
and backtest_whale_signals).

Runs against the QuestDB named by QUESTDB_TEST_HOST/PORT/USER/PASSWORD (CI service
container); skipped, without opening any connection, when they are not set.
"""

from __future__ import annotations

import asyncio
import os

import pytest


pytestmark = pytest.mark.asyncio

SOURCE_FRESHNESS_DDLS = (
    """
    CREATE TABLE IF NOT EXISTS block_heights (
        height LONG,
        ts TIMESTAMP,
        fetched_at TIMESTAMP
    ) timestamp(ts) PARTITION BY YEAR WAL
      DEDUP UPSERT KEYS(ts, height);
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_prices (
        date TIMESTAMP,
        price_usd DOUBLE,
        source SYMBOL,
        fetched_at TIMESTAMP
    ) timestamp(date) PARTITION BY YEAR WAL
      DEDUP UPSERT KEYS(date);
    """,
)

EXPECTED_TABLES = {
    "block_heights",
    "daily_prices",
    "live_snapshots",
    "entity_flows_daily",
    "whale_transactions",
    "mempool_predictions",
    "net_flow_metrics",
    "backtest_whale_signals",  # NEW per T022
    "price_analysis",
    "urpd_features_daily",
    "utxo_lifecycle",  # backing table for utxo_lifecycle_full
    "utxo_snapshots",
    "mvrv_daily",
    "nupl_daily",
    "realized_cap_daily",  # NEW per T022
}


_TARGET_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_USER",
    "QUESTDB_TEST_PASSWORD",
)


def _questdb_target() -> dict:
    """Explicit QuestDB test target; no default host/port/user, so a dev host is never hit by accident.

    These tests run the production DDL (CREATE TABLE IF NOT EXISTS), so they must only
    ever target a database somebody named on purpose (the CI service container).
    """
    missing = [name for name in _TARGET_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "explicit QuestDB test target required, not set: " + ", ".join(missing)
        )
    return {
        "host": os.environ["QUESTDB_TEST_HOST"],
        "port": int(os.environ["QUESTDB_TEST_PORT"]),
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }


async def _questdb_reachable(target: dict) -> bool:
    try:
        import asyncpg

        conn = await asyncio.wait_for(asyncpg.connect(**target), timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


async def _connect_questdb(target: dict):
    import asyncpg

    return await asyncpg.connect(**target)


async def _create_tables(target: dict, monkeypatch) -> None:
    """Run the production DDL against the explicit target.

    The fresh QuestDB of the CI gate has no tables until it runs. The production module reads
    its own connection settings, so they are pointed at the same target for this call.
    """
    import api.questdb_repository as repository

    for name, key in (
        ("QUESTDB_PG_HOST", "host"),
        ("QUESTDB_PG_PORT", "port"),
        ("QUESTDB_PG_USER", "user"),
        ("QUESTDB_PG_PASSWORD", "password"),
        ("QUESTDB_PG_DATABASE", "database"),
    ):
        monkeypatch.setattr(repository, name, target[key])
    await repository.create_tables_if_not_exist()


async def _ensure_source_freshness_tables(conn) -> None:
    for ddl in SOURCE_FRESHNESS_DDLS:
        await conn.execute(ddl)


async def test_required_tables_exist(monkeypatch):
    """T022a: every contract-required table must be created by `create_tables_if_not_exist`."""
    target = _questdb_target()
    if not await _questdb_reachable(target):
        pytest.skip("QuestDB test target not reachable")

    await _create_tables(target, monkeypatch)

    conn = await _connect_questdb(target)
    try:
        rows = await conn.fetch("SHOW TABLES")
    finally:
        await conn.close()

    present = {r["table_name"] for r in rows}
    missing = EXPECTED_TABLES - present
    assert not missing, (
        f"create_tables_if_not_exist did not register: {sorted(missing)}. "
        f"Present tables include: {sorted(t for t in present if t in EXPECTED_TABLES)}"
    )


async def test_daily_aggregate_tables_are_deduplicated(monkeypatch):
    """T022/T023b: daily aggregate target tables must deduplicate by ts."""
    target = _questdb_target()
    if not await _questdb_reachable(target):
        pytest.skip("QuestDB test target not reachable")

    await _create_tables(target, monkeypatch)

    conn = await _connect_questdb(target)
    try:
        rows = await conn.fetch(
            """
            SELECT table_name, walEnabled, dedup
            FROM tables()
            WHERE table_name IN (
                'block_heights',
                'daily_prices',
                'mvrv_daily',
                'nupl_daily',
                'realized_cap_daily',
                'backtest_whale_signals'
            )
            """
        )
    finally:
        await conn.close()

    by_name = {r["table_name"]: r for r in rows}
    for table_name in (
        "block_heights",
        "daily_prices",
        "mvrv_daily",
        "nupl_daily",
        "realized_cap_daily",
        "backtest_whale_signals",
    ):
        assert by_name[table_name]["walEnabled"] is True
        assert by_name[table_name]["dedup"] is True


async def test_source_freshness_tables_are_deduplicated():
    """Phase 1.5-v2: QuestDB reference tables must be WAL + DEDUP."""
    target = _questdb_target()
    if not await _questdb_reachable(target):
        pytest.skip("QuestDB test target not reachable")

    conn = await _connect_questdb(target)
    try:
        await _ensure_source_freshness_tables(conn)
        rows = await conn.fetch(
            """
            SELECT table_name, walEnabled, dedup
            FROM tables()
            WHERE table_name IN ('block_heights', 'daily_prices')
            """
        )
    finally:
        await conn.close()

    by_name = {r["table_name"]: r for r in rows}
    assert set(by_name) == {"block_heights", "daily_prices"}
    assert by_name["block_heights"]["walEnabled"] is True
    assert by_name["block_heights"]["dedup"] is True
    assert by_name["daily_prices"]["walEnabled"] is True
    assert by_name["daily_prices"]["dedup"] is True


@pytest.mark.parametrize(
    "test",
    [
        test_required_tables_exist,
        test_daily_aggregate_tables_are_deduplicated,
        test_source_freshness_tables_are_deduplicated,
    ],
)
async def test_no_connection_without_an_explicit_target(monkeypatch, test):
    """F-403: without an explicit target nothing may connect (the DDL tests write)."""
    import asyncpg

    for name in (*_TARGET_ENV, "QUESTDB_TEST_DATABASE"):
        monkeypatch.delenv(name, raising=False)

    async def forbidden(*args, **kwargs):
        raise AssertionError("a connection was attempted without an explicit target")

    monkeypatch.setattr(asyncpg, "connect", forbidden)
    monkeypatch.setattr(asyncpg, "create_pool", forbidden)

    parameters = test.__code__.co_varnames[: test.__code__.co_argcount]
    with pytest.raises(pytest.skip.Exception, match="explicit QuestDB test target"):
        await (test(monkeypatch) if parameters else test())
