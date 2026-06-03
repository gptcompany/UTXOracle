"""Tests for direct QuestDB UTXO lifecycle tip catch-up."""

from __future__ import annotations

from datetime import datetime, timezone


def test_iter_block_outputs_preserves_height_order(monkeypatch):
    import scripts.bootstrap.tip_catchup_lifecycle_via_rpc as module

    def fake_fetch(height: int):
        return height, datetime(2026, 1, 1, tzinfo=timezone.utc), {"height": height}

    monkeypatch.setattr(module, "_fetch_block_via_rpc", fake_fetch)

    rows = list(module._iter_block_outputs(10, 14, workers=2))

    assert [height for height, _ts, _block in rows] == [10, 11, 12, 13, 14]


def test_fetch_block_uses_output_only_verbosity(monkeypatch):
    import scripts.bootstrap.tip_catchup_lifecycle_via_rpc as module

    calls = []

    class FakeRPC:
        def getblockhash(self, height: int) -> str:
            calls.append(("getblockhash", height))
            return "block-hash"

        def getblock(self, block_hash: str, verbosity: int) -> dict:
            calls.append(("getblock", block_hash, verbosity))
            return {"time": 1767225600, "tx": []}

    monkeypatch.setattr(module, "_thread_rpc_client", FakeRPC)

    height, _block_time, block = module._fetch_block_via_rpc(928050)

    assert height == 928050
    assert block == {"time": 1767225600, "tx": []}
    assert calls == [
        ("getblockhash", 928050),
        ("getblock", "block-hash", 2),
    ]
