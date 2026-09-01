"""Unit tests for spec-061 Phase 1.5-v2 QuestDB-native freshness writers."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone


class FakeSender:
    def __init__(self):
        self.rows = []
        self.established = False
        self.flushes = 0
        self.closed = False

    def establish(self):
        self.established = True

    def row(self, table, symbols, columns, at):
        self.rows.append(
            {
                "table": table,
                "symbols": symbols,
                "columns": columns,
                "at": at,
            }
        )

    def flush(self):
        self.flushes += 1

    def close(self):
        self.closed = True


def test_block_heights_writer_streams_to_questdb(monkeypatch):
    from scripts.bootstrap import build_block_heights_questdb as writer

    sender = FakeSender()
    monkeypatch.setattr(writer, "_open_sender", lambda: sender)
    monkeypatch.setattr(
        writer,
        "iter_block_timestamps",
        lambda start, end, workers: iter(
            [
                (10, datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)),
                (11, datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)),
            ]
        ),
    )

    rows = writer.build_block_heights(10, 11, workers=2)

    assert rows == 2
    assert sender.established is True
    assert sender.flushes >= 1
    assert sender.closed is True
    assert [row["table"] for row in sender.rows] == ["block_heights", "block_heights"]
    assert sender.rows[0]["columns"]["height"] == 10
    assert sender.rows[0]["at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_daily_prices_writer_streams_to_questdb(monkeypatch):
    from scripts.bootstrap import build_price_table_questdb as writer

    async def fake_fetch_prices_batch(
        dates,
        session,
        mempool_url,
        semaphore,
        fallback_mempool_url,
    ):
        assert fallback_mempool_url == writer.DEFAULT_FALLBACK_MEMPOOL_URL
        return {dates[0]: 99_000.0}

    sender = FakeSender()
    monkeypatch.setattr(writer, "_open_sender", lambda: sender)
    monkeypatch.setattr(writer, "fetch_prices_batch", fake_fetch_prices_batch)

    rows = asyncio.run(
        writer.build_price_table(
            date(2026, 1, 1),
            date(2026, 1, 1),
            batch_size=1,
            rate_limit=1,
        )
    )

    assert rows == 1
    assert sender.established is True
    assert sender.flushes >= 1
    assert sender.closed is True
    row = sender.rows[0]
    assert row["table"] == "daily_prices"
    assert row["symbols"] == {"source": "mempool_space"}
    assert row["columns"]["price_usd"] == 99_000.0
    assert row["at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_phase15_writers_do_not_import_duckdb():
    from scripts.bootstrap import build_block_heights_questdb as blocks
    from scripts.bootstrap import build_price_table_questdb as prices

    assert "duckdb" not in vars(blocks)
    assert "duckdb" not in vars(prices)
