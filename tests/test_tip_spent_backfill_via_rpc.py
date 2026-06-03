"""Unit tests for tip_spent_backfill_via_rpc (spec-061 Wave 6 closing path).

Fully mocked. Verifies:
1. CLI surface (--start-block, --end-block, --workers).
2. Block input extraction skips coinbase (vin without txid).
3. UPDATE batching at the 1000-row boundary.
4. Range computation when no args are given (start = QuestDB max + 1, end = tip).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ── Block input extraction ────────────────────────────────────────────────────


def test_fetch_block_inputs_skips_coinbase():
    """A coinbase vin has no `txid`; spent backfill must NOT emit an UPDATE."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    fake_rpc = MagicMock()
    fake_rpc.getblockhash.return_value = "fakehash"
    fake_rpc.getblock.return_value = {
        "tx": [
            # Coinbase tx: vin has no txid.
            {"vin": [{"coinbase": "deadbeef"}]},
            # Normal tx with two spends.
            {
                "vin": [
                    {"txid": "aabb" * 16, "vout": 0},
                    {"txid": "ccdd" * 16, "vout": 3},
                ]
            },
        ]
    }

    with patch.object(module, "_thread_rpc_client", return_value=fake_rpc):
        height, updates = module._fetch_block_inputs(927970)

    assert height == 927970
    assert len(updates) == 2
    assert updates[0] == (927970, "aabb" * 16, 0)
    assert updates[1] == (927970, "ccdd" * 16, 3)


def test_fetch_block_inputs_skips_invalid_vout():
    """vin with a non-integer vout is silently skipped (defensive)."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    fake_rpc = MagicMock()
    fake_rpc.getblockhash.return_value = "h"
    fake_rpc.getblock.return_value = {
        "tx": [
            {
                "vin": [
                    {"txid": "good" * 16, "vout": 1},
                    {"txid": "bad" * 16, "vout": "not-int"},
                ]
            }
        ]
    }

    with patch.object(module, "_thread_rpc_client", return_value=fake_rpc):
        _, updates = module._fetch_block_inputs(927971)

    assert len(updates) == 1
    assert updates[0][2] == 1


# ── Batching ──────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, captured: list[tuple[str, list]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, query: str, params: list):
        self._captured.append((query, list(params)))


class _FakeConnection:
    def __init__(self, captured: list[tuple[str, list]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._captured)


def test_backfill_batches_at_threshold():
    """Batch is flushed when len(batch) >= _BATCH_SIZE.

    The script extends the batch with one block's worth of updates at a
    time and flushes when the running size crosses the threshold. With
    block-sized 1500 we therefore get ONE executemany call for 1500
    rows, then a final flush at end of input (no-op here). The contract
    is "bounded batch", not "exact 1000-row chunks".
    """
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    fake_blocks = {
        927968: [(927968, f"tx{i:062d}", i % 4) for i in range(1500)],
    }

    def fake_iter(start, end, workers=8):
        for h in range(start, end + 1):
            yield h, fake_blocks.get(h, [])

    captured: list[tuple[str, list]] = []

    with (
        patch.object(module, "_iter_block_updates", side_effect=fake_iter),
        patch.object(module, "_open_questdb_pg", return_value=_FakeConnection(captured)),
    ):
        rows = module.backfill(927968, 927968, workers=2)

    assert rows == 1500
    # Single flush carrying the whole bounded batch.
    assert len(captured) == 1
    assert len(captured[0][1]) == 1500
    assert "UPDATE utxo_lifecycle" in captured[0][0]
    assert "vout_index" in captured[0][0]


def test_backfill_flushes_each_block_when_above_threshold():
    """When each block already exceeds _BATCH_SIZE on its own, each block's
    extend() triggers a separate flush — one executemany per block."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    fake_blocks = {
        h: [(h, f"tx{h}{i:056d}", i % 4) for i in range(1200)]
        for h in (927968, 927969)
    }

    def fake_iter(start, end, workers=8):
        for h in range(start, end + 1):
            yield h, fake_blocks.get(h, [])

    captured: list[tuple[str, list]] = []
    with (
        patch.object(module, "_iter_block_updates", side_effect=fake_iter),
        patch.object(module, "_open_questdb_pg", return_value=_FakeConnection(captured)),
    ):
        rows = module.backfill(927968, 927969, workers=2)

    assert rows == 2400
    assert len(captured) == 2
    assert len(captured[0][1]) == 1200
    assert len(captured[1][1]) == 1200


def test_backfill_flushes_trailing_partial_batch():
    """If total updates < BATCH_SIZE, a single executemany still fires on exit."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    def fake_iter(start, end, workers=8):
        yield start, [(start, "tx" + "0" * 62, 0)]

    captured: list[tuple[str, list]] = []
    with (
        patch.object(module, "_iter_block_updates", side_effect=fake_iter),
        patch.object(module, "_open_questdb_pg", return_value=_FakeConnection(captured)),
    ):
        rows = module.backfill(927968, 927968)

    assert rows == 1
    assert len(captured) == 1
    assert len(captured[0][1]) == 1


# ── Range resolution ──────────────────────────────────────────────────────────


def test_main_resolves_range_from_questdb_and_tip():
    """When neither --start-block nor --end-block is given, the script derives
    them from QuestDB max(spent_block)+1 and bitcoin-cli getblockcount."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    with (
        patch.object(module, "_resolve_questdb_max_spent", return_value=950_000),
        patch.object(module, "_resolve_tip", return_value=952_000),
        patch.object(module, "backfill", return_value=42) as fake_backfill,
        patch("sys.argv", ["tip_spent_backfill_via_rpc"]),
    ):
        code = module.main()

    assert code == 0
    fake_backfill.assert_called_once()
    args, kwargs = fake_backfill.call_args
    # backfill(start, end, workers=...)
    assert args[0] == 950_001
    assert args[1] == 952_000


def test_main_skips_when_already_at_tip():
    """If start > end (QuestDB already at tip), backfill is not called."""
    from scripts.bootstrap import tip_spent_backfill_via_rpc as module

    with (
        patch.object(module, "_resolve_questdb_max_spent", return_value=952_000),
        patch.object(module, "_resolve_tip", return_value=951_999),
        patch.object(module, "backfill", return_value=0) as fake_backfill,
        patch("sys.argv", ["tip_spent_backfill_via_rpc"]),
    ):
        code = module.main()

    assert code == 0
    fake_backfill.assert_not_called()


# ── Log level resolution (parity with tip_catchup_lifecycle_via_rpc) ──────────


def test_resolve_log_level_handles_encrypted_env():
    """Encrypted/SOPS placeholders in LOG_LEVEL must degrade to INFO."""
    from scripts.bootstrap.tip_spent_backfill_via_rpc import _resolve_log_level
    import logging

    assert _resolve_log_level("INFO") == logging.INFO
    assert _resolve_log_level("DEBUG") == logging.DEBUG
    assert _resolve_log_level("ENC[AES256_GCM,data:abc==]") == logging.INFO
    assert _resolve_log_level("encrypted:abc==") == logging.INFO
    assert _resolve_log_level(None) == logging.INFO
    assert _resolve_log_level("") == logging.INFO
    assert _resolve_log_level("bogus") == logging.INFO
