"""Tests for creation-side UTXO lifecycle catch-up."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


def test_refuses_when_initial_mirror_incomplete(monkeypatch):
    import scripts.bootstrap.catchup_utxo_lifecycle_to_tip as module

    monkeypatch.setattr(
        module,
        "_duckdb_state",
        lambda duckdb_path: module.LifecycleState(count=100, max_creation_block=1000),
    )
    monkeypatch.setattr(
        module,
        "_questdb_state",
        lambda: module.LifecycleState(count=10, max_creation_block=1000),
    )

    with pytest.raises(RuntimeError, match="incomplete"):
        module.catchup()


def test_dry_run_resolves_range_after_initial_mirror(monkeypatch):
    import scripts.bootstrap.catchup_utxo_lifecycle_to_tip as module

    monkeypatch.setattr(
        module,
        "_duckdb_state",
        lambda duckdb_path: module.LifecycleState(count=100, max_creation_block=1000),
    )
    monkeypatch.setattr(
        module,
        "_questdb_state",
        lambda: module.LifecycleState(count=100, max_creation_block=1000),
    )
    monkeypatch.setattr(module, "_bitcoin_tip", lambda: 1100)

    stats = module.catchup(dry_run=True)

    assert stats.start_block == 1001
    assert stats.end_block == 1100
    assert stats.dry_run is True
    assert stats.sync_result is None
    assert stats.mirrored_rows == 0


def test_sync_then_mirror_new_range(monkeypatch):
    import scripts.bootstrap.catchup_utxo_lifecycle_to_tip as module

    monkeypatch.setattr(
        module,
        "_duckdb_state",
        lambda duckdb_path: module.LifecycleState(count=100, max_creation_block=1000),
    )
    monkeypatch.setattr(
        module,
        "_questdb_state",
        lambda: module.LifecycleState(count=100, max_creation_block=1000),
    )
    monkeypatch.setattr(module, "_bitcoin_tip", lambda: 1002)

    calls = {}

    fake_sync_module = SimpleNamespace(
        UTXO_DB_PATH="old-utxo.duckdb",
        MAIN_DB_PATH="old-utxo.duckdb",
    )

    def fake_run_sync(**kwargs):
        calls["sync_utxo_path"] = fake_sync_module.UTXO_DB_PATH
        calls["sync_main_path"] = fake_sync_module.MAIN_DB_PATH
        calls["sync"] = kwargs
        return {"status": "completed", "blocks_processed": 2}

    fake_sync_module.run_sync = fake_run_sync

    def fake_mirror(**kwargs):
        calls["mirror"] = kwargs
        return SimpleNamespace(mirrored_rows=12)

    monkeypatch.setitem(
        sys.modules,
        "scripts.sync_utxo_lifecycle",
        fake_sync_module,
    )
    monkeypatch.setattr(module, "mirror", fake_mirror)

    stats = module.catchup(
        duckdb_path="/tmp/spec-061-catchup.duckdb", source="rpc-v3", workers=8
    )

    assert calls["sync_utxo_path"] == "/tmp/spec-061-catchup.duckdb"
    assert calls["sync_main_path"] == "/tmp/spec-061-catchup.duckdb"
    assert calls["sync"] == {
        "start_block": 1001,
        "end_block": 1002,
        "source": "rpc-v3",
        "workers": 8,
        "prune": False,
    }
    assert calls["mirror"]["start_block"] == 1001
    assert calls["mirror"]["end_block"] == 1002
    assert calls["mirror"]["allow_nonempty_target"] is True
    assert calls["mirror"]["resume"] is True
    assert stats.mirrored_rows == 12
    assert fake_sync_module.UTXO_DB_PATH == "old-utxo.duckdb"
    assert fake_sync_module.MAIN_DB_PATH == "old-utxo.duckdb"
