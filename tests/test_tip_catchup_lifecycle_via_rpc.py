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
