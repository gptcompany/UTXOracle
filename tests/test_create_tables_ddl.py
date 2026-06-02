"""DDL coverage test (spec-061 US2 T022a).

Asserts that create_tables_if_not_exist registers every table the
public contract surface depends on: the 11 contractual streams that
predate spec-061 PLUS the 2 new tables added by T022 (realized_cap_daily
and backtest_whale_signals).

Runs against a live QuestDB on localhost:8812 - skipped if unreachable.
"""

from __future__ import annotations

import asyncio
import os

import pytest


pytestmark = pytest.mark.asyncio

EXPECTED_TABLES = {
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


async def _questdb_reachable() -> bool:
    try:
        import asyncpg

        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=os.getenv("QUESTDB_PG_HOST", "localhost"),
                port=int(os.getenv("QUESTDB_PG_PORT", 8812)),
                user=os.getenv("QUESTDB_PG_USER", "admin"),
                password=os.getenv("QUESTDB_PG_PASSWORD", "quest"),
                database=os.getenv("QUESTDB_PG_DATABASE", "main"),
            ),
            timeout=3,
        )
        await conn.close()
        return True
    except Exception:
        return False


async def test_required_tables_exist():
    """T022a: every contract-required table must be created by `create_tables_if_not_exist`."""
    if not await _questdb_reachable():
        pytest.skip("QuestDB not reachable on :8812")

    import asyncpg

    from api.questdb_repository import create_tables_if_not_exist

    await create_tables_if_not_exist()

    conn = await asyncpg.connect(
        host=os.getenv("QUESTDB_PG_HOST", "localhost"),
        port=int(os.getenv("QUESTDB_PG_PORT", 8812)),
        user=os.getenv("QUESTDB_PG_USER", "admin"),
        password=os.getenv("QUESTDB_PG_PASSWORD", "quest"),
        database=os.getenv("QUESTDB_PG_DATABASE", "main"),
    )
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


async def test_daily_aggregate_tables_are_deduplicated():
    """T022/T023b: daily aggregate target tables must deduplicate by ts."""
    if not await _questdb_reachable():
        pytest.skip("QuestDB not reachable on :8812")

    import asyncpg

    from api.questdb_repository import create_tables_if_not_exist

    await create_tables_if_not_exist()

    conn = await asyncpg.connect(
        host=os.getenv("QUESTDB_PG_HOST", "localhost"),
        port=int(os.getenv("QUESTDB_PG_PORT", 8812)),
        user=os.getenv("QUESTDB_PG_USER", "admin"),
        password=os.getenv("QUESTDB_PG_PASSWORD", "quest"),
        database=os.getenv("QUESTDB_PG_DATABASE", "main"),
    )
    try:
        rows = await conn.fetch(
            """
            SELECT table_name, walEnabled, dedup
            FROM tables()
            WHERE table_name IN (
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
        "mvrv_daily",
        "nupl_daily",
        "realized_cap_daily",
        "backtest_whale_signals",
    ):
        assert by_name[table_name]["walEnabled"] is True
        assert by_name[table_name]["dedup"] is True
