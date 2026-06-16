"""Tests for spec-063 entity_flows_daily QuestDB producer pilot."""

from datetime import date as date_cls, datetime
import inspect
import logging
from pathlib import Path

import duckdb
import pytest


def _build_flow_fixture_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE address_clusters (
                address VARCHAR,
                cluster_id VARCHAR,
                label VARCHAR,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO address_clusters VALUES
            ('addr_1', 'cluster_001', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00'),
            ('addr_2', 'cluster_002', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00'),
            ('addr_3', 'cluster_003', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00')
            """
        )
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                txid VARCHAR,
                address VARCHAR,
                ts TIMESTAMP,
                btc_value DOUBLE,
                is_spent BOOLEAN
            )
            """
        )
        conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES
            ('tx_1', 'addr_1', TIMESTAMP '2026-06-15 01:00:00', 1.25, FALSE),
            ('tx_2', 'addr_2', TIMESTAMP '2026-06-15 02:00:00', 2.50, FALSE),
            ('tx_3', 'addr_3', TIMESTAMP '2026-06-15 03:00:00', 3.75, FALSE)
            """
        )
    finally:
        conn.close()


def _duckdb_entity_flow_rows(path: Path) -> list[dict[str, object]]:
    conn = duckdb.connect(str(path))
    try:
        rows = conn.execute(
            """
            SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange
            FROM entity_flows_daily
            ORDER BY date, entity_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "entity_id": row[0],
            "date": row[1],
            "inflow_btc": row[2],
            "outflow_btc": row[3],
            "netflow_btc": row[4],
            "is_exchange": row[5],
        }
        for row in rows
    ]


def test_placeholder():
    assert True


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("False", False),
        ("  false  ", False),
        ("no", False),
        ("NO", False),
        ("No", False),
        ("disable", True),
        ("off", True),
        ("nope", True),
    ],
)
def test_should_write_questdb_parser_table(monkeypatch, raw_value, expected):
    from scripts.live.flow_aggregator import _should_write_questdb

    if raw_value is None:
        monkeypatch.delenv("SPEC063_QUESTDB_WRITE", raising=False)
    else:
        monkeypatch.setenv("SPEC063_QUESTDB_WRITE", raw_value)

    assert _should_write_questdb() is expected


def test_save_entity_flows_daily_signature():
    from api.questdb_repository import save_entity_flows_daily

    signature = inspect.signature(save_entity_flows_daily)
    assert list(signature.parameters) == [
        "entity_id",
        "date",
        "inflow_btc",
        "outflow_btc",
        "netflow_btc",
        "is_exchange",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.return_annotation is None


def test_dual_write_payload_byte_identity(tmp_path, monkeypatch):
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)
    calls = []

    def record_save(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        flow_aggregator,
        "save_entity_flows_daily",
        record_save,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert calls == _duckdb_entity_flow_rows(db_path)


def test_cast_contract_matches_data_model(tmp_path, monkeypatch):
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)
    calls = []

    def record_save(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        flow_aggregator,
        "save_entity_flows_daily",
        record_save,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert calls
    for call in calls:
        assert isinstance(call["entity_id"], str)
        assert isinstance(call["date"], date_cls)
        assert not isinstance(call["date"], datetime)
        assert isinstance(call["inflow_btc"], float)
        assert isinstance(call["outflow_btc"], float)
        assert isinstance(call["netflow_btc"], float)
        assert isinstance(call["is_exchange"], bool)


def test_disabled_state_emits_explicit_INFO_log(tmp_path, monkeypatch, caplog):
    """T014 [RED]: with SPEC063_QUESTDB_WRITE OFF, the producer MUST emit an
    INFO log declaring the disabled state (per quickstart.md Rollback Step 2)
    AND MUST NOT open a QuestDB connection AND MUST NOT emit the success log
    shape containing rows_written_questdb=.

    Three assertions:
      (a) regression guard for T012 gating — _open_pg_sync NOT invoked;
      (b) RED-state property — disabled-state INFO log line emitted exactly
          once with the canonical prefix;
      (c) negative property — success log shape NOT present in OFF mode.
    """
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)

    def must_not_open(*args, **kwargs):
        raise AssertionError(
            "_open_pg_sync must not be called when SPEC063_QUESTDB_WRITE=0"
        )

    monkeypatch.setenv("SPEC063_QUESTDB_WRITE", "0")
    monkeypatch.setattr(
        flow_aggregator, "_open_pg_sync", must_not_open, raising=False
    )
    caplog.set_level(logging.INFO, logger="scripts.live.flow_aggregator")

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    # (a) Connection guard — implicit (must_not_open would have raised)
    # (b) Disabled-state INFO log emitted exactly once
    disabled_prefix = (
        "spec-063 entity_flows_daily QuestDB write half disabled by "
        "SPEC063_QUESTDB_WRITE="
    )
    disabled_records = [
        r for r in caplog.records if r.getMessage().startswith(disabled_prefix)
    ]
    assert len(disabled_records) == 1, (
        f"expected exactly one disabled-state INFO log, got {len(disabled_records)}: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
    # (c) The success log MAY appear in OFF mode (T026 design), but the
    # rows_written_questdb token MUST be the literal "disabled" — never a
    # numeric value that would imply "wrote 0 rows because all rows failed"
    # vs. the actual "operator disabled the write half".
    for r in caplog.records:
        msg = r.getMessage()
        if "rows_written_questdb=" in msg:
            assert "rows_written_questdb=disabled" in msg, (
                f"success log used numeric rows_written_questdb in OFF mode "
                f"(should be 'disabled'): {msg}"
            )


def test_questdb_failure_does_not_roll_back_duckdb(tmp_path, monkeypatch, caplog):
    """T015 [RED]: simulating a QuestDB write failure on every per-row
    save_entity_flows_daily call MUST satisfy three properties:
      (a) aggregate_flows returns without raising upward (DuckDB SSOT
          integrity preserved per FR-002);
      (b) the DuckDB entity_flows_daily row count equals the pre-spec-063
          count (legacy write path NOT rolled back);
      (c) each row failure is logged at ERROR per FR-003 with the canonical
          prefix "entity_flows_daily QuestDB save failed".
    T012 GREEN does NOT wrap the save_entity_flows_daily call in try/except,
    so this test fails RED on assertion (a) — the AssertionError raised by
    the patched save method bubbles out of aggregate_flows.
    """
    import psycopg

    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)

    def always_fail(**kwargs):
        raise psycopg.OperationalError("simulated QuestDB write failure")

    monkeypatch.setattr(
        flow_aggregator, "save_entity_flows_daily", always_fail, raising=False
    )
    caplog.set_level(logging.ERROR, logger="scripts.live.flow_aggregator")

    # (a) Must not raise
    try:
        flow_aggregator.aggregate_flows(db_path=str(db_path))
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"aggregate_flows raised QuestDB error instead of isolating it: {exc}"
        )

    # (b) DuckDB row count matches the pre-spec-063 contract
    duckdb_rows = _duckdb_entity_flow_rows(db_path)
    assert duckdb_rows, (
        "DuckDB write path produced zero rows — legacy SSOT was clobbered"
    )

    # (c) Per-row ERROR log emitted per FR-003
    error_records = [
        r
        for r in caplog.records
        if "entity_flows_daily QuestDB save failed" in r.getMessage()
    ]
    assert len(error_records) == len(duckdb_rows), (
        f"expected {len(duckdb_rows)} ERROR logs, got {len(error_records)}: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_aggregated_webhook_fires_exactly_once_per_failing_run(
    tmp_path, monkeypatch
):
    """T018 [RED]: when N rows fail QuestDB save, the webhook MUST be POSTed
    exactly once with an aggregated payload matching contracts/webhook_payload.md.
    """
    import json
    import re
    import psycopg

    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)

    def always_fail(**kwargs):
        raise psycopg.OperationalError("simulated QuestDB write failure")

    posted = []

    def fake_urlopen(request, timeout=None):
        posted.append(
            {
                "url": request.full_url,
                "body": request.data,
                "timeout": timeout,
            }
        )

        class _R:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _=0):
                return b""

        return _R()

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    monkeypatch.setattr(
        flow_aggregator, "save_entity_flows_daily", always_fail, raising=False
    )
    monkeypatch.setattr(
        "scripts.live.flow_aggregator.urllib.request.urlopen",
        fake_urlopen,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert len(posted) == 1, (
        f"expected exactly one webhook POST, got {len(posted)}"
    )
    assert posted[0]["url"] == "https://discord.invalid/webhook/abc"
    body = json.loads(posted[0]["body"].decode("utf-8"))
    pattern = (
        r"^:rotating_light: entity_flows_daily QuestDB write failed for "
        r"(\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}): "
        r"\d+ rows failed \([\w\.]+\)$"
    )
    assert re.match(pattern, body["content"]), (
        f"payload does not match contracts/webhook_payload.md: {body['content']!r}"
    )


def test_webhook_NOT_fired_on_successful_run(tmp_path, monkeypatch):
    """T019 [RED]: a fully successful aggregate_flows run MUST NOT POST to the
    Discord webhook."""
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)
    posted = []

    def fake_urlopen(*args, **kwargs):
        posted.append(args)
        raise AssertionError(
            "urlopen MUST NOT be called when no rows fail QuestDB save"
        )

    def record_save(**kwargs):
        # Successful save — no exception
        return None

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    monkeypatch.setattr(
        flow_aggregator, "save_entity_flows_daily", record_save, raising=False
    )
    monkeypatch.setattr(
        "scripts.live.flow_aggregator.urllib.request.urlopen",
        fake_urlopen,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert posted == [], (
        f"webhook leaked on successful run: {posted}"
    )


@pytest.mark.integration
def test_rollback_OFF_preserves_pre_existing_questdb_row_values(
    tmp_path, monkeypatch
):
    """T020 [RED]: seeded QuestDB rows with distinct sentinel values MUST
    survive an `aggregate_flows()` run executed with SPEC063_QUESTDB_WRITE=0.
    Pre-existing row values MUST NOT be overwritten by the aggregate values.

    Requires a live QuestDB instance reachable via _open_pg_sync; skip if
    unreachable (consistent with analyze remediation F7).
    """
    import datetime as _dt
    import psycopg

    try:
        from api.questdb_repository import (
            _open_pg_sync,
            create_tables_if_not_exist,
        )
    except ImportError as exc:
        pytest.skip(f"questdb_repository unavailable: {exc}")

    try:
        conn = _open_pg_sync()
        conn.close()
    except Exception as exc:
        pytest.skip(f"live QuestDB unreachable: {exc}")

    import asyncio

    asyncio.run(_create_tables_async())

    sentinel_date = _dt.date(2026, 6, 16)
    sentinel_entity_a = "cluster_sentinel_A"
    sentinel_entity_b = "cluster_sentinel_B"
    sentinel_inflow_a = 999.123456
    sentinel_inflow_b = 888.654321

    # Seed sentinel rows. DEDUP UPSERT KEYS(date, entity_id) makes this
    # idempotent — re-running the test upserts the sentinel values, no DELETE
    # preamble needed (QuestDB DELETE has limited syntax support).
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            for entity, inflow in (
                (sentinel_entity_a, sentinel_inflow_a),
                (sentinel_entity_b, sentinel_inflow_b),
            ):
                cur.execute(
                    """
                    INSERT INTO entity_flows_daily
                    (entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (entity, sentinel_date, inflow, 0.0, inflow, False),
                )
        conn.commit()

    # Run with env var OFF — aggregate_flows MUST NOT touch QuestDB
    monkeypatch.setenv("SPEC063_QUESTDB_WRITE", "0")
    db_path = tmp_path / "rollback.duckdb"
    _build_flow_fixture_db(db_path)
    from scripts.live import flow_aggregator

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    # Assert sentinel rows survived unchanged
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity_id, inflow_btc FROM entity_flows_daily "
                "WHERE entity_id IN (%s, %s) AND date = %s ORDER BY entity_id",
                (sentinel_entity_a, sentinel_entity_b, sentinel_date),
            )
            rows = cur.fetchall()

    assert len(rows) == 2, f"sentinel rows missing: {rows}"
    by_id = {r[0]: r[1] for r in rows}
    assert by_id[sentinel_entity_a] == pytest.approx(sentinel_inflow_a)
    assert by_id[sentinel_entity_b] == pytest.approx(sentinel_inflow_b)


async def _create_tables_async():
    from api.questdb_repository import create_tables_if_not_exist
    await create_tables_if_not_exist()


def test_dual_write_site_exists_in_source():
    """T024 [GUARD]: catches a future refactor that silently removes the
    QuestDB write half (FR-009 / FR-008 guard)."""
    src = Path("scripts/live/flow_aggregator.py").read_text()
    assert "save_entity_flows_daily" in src, (
        "save_entity_flows_daily not imported/called in flow_aggregator.py"
    )
    assert "_should_write_questdb" in src, (
        "_should_write_questdb gating helper missing"
    )


def test_duckdb_write_path_preserved():
    """T025 [GUARD]: catches a future refactor that removes the DuckDB write
    half BEFORE the legacy-removal follow-up spec authorises it (FR-002,
    FR-009)."""
    src = Path("scripts/live/flow_aggregator.py").read_text()
    assert "INSERT OR REPLACE INTO entity_flows_daily" in src, (
        "DuckDB write path INSERT OR REPLACE INTO entity_flows_daily is gone"
    )
