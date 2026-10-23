"""RPC consumers authenticate with the bitcoind cookie (R4-H1).

A fake JSON-RPC HTTP server accepts only the current cookie, like bitcoind after
removing rpcuser/rpcpassword. Every credential here is a dummy. Imports of the
code under test are lazy so these tests also run (and fail) on the pre-fix head.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from tests.fake_bitcoind import FakeBitcoind, load_live_rpc

COOKIE_1 = "__cookie__:DUMMYCOOKIE0001"
COOKIE_2 = "__cookie__:DUMMYCOOKIE0002"
LEGACY = ("legacy_user", "DUMMYLEGACYPASS")
pytestmark = pytest.mark.usefixtures("hermetic_rpc")


@pytest.fixture
def node(tmp_path):
    """Datadir with a cookie-only bitcoin.conf and a fake node on a free port."""
    srv = FakeBitcoind(tuple(COOKIE_1.split(":")), {"getblockcount": lambda p: 900_000})
    (tmp_path / ".cookie").write_text(COOKIE_1)
    (tmp_path / "bitcoin.conf").write_text(f"rpcport={srv.port}\n")
    srv.datadir = tmp_path
    yield srv
    srv.stop()


def rotate_cookie(node: FakeBitcoind) -> None:
    """bitcoind restart: new cookie on disk, old one rejected."""
    node.accepted = tuple(COOKIE_2.split(":"))
    (node.datadir / ".cookie").write_text(COOKIE_2)


# --- shared helper -------------------------------------------------------------


def test_helper_cookie_only_call(node):
    from scripts.utils.rpc_cookie import RpcClient

    assert RpcClient(node.datadir).call("getblockcount") == 900_000
    assert node.requests == [("getblockcount", "__cookie__")]


def test_helper_401_rereads_cookie_once_and_retries(node):
    from scripts.utils.rpc_cookie import RpcClient

    client = RpcClient(node.datadir)
    rotate_cookie(node)
    assert client.call("getblockcount") == 900_000
    assert [u for _, u in node.requests] == ["__cookie__", "__cookie__"]


def test_helper_second_401_is_an_error_without_a_second_retry(node):
    from scripts.utils.rpc_cookie import RpcClient

    client = RpcClient(node.datadir)
    node.accepted = ("nobody", "DUMMYOTHER")  # cookie on disk never matches
    with pytest.raises(ConnectionError, match="401"):
        client.call("getblockcount")
    assert len(node.requests) == 2


def test_helper_cookie_absent_at_construction_is_picked_up_later(node):
    """R5-M3: started before bitcoind wrote the cookie; same object must recover."""
    from scripts.utils.rpc_cookie import RpcAuthError, RpcClient

    (node.datadir / ".cookie").unlink()
    client = RpcClient(node.datadir)
    with pytest.raises(RpcAuthError):
        client.call("getblockcount")
    assert node.requests == []  # refused before any HTTP while there is no cookie
    (node.datadir / ".cookie").write_text(COOKIE_1)
    assert client.call("getblockcount") == 900_000
    assert node.requests == [("getblockcount", "__cookie__")]


def test_helper_cookie_unreadable_at_401_reread_recovers_on_next_call(node):
    """R5-M3: bitcoind restarting, cookie briefly gone when re-read after the 401."""
    from scripts.utils.rpc_cookie import RpcAuthError, RpcClient

    client = RpcClient(node.datadir)
    node.accepted = tuple(COOKIE_2.split(":"))
    (node.datadir / ".cookie").unlink()
    with pytest.raises(RpcAuthError) as exc:
        client.call("getblockcount")
    assert exc.value.status == 401
    assert len(node.requests) == 1  # no retry without a cookie to retry with
    (node.datadir / ".cookie").write_text(COOKIE_2)
    assert client.call("getblockcount") == 900_000
    assert len(node.requests) == 2


def test_helper_recovered_but_rejected_cookie_still_retries_once_per_call(node):
    """R5-M3: the per-call 401 retry stays bounded to one re-read and one retry."""
    from scripts.utils.rpc_cookie import RpcClient

    (node.datadir / ".cookie").unlink()
    client = RpcClient(node.datadir)
    (node.datadir / ".cookie").write_text(COOKIE_1)
    node.accepted = ("nobody", "DUMMYOTHER")
    for expected in (2, 4):
        with pytest.raises(ConnectionError, match="401"):
            client.call("getblockcount")
        assert len(node.requests) == expected


def test_helper_cookie_wins_over_conf_credentials(node):
    from scripts.utils.rpc_cookie import RpcClient

    with open(node.datadir / "bitcoin.conf", "a") as f:
        f.write(f"rpcuser={LEGACY[0]}\nrpcpassword={LEGACY[1]}\n")
    RpcClient(node.datadir).call("getblockcount")
    assert node.requests == [("getblockcount", "__cookie__")]


def test_helper_conf_credentials_only_as_fallback_without_cookie(node):
    from scripts.utils.rpc_cookie import RpcClient

    (node.datadir / ".cookie").unlink()
    node.accepted = LEGACY
    with open(node.datadir / "bitcoin.conf", "a") as f:
        f.write(f"rpcuser={LEGACY[0]}\nrpcpassword={LEGACY[1]}\n")
    assert RpcClient(node.datadir).call("getblockcount") == 900_000
    assert node.requests == [("getblockcount", LEGACY[0])]


def test_helper_honours_rpccookiefile(node, tmp_path_factory):
    from scripts.utils.rpc_cookie import RpcClient

    other = tmp_path_factory.mktemp("cookie") / "custom.cookie"
    other.write_text(COOKIE_1)
    (node.datadir / ".cookie").unlink()
    with open(node.datadir / "bitcoin.conf", "a") as f:
        f.write(f"rpccookiefile={other}\n")
    assert RpcClient(node.datadir).call("getblockcount") == 900_000


def test_helper_without_any_credential_fails_without_leaking(node, caplog):
    from scripts.utils.rpc_cookie import RpcClient

    (node.datadir / ".cookie").unlink()
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ConnectionError) as exc:
        RpcClient(node.datadir).call("getblockcount")
    assert node.requests == []
    assert "DUMMY" not in str(exc.value) + caplog.text


def test_helper_never_logs_the_cookie_value(node, caplog):
    from scripts.utils.rpc_cookie import RpcClient

    caplog.set_level(logging.DEBUG)
    client = RpcClient(node.datadir)
    rotate_cookie(node)
    client.call("getblockcount")
    assert "DUMMYCOOKIE" not in caplog.text


def test_helper_malformed_cookie_is_ignored_with_a_warning(node, caplog):
    from scripts.utils.rpc_cookie import RpcClient, read_cookie

    (node.datadir / ".cookie").write_text("no-separator-here")
    caplog.set_level(logging.WARNING)
    assert read_cookie(node.datadir) is None
    assert "malformed" in caplog.text and "no-separator" not in caplog.text
    with pytest.raises(ConnectionError):
        RpcClient(node.datadir).call("getblockcount")


def test_helper_http_and_json_rpc_errors_are_distinct(node):
    from scripts.utils.rpc_cookie import RpcClient, RpcHttpError

    client = RpcClient(node.datadir)
    with pytest.raises(ConnectionError, match="failed"):
        client.call("nosuchmethod")
    node.force_status = 503
    with pytest.raises(RpcHttpError) as exc:
        client.call("getblockcount")
    assert exc.value.status == 503


def test_live_client_started_with_legacy_password_survives_the_migration(node):
    """R4-H1 scenario: client built before the migration, then conf directives
    removed and a new cookie issued."""
    LiveRPC = load_live_rpc()
    (node.datadir / ".cookie").unlink()
    node.accepted = LEGACY
    conf = node.datadir / "bitcoin.conf"
    legacy_conf = f"rpcport={node.port}\nrpcuser={LEGACY[0]}\nrpcpassword={LEGACY[1]}\n"
    conf.write_text(legacy_conf)
    client = LiveRPC(datadir=str(node.datadir))
    assert client.ask_node("getblockcount") == 900_000

    conf.write_text(f"rpcport={node.port}\n")
    rotate_cookie(node)
    assert client.ask_node("getblockcount") == 900_000


# --- consumers -------------------------------------------------------------------


@pytest.fixture
def sync_rpc(node, monkeypatch):
    """scripts.sync_utxo_lifecycle.BitcoinRPC pointed at the fake node, no user/password."""
    from scripts import sync_utxo_lifecycle as mod

    for var in ("BITCOIN_RPC_USER", "BITCOIN_RPC_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BITCOIN_RPC_URL", f"http://127.0.0.1:{node.port}")
    monkeypatch.setenv("BITCOIN_DATADIR", str(node.datadir))
    return mod.BitcoinRPC


def test_sync_client_without_user_and_password_uses_cookie(node, sync_rpc):
    assert sync_rpc().getblockcount() == 900_000
    assert node.requests == [("getblockcount", "__cookie__")]


def test_sync_client_rereads_cookie_after_401(node, sync_rpc):
    rpc = sync_rpc()
    rotate_cookie(node)
    assert rpc.getblockcount() == 900_000


def test_sync_cookie_wins_over_env_user_and_password(node, sync_rpc, monkeypatch):
    monkeypatch.setenv("BITCOIN_RPC_USER", LEGACY[0])
    monkeypatch.setenv("BITCOIN_RPC_PASSWORD", LEGACY[1])
    assert sync_rpc().getblockcount() == 900_000
    assert node.requests == [("getblockcount", "__cookie__")]


def test_sync_env_user_and_password_are_only_a_fallback(node, sync_rpc, monkeypatch):
    (node.datadir / ".cookie").unlink()
    node.accepted = LEGACY
    monkeypatch.setenv("BITCOIN_RPC_USER", LEGACY[0])
    monkeypatch.setenv("BITCOIN_RPC_PASSWORD", LEGACY[1])
    assert sync_rpc().getblockcount() == 900_000


def test_live_client_without_user_and_password_uses_cookie(node):
    BitcoinRPC = load_live_rpc()

    assert BitcoinRPC(datadir=str(node.datadir)).ask_node("getblockcount") == 900_000


def test_live_client_rereads_cookie_after_401(node):
    BitcoinRPC = load_live_rpc()

    rpc = BitcoinRPC(datadir=str(node.datadir))
    rotate_cookie(node)
    assert rpc.ask_node("getblockcount") == 900_000


def test_live_cookie_wins_over_conf_user_and_password(node):
    BitcoinRPC = load_live_rpc()

    with open(node.datadir / "bitcoin.conf", "a") as f:
        f.write(f"rpcuser={LEGACY[0]}\nrpcpassword={LEGACY[1]}\n")
    BitcoinRPC(datadir=str(node.datadir)).ask_node("getblockcount")
    assert node.requests == [("getblockcount", "__cookie__")]


def test_daily_analysis_accepts_cookie_only_configuration(node):
    from scripts.daily_analysis import _fetch_from_bitcoin_core

    node.methods["getbestblockhash"] = lambda p: "ab" * 32
    node.methods["getblock"] = lambda p: {"tx": [{"txid": str(i)} for i in range(1000)]}
    assert len(_fetch_from_bitcoin_core(str(node.datadir))) == 1000
    assert {u for _, u in node.requests} == {"__cookie__"}


def test_daily_analysis_historical_path_accepts_cookie_only_configuration(node):
    from scripts.daily_analysis import fetch_historical_transactions

    now = int(datetime.now(timezone.utc).timestamp())
    node.methods.update(
        getblockcount=lambda p: 1000,
        getblockhash=lambda p: f"{p[0]:064x}",
        getblockheader=lambda p: {"time": now - (1000 - int(p[0], 16)) * 600},
        getblock=lambda p: {"tx": [{"txid": p[0]}]},
    )
    day = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    txs = fetch_historical_transactions(day, {"BITCOIN_DATADIR": str(node.datadir)})
    assert len(txs) >= 100
    assert {u for _, u in node.requests} == {"__cookie__"}
