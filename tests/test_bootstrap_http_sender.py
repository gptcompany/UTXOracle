"""F-434: the bootstrap scripts write through the one HTTP sender, never ILP over TCP.

Over TCP QuestDB drops a row it cannot ingest without telling the writer; the HTTP flush is
confirmed. Each script's sender builder is run against a stand-in for the questdb client, so
no connection is opened.
"""

from __future__ import annotations

import importlib

import pytest

import api.questdb_repository as repository

BUILDERS = [
    ("scripts.bootstrap.tip_catchup_lifecycle_via_rpc", "_ilp_sender"),
    ("scripts.bootstrap.mirror_live_questdb_to_host", "_target_sender"),
    ("scripts.bootstrap.build_block_heights_questdb", "_open_sender"),
    ("scripts.bootstrap.build_price_table_questdb", "_open_sender"),
]


class _Recorder:
    calls: list = []

    def __init__(self, protocol, host, port, **kwargs):
        type(self).calls.append((protocol, host, port, kwargs))

    def establish(self):
        pass


@pytest.mark.parametrize(("module", "builder"), BUILDERS)
def test_script_sender_is_the_confirmed_http_sender(monkeypatch, module, builder):
    _Recorder.calls = []
    monkeypatch.setattr(repository, "Sender", _Recorder)
    monkeypatch.setattr(repository, "QUESTDB_HTTP_HOST", "db.invalid")
    monkeypatch.setattr(repository, "QUESTDB_HTTP_PORT", 9900)

    getattr(importlib.import_module(module), builder)()

    assert _Recorder.calls == [("http", "db.invalid", 9900, {"auto_flush": False})]
