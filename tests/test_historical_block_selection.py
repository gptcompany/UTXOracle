"""F-442: the blocks of a day are selected by MEDIANTIME, exactly, and streamed.

Bitcoin Core is replaced by a SYNTHETIC chain (declared as such): a fake rpc_client whose
heights have a strictly monotone `mediantime` (BIP113) and a deliberately misleading `time`
at the day boundaries, so that selecting by `time` gives a different set of blocks.
"""

from __future__ import annotations

import gc
import sys
import types
import weakref
from datetime import datetime, timezone

import pytest

DAY = "2026-10-26"  # D: the day passed as date_str
START = int(datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp())  # D 00:00:00Z
END = START + 86400  # D+1 00:00:00Z
FIRST = 500  # height whose mediantime is exactly D 00:00:00Z
SPACING = 600  # seconds between mediantimes: 144 blocks in the day


@pytest.fixture(autouse=True)
def _secrets_loader_stub(monkeypatch):
    stub = types.ModuleType("secrets_loader")
    stub.load_secrets = lambda _path=None: False
    monkeypatch.setitem(sys.modules, "secrets_loader", stub)


class _Tx(dict):
    """A dict that supports weakrefs (plain dicts do not)."""


class FakeChain:
    """Synthetic chain. m(h) = START + offset(h - FIRST): strictly monotone."""

    def __init__(self, tip, offset=lambda k: k * SPACING, fail_header=()):
        self.tip = tip
        self.offset = offset
        self.fail_header = set(fail_header)
        self.fail_block = None
        self.tx_refs: dict[int, weakref.ref] = {}

    def mediantime(self, h):
        return START + self.offset(h - FIRST)

    def time(self, h):
        # `time` is NOT monotone at the boundaries (allowed by consensus): the block that
        # starts the day looks like the previous day, the one before it looks inside, and
        # the same at D+1 00:00Z.
        end_first = (
            FIRST + (END - START) // SPACING
        )  # first height with mediantime >= END
        special = {
            FIRST - 1: START + 5,
            FIRST: START - 10,
            end_first - 1: END + 20,
            end_first: END - 30,
        }
        return special.get(h, self.mediantime(h) + 300)

    def call(self, method, params=None):
        if method == "getblockcount":
            return self.tip
        if method == "getblockhash":
            return f"hash{params[0]}"
        h = int(params[0][4:])
        if method == "getblockheader":
            if h in self.fail_header:
                raise RuntimeError("rpc header down (test)")
            return {"time": self.time(h), "mediantime": self.mediantime(h)}
        if method == "getblock":
            if h == self.fail_block:
                raise RuntimeError("rpc block down (test)")
            tx = _Tx(
                txid=f"tx{h}",
                vin=[{"txid": "x"}],
                vout=[{"value": 0.1}, {"value": 0.2}],
            )
            self.tx_refs[h] = weakref.ref(tx)
            return {"tx": [tx]}
        raise AssertionError(method)


def _fetch(monkeypatch, chain):
    import scripts.daily_analysis as daily

    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    return daily.fetch_historical_transactions(DAY, {})


def _txids(transactions) -> set[str]:
    return {tx["txid"] for tx in transactions}


def test_selection_is_exact_by_mediantime_even_with_time_out_of_order(monkeypatch):
    chain = FakeChain(tip=700)

    selected = _txids(_fetch(monkeypatch, chain))

    end_first = FIRST + 144
    assert selected == {f"tx{h}" for h in range(FIRST, end_first)}
    assert (
        f"tx{FIRST}" in selected
    )  # mediantime == D 00:00:00Z: in, though time says D-1
    assert f"tx{FIRST - 1}" not in selected  # time says inside, mediantime says D-1
    assert f"tx{end_first - 1}" in selected  # mediantime < D+1, though time says D+1
    assert f"tx{end_first}" not in selected  # mediantime == D+1 00:00:00Z: out


def _main_with_historical_day(monkeypatch, chain, tmp_path=None):
    """main() wired the way the daily job will use the historical path: the price comes
    from the library fed with the day's blocks; any exception must end the process."""
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    sent: list[str] = []
    monkeypatch.setattr(
        repository.QuestDBRepository,
        "_send_row",
        lambda self, table, symbols, columns, at=None, flush=False: sent.append(table)
        or True,
    )
    monkeypatch.setattr(daily, "validate_config", lambda config: None)
    monkeypatch.setattr(daily, "WhaleFlowDetector", None)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", False)
    monkeypatch.setattr(daily, "fetch_mempool_price", lambda url: 100_000.0)
    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py"])

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            count = sum(1 for _ in transactions)
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": count}

    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)

    def calculate(config):
        result = daily.UTXOracleCalculator().calculate_price_for_transactions(
            daily.fetch_historical_transactions(DAY, config)
        )
        result["fetch_tier"] = 3
        return result

    monkeypatch.setattr(daily, "calculate_utxoracle_price", calculate)
    with pytest.raises(SystemExit) as stop:
        daily.main()
    return stop.value.code, sent


def test_rpc_error_near_the_end_of_the_day_is_propagated_not_swallowed(monkeypatch):
    # The headers around D+1 00:00Z are the ones any exact boundary search has to read.
    chain = FakeChain(tip=700, fail_header=range(FIRST + 139, FIRST + 149))

    with pytest.raises(RuntimeError, match="rpc header down"):
        list(_fetch(monkeypatch, chain))


def test_rpc_error_mid_day_ends_the_process_non_zero_with_nothing_written(monkeypatch):
    chain = FakeChain(tip=700, fail_header=range(FIRST + 139, FIRST + 149))

    code, sent = _main_with_historical_day(monkeypatch, chain)

    assert code == 2
    assert sent == []


def test_incomplete_window_is_a_dedicated_error_and_exit_7_without_writing(monkeypatch):
    import scripts.daily_analysis as daily

    end_first = FIRST + 144
    chain = FakeChain(tip=end_first - 1)  # tip mediantime < D+1 00:00Z: day still open

    with pytest.raises(daily.IncompleteWindowError):
        _fetch(monkeypatch, chain)

    code, sent = _main_with_historical_day(monkeypatch, FakeChain(tip=end_first - 1))
    assert code == daily.EXIT_INCOMPLETE_WINDOW == 7
    assert sent == []


def test_a_day_of_401_blocks_is_implausible_and_400_is_the_allowed_limit(monkeypatch):
    import scripts.daily_analysis as daily

    many = FakeChain(tip=1200, offset=lambda k: k * 86400 // 401)  # 401 blocks in D
    with pytest.raises(daily.ImplausibleDayError, match="401"):
        _fetch(monkeypatch, many)

    limit = FakeChain(tip=1200, offset=lambda k: k * 216)  # exactly 400 blocks in D
    assert len(list(_fetch(monkeypatch, limit))) == 400


def test_blocks_are_streamed_and_not_retained(monkeypatch):
    """No list of the day, no block kept: consumed blocks are garbage collectable."""
    chain = FakeChain(tip=700)
    stream = _fetch(monkeypatch, chain)

    assert not isinstance(stream, (list, tuple, dict)), (
        "the day must not be a collection"
    )
    seen = []
    for tx in stream:
        seen.append(tx["txid"])  # only a string is kept, never the transaction
        if len(seen) == 3:
            break
    del tx
    gc.collect()

    assert chain.tx_refs[FIRST]() is None  # the first block's transaction is gone


def test_callers_let_the_incomplete_window_error_through(monkeypatch):
    import scripts.daily_analysis as daily

    def open_day(*args, **kwargs):
        raise daily.IncompleteWindowError("day still open (test)")

    monkeypatch.setattr(daily, "fetch_bitcoin_transactions", open_day)
    monkeypatch.setattr(daily, "fetch_historical_transactions", open_day)
    monkeypatch.setattr(daily, "fetch_mempool_price", lambda url: 1.0)

    with pytest.raises(daily.IncompleteWindowError):
        daily.calculate_utxoracle_price({})
    with pytest.raises(daily.IncompleteWindowError):
        daily.backfill_gap(DAY, {})


def test_backfill_records_the_dedicated_historical_tier_and_streams(monkeypatch):
    import scripts.daily_analysis as daily

    saved: list[dict] = []
    chain = FakeChain(tip=700)
    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    monkeypatch.setattr(daily, "fetch_mempool_price", lambda url: 100_000.0)
    monkeypatch.setattr(daily, "save_to_questdb", saved.append)

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            assert not isinstance(transactions, (list, tuple))
            return {
                "price_usd": 99_500.0,
                "confidence": 0.9,
                "tx_count": sum(1 for _ in transactions),
            }

    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)

    assert daily.backfill_gap(DAY, {}) is True
    assert saved[0]["fetch_tier"] == daily.FETCH_TIER_RPC_HISTORICAL == 4
    assert saved[0]["tx_count"] == 144
