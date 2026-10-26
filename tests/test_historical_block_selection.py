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
    # If scripts.daily_analysis was imported earlier (collection, another module) it already
    # holds the REAL load_secrets on a machine that has the loader (the Dell): that one reads
    # the machine's encrypted secrets into os.environ. Replace the bound name too.
    already_imported = sys.modules.get("scripts.daily_analysis")
    if already_imported is not None:
        monkeypatch.setattr(already_imported, "load_secrets", stub.load_secrets)


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
        self.block_calls: list[str] = []  # hashes passed to getblock, in order
        self.calls: list[str] = []  # every RPC method received, in order
        self.reorg_from: int | None = (
            None  # heights >= this are replaced by "alt" blocks
        )
        self.stale_header_height: int | None = (
            None  # that block's header: confirmations -1
        )

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
        self.calls.append(method)
        if method == "getblockcount":
            return self.tip
        if method == "getblockhash":
            h = params[0]
            return (
                f"alt{h}"
                if self.reorg_from is not None and h >= self.reorg_from
                else f"hash{h}"
            )
        h = int(params[0][4:] if params[0].startswith("hash") else params[0][3:])
        confirmations = self.tip - h + 1
        if method == "getblockheader":
            if h == self.stale_header_height:
                confirmations = -1
            if h in self.fail_header:
                raise RuntimeError("rpc header down (test)")
            return {
                "time": self.time(h),
                "mediantime": self.mediantime(h),
                "confirmations": confirmations,
            }
        if method == "getblock":
            self.block_calls.append(params[0])
            if h == self.fail_block:
                raise RuntimeError("rpc block down (test)")
            if (
                self.reorg_from is not None
                and params[0].startswith("hash")
                and h >= self.reorg_from
            ):
                confirmations = -1  # the block left the best chain

            tx = _Tx(
                txid=f"tx{h}",
                vin=[{"txid": "x"}],
                vout=[{"value": 0.1}, {"value": 0.2}],
            )
            self.tx_refs[h] = weakref.ref(tx)
            return {"tx": [tx], "confirmations": confirmations}
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


def _main_with_historical_day(monkeypatch, chain, tmp_path=None, expect_exit=True):
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
    # The start-up checks (destination, dedup, .env, run window) have their own tests in
    # test_daily_analysis_questdb_e2e.py; here the day is fixed and nothing external is read.
    monkeypatch.setattr(
        daily,
        "preflight",
        lambda args: (datetime(2026, 10, 25, tzinfo=timezone.utc), set(), False),
    )
    # The fail-closed gate of main() (F-438) is lifted: these tests check the selection errors
    # and exit codes as they will work once F-432 computes the metrics in the same pass.
    monkeypatch.setattr(daily, "HISTORICAL_DAY_IS_STREAMED", False)
    monkeypatch.setattr(daily, "validate_config", lambda config: None)
    monkeypatch.setattr(daily, "WhaleFlowDetector", None)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", False)
    monkeypatch.setattr(
        daily, "fetch_mempool_price_at", lambda timestamp, url: 100_000.0
    )
    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py"])

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            count = sum(1 for _ in transactions)
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": count}

    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)

    def calculate(config, day=None):
        result = daily.UTXOracleCalculator().calculate_price_for_transactions(
            daily.fetch_historical_transactions(DAY, config)
        )
        result["fetch_tier"] = 3
        # what the metrics need, so that a success would really write both tables
        result["transactions"] = [
            {
                "vin": [{"prevout": {"scriptpubkey_address": "bc1qin"}}],
                "vout": [{"scriptpubkey_address": "bc1qout", "value": 0.5}],
            }
        ]
        return result

    monkeypatch.setattr(daily, "calculate_utxoracle_price", calculate)
    if not expect_exit:
        daily.main()
        return 0, sent
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


# --- M2 (B3): hashes fixed at selection, read by hash; last block needs confirmations ------


def test_blocks_are_read_by_the_hashes_fixed_at_selection(monkeypatch):
    chain = FakeChain(tip=700)

    list(_fetch(monkeypatch, chain))

    assert chain.block_calls == [f"hash{h}" for h in range(FIRST, FIRST + 144)]


def test_a_block_that_left_the_best_chain_during_the_stream_is_an_explicit_error(
    monkeypatch,
):
    import scripts.daily_analysis as daily

    chain = FakeChain(tip=700)
    stream = _fetch(monkeypatch, chain)
    chain.reorg_from = FIRST + 10  # after the selection: heights >= this are replaced

    with pytest.raises(daily.StaleBlockError, match="confirmations"):
        list(stream)


def test_a_reorg_mid_stream_ends_the_process_with_exit_2_and_nothing_written(
    monkeypatch,
):
    chain = FakeChain(tip=700)
    original = chain.call

    def reorg_when_streaming(method, params=None):
        if (
            method == "getblock"
            and chain.reorg_from is None
            and len(chain.block_calls) == 5
        ):
            chain.reorg_from = FIRST + 10
        return original(method, params)

    chain.call = reorg_when_streaming

    code, sent = _main_with_historical_day(monkeypatch, chain)

    assert code == 2
    assert sent == []


def test_last_block_with_too_few_confirmations_is_an_incomplete_window(monkeypatch):
    import scripts.daily_analysis as daily

    end_first = FIRST + 144
    # tip mediantime >= D+1 (so the tip check passes) but the last block of D has 4 confirmations
    chain = FakeChain(tip=end_first + 2)
    with pytest.raises(daily.IncompleteWindowError, match="confirmations"):
        _fetch(monkeypatch, chain)

    code, sent = _main_with_historical_day(monkeypatch, FakeChain(tip=end_first + 2))
    assert code == daily.EXIT_INCOMPLETE_WINDOW
    assert sent == []

    assert len(list(_fetch(monkeypatch, FakeChain(tip=end_first + 5)))) == 144  # 7 >= 6


def test_min_confirmations_is_configurable_and_a_bad_value_is_reported_by_name_only(
    monkeypatch,
):
    import scripts.daily_analysis as daily

    end_first = FIRST + 144
    monkeypatch.setenv("MIN_CONFIRMATIONS", "3")
    assert len(list(_fetch(monkeypatch, FakeChain(tip=end_first + 2)))) == 144  # 4 >= 3

    monkeypatch.setenv("MIN_CONFIRMATIONS", "not-a-number-5521")
    with pytest.raises(ValueError) as error:
        _fetch(monkeypatch, FakeChain(tip=700))
    assert "MIN_CONFIRMATIONS" in str(error.value)
    assert "not-a-number-5521" not in str(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert daily.DEFAULT_MIN_CONFIRMATIONS == 6


@pytest.mark.parametrize("value", ["0", "-3", "abc-7741"])
def test_min_confirmations_must_be_an_integer_of_at_least_1(monkeypatch, value):
    monkeypatch.setenv("MIN_CONFIRMATIONS", value)

    with pytest.raises(ValueError) as error:
        _fetch(monkeypatch, FakeChain(tip=700))

    assert "MIN_CONFIRMATIONS" in str(error.value)
    assert value not in str(error.value)  # the value is never reported


@pytest.mark.parametrize("value", ["0", "-3", "abc-7741"])
def test_a_bad_min_confirmations_ends_the_process_with_exit_6_naming_only_the_variable(
    monkeypatch, caplog, value
):
    import scripts.daily_analysis as daily

    monkeypatch.setenv("MIN_CONFIRMATIONS", value)

    with caplog.at_level("ERROR"):
        code, sent = _main_with_historical_day(monkeypatch, FakeChain(tip=700))

    assert code == daily.EXIT_BAD_ENV_VALUE == 6
    assert sent == []
    assert "MIN_CONFIRMATIONS" in caplog.text
    # (a bare "0" or "-3" also occurs in line numbers: look for the value in context)
    for shape in (f"={value}", f"'{value}'", f'"{value}"', f": {value}"):
        assert shape not in caplog.text
    if value.startswith("abc"):
        assert value not in caplog.text


def test_the_wired_main_writes_both_tables_for_a_healthy_day(monkeypatch):
    """Control for the exit tests above: with a healthy chain the same wiring writes."""
    code, sent = _main_with_historical_day(
        monkeypatch, FakeChain(tip=700), expect_exit=False
    )

    assert code == 0
    assert set(sent) == {"price_analysis", "metrics"}


# --- review r1 of #65 --------------------------------------------------------------------
# These tests use NO stub of the calculator. The tests above that replace
# UTXOracleCalculator with a stub are: _main_with_historical_day (and every test built on
# it) and test_backfill_records_the_dedicated_historical_tier_and_streams.


def _plain_transactions(count: int) -> list[dict]:
    return [
        {
            "txid": f"t{i}",
            "vin": [{"txid": f"p{i}"}],
            "vout": [
                {"value": 0.01 + (i % 50) / 1000},
                {"value": 0.02 + (i % 70) / 1000},
            ],
        }
        for i in range(count)
    ]


def test_the_real_calculator_consumes_a_one_shot_generator_like_a_list():
    from UTXOracle_library import UTXOracleCalculator

    transactions = _plain_transactions(1500)
    from_list = UTXOracleCalculator().calculate_price_for_transactions(transactions)

    pulled = []

    def one_shot():
        for tx in transactions:
            pulled.append(tx["txid"])
            yield tx

    from_stream = UTXOracleCalculator().calculate_price_for_transactions(one_shot())

    assert len(pulled) == 1500  # consumed once, element by element
    assert from_stream["diagnostics"]["total_txs"] == 1500
    assert from_stream == from_list  # same answer as with the list


def test_the_real_calculator_on_an_empty_stream_answers_without_an_exception():
    from UTXOracle_library import UTXOracleCalculator

    result = UTXOracleCalculator().calculate_price_for_transactions(iter(()))

    assert result["tx_count"] == 0 and result["price_usd"] is None


def test_a_stale_last_header_is_stale_block_error_exit_2_not_an_incomplete_window(
    monkeypatch,
):
    import scripts.daily_analysis as daily

    last = FIRST + 143

    def stale_final_header():
        chain = FakeChain(tip=700)
        chain.stale_header_height = (
            last  # hashes are fixed, then the last header says -1
        )
        return chain

    with pytest.raises(daily.StaleBlockError, match="confirmations"):
        _fetch(monkeypatch, stale_final_header())

    code, sent = _main_with_historical_day(monkeypatch, stale_final_header())
    assert code == 2
    assert sent == []


def test_a_real_mempool_call_in_these_tests_fails_loudly():
    """The conftest guard (F-446): before it, the Dell's local mempool answered, CI's did not."""
    import socket

    import scripts.daily_analysis as daily

    with pytest.raises(AssertionError, match="real network call"):
        daily.fetch_mempool_price_at(1, "http://localhost:8999")
    with pytest.raises(AssertionError, match="real network call"):
        daily.fetch_mempool_price("http://localhost:8999")  # requests -> socket
    with pytest.raises(AssertionError, match="real network call"):
        socket.socket().connect(("127.0.0.1", 3002))  # electrs default
    with pytest.raises(AssertionError, match="real network call"):
        socket.socket().connect(("93.184.216.34", 80))  # any non-loopback host
