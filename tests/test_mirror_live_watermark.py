"""F-434 (rev-utx71-r2): the mirror's watermark only moves past rows a flush confirmed.

The client empties its buffer when a flush is rejected, and the bounded sender flushes from
inside row(): the rows of a rejected batch are gone. The checkpoint must stay on the last
confirmed row and the cycle must end with a non-zero exit, so the next run copies the rest.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from questdb.ingress import IngressError, IngressErrorCode

import api.questdb_repository as repository
import scripts.bootstrap.mirror_live_questdb_to_host as mirror

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
ROWS = [START + timedelta(seconds=i) for i in range(1, 11)]  # 10 rows
STREAM = "live_snapshots"


class _Inner:
    """Sender stand-in: one unit per row, a flush can be rejected (and then empties the buffer)."""

    def __init__(self, persisted, reject_flushes):
        self.persisted, self.reject_flushes = persisted, set(reject_flushes)
        self.buffer, self.flushes = [], 0

    def establish(self):
        pass

    def __len__(self):
        return len(self.buffer)

    def row(self, table, *, symbols, columns, at):
        self.buffer.append(at)

    def flush(self):
        self.flushes += 1
        rows, self.buffer = self.buffer, []
        if self.flushes in self.reject_flushes:
            raise IngressError(IngressErrorCode.ServerFlushError, "rejected")
        self.persisted.extend(rows)

    def close(self, flush=True):
        if flush and self.buffer:
            self.flush()


class _Source:
    def close(self):
        pass


@pytest.fixture
def cycle(monkeypatch, tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    persisted: list = []
    monkeypatch.setattr(mirror, "CHECKPOINT_PATH", checkpoint)
    monkeypatch.setattr(mirror, "_source_connection", lambda: _Source())
    monkeypatch.setattr(repository, "ILP_FLUSH_BYTES", 4)  # auto flush every 4 rows

    def stream_rows(conn, spec, last_ts, limit):
        for at in ROWS:
            if last_ts is None or at.isoformat() > last_ts:
                yield {spec.at_column: at}

    monkeypatch.setattr(mirror, "_stream_rows", stream_rows)

    def run(*, reject=()):
        inner = _Inner(persisted, reject)
        monkeypatch.setattr(
            mirror, "_target_sender", lambda: repository._BoundedSender(inner)
        )
        monkeypatch.setattr("sys.argv", ["mirror", "--stream", STREAM])
        return mirror.main()

    def watermark():
        return (
            json.loads(checkpoint.read_text()).get(STREAM)
            if checkpoint.exists()
            else None
        )

    return run, watermark, persisted


def test_rejected_first_flush_leaves_the_watermark_and_fails(cycle):
    run, watermark, persisted = cycle
    assert run(reject={1}) != 0
    assert watermark() in (None, "")
    assert persisted == []


def test_rejected_second_flush_keeps_the_watermark_on_the_first_batch(cycle):
    run, watermark, persisted = cycle
    assert run(reject={2}) != 0
    assert persisted == ROWS[:4]
    assert watermark() == ROWS[3].isoformat()


def test_a_run_without_rejections_after_a_failure_leaves_no_gap(cycle):
    run, watermark, persisted = cycle
    assert run(reject={2}) != 0
    assert run() == 0
    assert persisted == ROWS
    assert watermark() == ROWS[-1].isoformat()
