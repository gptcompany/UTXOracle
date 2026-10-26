"""F-419: daily_analysis.main() must leave rows in price_analysis AND metrics.

Runs main() in-process against the QuestDB named by QUESTDB_TEST_* (the CI service
container); skipped, without opening any connection, when they are not set. There is no
default host or port, and the live QuestDB (9900/9912/9909) and the host one (9000) are
refused, so a developer machine is never written to by accident.

Fixtures are SYNTHETIC (declared): bitcoind and mempool.space are replaced by a hand-made
price and a 2-transaction list in the mempool.space shape; no recording of real responses
exists in the repo for this path. The code under test (main, save_to_questdb,
save_metrics_to_db, the ILP sender and the QuestDB itself) is real.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

import pytest

_TARGET_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_ILP_PORT",
    "QUESTDB_TEST_USER",
    "QUESTDB_TEST_PASSWORD",
)
_FORBIDDEN_PORTS = {9000, 9900, 9909, 9912}

SYNTHETIC_TRANSACTIONS = [
    {
        "vin": [{"prevout": {"scriptpubkey_address": "bc1qsynthsender0001"}}],
        "vout": [
            {"scriptpubkey_address": "bc1qsynthreceiver001", "value": 50_000_000},
            {"scriptpubkey_address": "bc1qsynthchange0001", "value": 1_000_000},
        ],
    },
    {
        "vin": [{"prevout": {"scriptpubkey_address": "bc1qsynthsender0002"}}],
        "vout": [{"scriptpubkey_address": "bc1qsynthreceiver002", "value": 10_000_000}],
    },
]


@pytest.fixture(autouse=True)
def _secrets_loader_stub(monkeypatch):
    """daily_analysis imports secrets_loader from a path that exists only on the Dell.

    Stubbed here, scoped to each test, so the result does not depend on test order.
    """
    stub = types.ModuleType("secrets_loader")
    stub.load_secrets = lambda _path=None: False
    monkeypatch.setitem(sys.modules, "secrets_loader", stub)


def _target() -> dict:
    missing = [name for name in _TARGET_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "explicit QuestDB test target required, not set: " + ", ".join(missing)
        )
    target = {
        "host": os.environ["QUESTDB_TEST_HOST"],
        "port": int(os.environ["QUESTDB_TEST_PORT"]),
        "ilp_port": int(os.environ["QUESTDB_TEST_ILP_PORT"]),
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }
    forbidden = {target["port"], target["ilp_port"]} & _FORBIDDEN_PORTS
    assert not forbidden, (
        f"QUESTDB_TEST_* points at a non-test QuestDB port: {forbidden}"
    )
    return target


async def _count(target: dict, table: str) -> int:
    import asyncpg

    conn = await asyncpg.connect(
        host=target["host"],
        port=target["port"],
        user=target["user"],
        password=target["password"],
        database=target["database"],
    )
    try:
        return await conn.fetchval(f"SELECT count() FROM {table}")
    except Exception:  # table not created yet: ILP creates it on first row
        return 0
    finally:
        await conn.close()


async def _wait_for_growth(target: dict, table: str, before: int) -> int:
    """ILP into a WAL table becomes visible asynchronously: poll briefly."""
    after = before
    for _ in range(30):
        after = await _count(target, table)
        if after > before:
            break
        await asyncio.sleep(1)
    return after


def _stub_inputs(monkeypatch, daily) -> None:
    """Replace only bitcoind, mempool.space and the config checks (synthetic, see header)."""
    monkeypatch.setattr(daily, "validate_config", lambda config: None)
    monkeypatch.setattr(daily, "WhaleFlowDetector", None)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", False)
    monkeypatch.setattr(daily, "fetch_mempool_price", lambda url: 100_000.0)
    monkeypatch.setattr(
        daily,
        "calculate_utxoracle_price",
        lambda config: {
            "price_usd": 99_500.0,
            "confidence": 0.9,
            "tx_count": 2,
            "fetch_tier": "synthetic",
            "block_height": 900_000,
            "transactions": SYNTHETIC_TRANSACTIONS,
        },
    )
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py"])


def test_daily_analysis_sends_rows_for_both_tables_without_a_database(monkeypatch):
    """Always runs: the ILP rows main() queues, with no QuestDB involved."""
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    sent: list[tuple[str, dict]] = []

    def record(self, table, symbols, columns, at=None, flush=False):
        sent.append((table, columns))
        return True

    monkeypatch.setattr(repository.QuestDBRepository, "_send_row", record)
    _stub_inputs(monkeypatch, daily)

    daily.main()

    tables = [table for table, _ in sent]
    assert "price_analysis" in tables
    assert "metrics" in tables
    metrics_columns = next(c for t, c in sent if t == "metrics")
    assert metrics_columns["active_addresses_block"] == 5
    assert metrics_columns["tx_count"] == 2


def test_daily_analysis_writes_price_analysis_and_metrics(monkeypatch, tmp_path):
    target = _target()
    try:
        before = {
            t: asyncio.run(_count(target, t)) for t in ("price_analysis", "metrics")
        }
    except OSError:
        pytest.skip("QuestDB test target not reachable")

    import api.questdb_repository as repository
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    # Point both ILP writers (price_analysis via a new repository, metrics via the module
    # singleton) at the test target.
    monkeypatch.setattr(repository, "QUESTDB_ILP_HOST", target["host"])
    monkeypatch.setattr(repository, "QUESTDB_ILP_PORT", target["ilp_port"])
    monkeypatch.setattr(metrics._repo, "ilp_host", target["host"])
    monkeypatch.setattr(metrics._repo, "ilp_port", target["ilp_port"])

    _stub_inputs(monkeypatch, daily)

    daily.main()

    for table in ("price_analysis", "metrics"):
        after = asyncio.run(_wait_for_growth(target, table, before[table]))
        assert after > before[table], f"{table}: no new row after daily_analysis"
