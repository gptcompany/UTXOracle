"""R5-M2: one resolver for the bitcoind connection, with Bitcoin Core semantics.

Every case writes a real bitcoin.conf and resolves it with an explicit, empty
environment unless the case is about the environment. Values follow Bitcoin Core
v28 (common/config.cpp, common/args.cpp, common/settings.cpp, chainparamsbase.cpp).
Dummy credentials only. Imports are lazy so the module also runs on the pre-fix head.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from tests.fake_bitcoind import load_live_rpc

REPO = Path(__file__).resolve().parent.parent


def resolve(datadir, text=None, env=None):
    from scripts.utils.rpc_cookie import resolve_target

    if text is not None:
        (Path(datadir) / "bitcoin.conf").write_text(text)
    return resolve_target(datadir, env={} if env is None else env)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """No RPC variable from the developer shell, and an empty HOME."""
    for var in (
        "BITCOIN_DATADIR",
        "BITCOIN_RPC_URL",
        "BITCOIN_RPC_USER",
        "BITCOIN_RPC_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


# --- R5-M2 scenario ----------------------------------------------------------------

R5_CONF = "rpcport=8332\nserver=1\n[regtest]\nrpcport=18443\n"


def test_inactive_regtest_section_does_not_change_the_mainnet_port(tmp_path):
    target = resolve(tmp_path, R5_CONF)
    assert (target.network, target.port) == ("main", 8332)
    assert target.cookie_path == tmp_path / ".cookie"


def test_r5_conf_keeps_the_mainnet_port_in_client_and_live(tmp_path, clean_env):
    from scripts.utils.rpc_cookie import RpcClient

    (tmp_path / "bitcoin.conf").write_text(R5_CONF)
    assert RpcClient(tmp_path).port == 8332
    assert load_live_rpc()(datadir=str(tmp_path)).rpc_port == 8332


def test_every_consumer_reads_the_mainnet_port_of_the_r5_conf(
    tmp_path, clean_env, monkeypatch
):
    from scripts import daily_analysis, sync_utxo_lifecycle

    (tmp_path / "bitcoin.conf").write_text(R5_CONF)
    (tmp_path / ".cookie").write_text("__cookie__:DUMMYCOOKIE0001")
    live = load_live_rpc()(datadir=str(tmp_path))
    daily = daily_analysis.rpc_client({"BITCOIN_DATADIR": str(tmp_path)})
    monkeypatch.setenv("BITCOIN_DATADIR", str(tmp_path))
    sync = sync_utxo_lifecycle.BitcoinRPC()
    assert (live.rpc_port, daily.port, sync.port) == (8332, 8332, 8332)


# --- active network section --------------------------------------------------------


@pytest.mark.parametrize("selector", ["regtest=1", "chain=regtest"])
def test_active_section_wins_over_the_default_section(tmp_path, selector):
    target = resolve(
        tmp_path,
        f"{selector}\nrpcconnect=10.0.0.1\nrpcuser=top\nrpcpassword=DUMMYTOP\n"
        "[test]\nrpcconnect=10.0.0.3\n[regtest]\nrpcconnect=127.0.0.2\nrpcport=18444\n",
    )
    assert target.network == "regtest"
    assert (target.host, target.port) == ("127.0.0.2", 18444)
    assert target.fallback == ("top", "DUMMYTOP"), "not network-only: default applies"


def test_section_prefix_is_the_same_setting_as_the_section(tmp_path):
    target = resolve(tmp_path, "regtest=1\nregtest.rpcport=18999\ntest.rpcport=1\n")
    assert target.port == 18999


@pytest.mark.parametrize(
    ("flag", "network", "subdir", "port"),
    [
        ("testnet=1", "test", "testnet3", 18332),
        ("testnet4=1", "testnet4", "testnet4", 48332),
        ("signet=1", "signet", "signet", 38332),
        ("regtest=1", "regtest", "regtest", 18443),
        ("", "main", "", 8332),
    ],
)
def test_network_selects_subdirectory_cookie_and_default_port(
    tmp_path, flag, network, subdir, port
):
    target = resolve(tmp_path, f"{flag}\n")
    assert (target.network, target.port) == (network, port)
    assert target.net_datadir == tmp_path / subdir
    assert target.cookie_path == tmp_path / subdir / ".cookie"


def test_chain_flags_take_the_last_value_and_chain_the_first(tmp_path):
    assert resolve(tmp_path, "regtest=1\nregtest=0\n").network == "main"
    assert resolve(tmp_path, "chain=signet\nchain=regtest\n").network == "signet"


def test_two_networks_are_an_error(tmp_path):
    from scripts.utils.rpc_cookie import ConfigError

    with pytest.raises(ConfigError, match="Invalid combination"):
        resolve(tmp_path, "regtest=1\ntestnet4=1\n")
    with pytest.raises(ConfigError, match="unknown chain"):
        resolve(tmp_path, "chain=mainnet\n")


def test_chain_flags_inside_a_section_do_not_select_the_network(tmp_path):
    assert resolve(tmp_path, "[regtest]\nregtest=1\n").network == "main"


# --- network-only options ------------------------------------------------------------


def test_network_only_option_in_default_section_is_ignored_outside_main(tmp_path):
    target = resolve(tmp_path, "regtest=1\nrpcport=1111\nrpcconnect=127.0.0.9\n")
    assert target.port == 18443, "rpcport is NETWORK_ONLY"
    assert target.host == "127.0.0.9", "rpcconnect is not"


def test_network_only_option_in_default_section_applies_on_main(tmp_path):
    assert resolve(tmp_path, "rpcport=1111\n[main]\nrpcbind=x\n").port == 1111


def test_main_section_wins_on_main(tmp_path):
    assert resolve(tmp_path, "rpcport=1111\n[main]\nrpcport=2222\n").port == 2222


def test_network_only_set_matches_bitcoin_core_v28():
    from scripts.utils.rpc_cookie import NETWORK_ONLY

    # AddArg(... ArgsManager::NETWORK_ONLY ...) in init.cpp, bitcoin-cli.cpp, wallet/init.cpp
    assert NETWORK_ONLY == {
        "addnode",
        "bind",
        "connect",
        "port",
        "rpcbind",
        "rpcport",
        "wallet",
        "walletdir",
    }


# --- first value wins ----------------------------------------------------------------


def test_first_assignment_wins_in_each_section(tmp_path):
    target = resolve(
        tmp_path, "rpcport=1001\nrpcport=1002\n[main]\nrpcconnect=a\nrpcconnect=b\n"
    )
    assert (target.port, target.host) == (1001, "a")


def test_first_wins_across_prefix_and_section_in_file_order(tmp_path):
    # A prefix can only precede a section header: after one, keys belong to it.
    text = "regtest=1\nregtest.rpcport=5001\n[regtest]\nrpcport=5002\n"
    assert resolve(tmp_path, text).port == 5001


def test_repeated_options_are_all_kept_in_order(tmp_path):
    from scripts.utils.rpc_cookie import parse_conf

    (tmp_path / "bitcoin.conf").write_text("rpcauth=a:1\nrpcauth=b:2\nrpcauth=c:3\n")
    assert parse_conf(tmp_path / "bitcoin.conf")[""]["rpcauth"] == [
        "a:1",
        "b:2",
        "c:3",
    ]


def test_negation_resets_earlier_values(tmp_path):
    from scripts.utils.rpc_cookie import ConfigError

    assert resolve(tmp_path, "rpcconnect=a\nnorpcconnect=1\nrpcconnect=b\n").host == "b"
    with pytest.raises(ConfigError, match="rpcport"):
        resolve(tmp_path, "rpcport=1\nnorpcport=1\n")


# --- cookie ----------------------------------------------------------------------------


def test_relative_rpccookiefile_is_under_the_network_datadir(tmp_path):
    target = resolve(tmp_path, "regtest=1\nrpccookiefile=auth/my.cookie\n")
    assert target.cookie_path == tmp_path / "regtest" / "auth" / "my.cookie"


def test_absolute_rpccookiefile_is_kept(tmp_path):
    other = tmp_path / "elsewhere.cookie"
    assert resolve(tmp_path, f"rpccookiefile={other}\n").cookie_path == other


def test_rpccookiefile_of_an_inactive_section_is_ignored(tmp_path):
    target = resolve(tmp_path, "[test]\nrpccookiefile=/wrong\n")
    assert target.cookie_path == tmp_path / ".cookie"


def test_norpccookiefile_disables_the_cookie_and_keeps_the_fallback(tmp_path):
    from scripts.utils.rpc_cookie import RpcClient

    (tmp_path / ".cookie").write_text("__cookie__:DUMMYCOOKIE0001")
    text = "norpccookiefile=1\nrpcuser=u\nrpcpassword=DUMMYPASS\n"
    assert resolve(tmp_path, text).cookie_path is None
    client = RpcClient(tmp_path)
    assert client._cookie is None and client._fallback == ("u", "DUMMYPASS")


def test_regtest_cookie_is_read_from_the_network_subdirectory(tmp_path, clean_env):
    from scripts.utils.rpc_cookie import RpcClient

    (tmp_path / "regtest").mkdir()
    (tmp_path / "regtest" / ".cookie").write_text("__cookie__:DUMMYCOOKIE0001")
    (tmp_path / ".cookie").write_text("__cookie__:DUMMYMAINNET")
    (tmp_path / "bitcoin.conf").write_text("regtest=1\n")
    assert RpcClient(tmp_path)._cookie == ("__cookie__", "DUMMYCOOKIE0001")


# --- unsupported directives and grammar ------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["includeconf=extra.conf\n", "[regtest]\nincludeconf=extra.conf\n", "conf=x\n"],
)
def test_include_and_conf_directives_are_explicit_errors(tmp_path, text):
    from scripts.utils.rpc_cookie import ConfigError

    with pytest.raises(ConfigError, match="not supported"):
        resolve(tmp_path, text)


def test_hash_starts_a_comment_anywhere(tmp_path):
    assert resolve(tmp_path, "# c\nrpcport=1234 # c\n").port == 1234
    assert resolve(tmp_path, "rpcport=1235#c\n").port == 1235


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("rpcpassword=DUMMY#PASS\n", "rpcpassword"),
        ("-rpcport=1\n", "invalid option"),
        ("[regtest]\n-rpcport=1\n", "invalid option"),
        ("rpcpassword DUMMYSECRET\n", "parse error on line 1"),
        ("rpcport=1\n  rpcbind=2\n", "continuation"),
        ("rpcport=abc\n", "Invalid port"),
        ("rpcconnect=host:0\n", "Invalid port"),
    ],
)
def test_malformed_conf_is_an_error_that_never_echoes_values(tmp_path, text, match):
    from scripts.utils.rpc_cookie import ConfigError

    with pytest.raises(ConfigError, match=match) as exc:
        resolve(tmp_path, text)
    assert "DUMMY" not in str(exc.value)


def test_option_names_are_case_sensitive(tmp_path):
    assert resolve(tmp_path, "RPCPORT=1111\n").port == 8332


def test_missing_conf_is_an_empty_configuration(tmp_path):
    target = resolve(tmp_path)
    assert (target.network, target.host, target.port) == ("main", "127.0.0.1", 8332)


@pytest.mark.parametrize(
    ("text", "host", "port"),
    [
        ("rpcconnect=10.1.1.1:9999\n", "10.1.1.1", 9999),
        ("rpcconnect=10.1.1.1:9999\nrpcport=7777\n", "10.1.1.1", 7777),
        ("rpcconnect=[::1]:9998\n", "::1", 9998),
        ("rpcconnect=::1\n", "::1", 8332),
    ],
)
def test_rpcconnect_host_and_port_like_bitcoin_cli(tmp_path, text, host, port):
    target = resolve(tmp_path, text)
    assert (target.host, target.port) == (host, port)


# --- datadir and environment precedence --------------------------------------------------


def test_datadir_argument_wins_over_environment(tmp_path):
    arg, envdir = tmp_path / "arg", tmp_path / "env"
    arg.mkdir(), envdir.mkdir()
    target = resolve(arg, env={"BITCOIN_DATADIR": str(envdir)})
    assert target.datadir == arg


def test_bitcoin_datadir_selects_the_conf_and_ignores_its_datadir_line(tmp_path):
    (tmp_path / "bitcoin.conf").write_text("datadir=/elsewhere\nrpcport=4444\n")
    target = resolve(None, env={"BITCOIN_DATADIR": str(tmp_path)})
    assert (target.datadir, target.port) == (tmp_path, 4444)


def test_default_conf_datadir_line_moves_the_cookie(tmp_path, clean_env):
    node = tmp_path / "node"
    (clean_env / ".bitcoin").mkdir()
    (clean_env / ".bitcoin" / "bitcoin.conf").write_text(f"datadir={node}\n")
    target = resolve(None, env={"BITCOIN_DATADIR": "ENC[AES256_GCM,data:x]"})
    assert target.datadir == node and target.cookie_path == node / ".cookie"


def test_rpc_url_overrides_host_and_port_and_keeps_conf_port_without_one(tmp_path):
    (tmp_path / "bitcoin.conf").write_text("rpcport=4444\n")
    with_port = resolve(tmp_path, env={"BITCOIN_RPC_URL": "http://10.2.2.2:5555"})
    without = resolve(tmp_path, env={"BITCOIN_RPC_URL": "10.2.2.3"})
    assert (with_port.host, with_port.port) == ("10.2.2.2", 5555)
    assert (without.host, without.port) == ("10.2.2.3", 4444)


def test_unparseable_rpc_url_is_ignored_without_logging_it(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    target = resolve(tmp_path, env={"BITCOIN_RPC_URL": "http://u:DUMMYPW@[bad/"})
    assert (target.host, target.port) == ("127.0.0.1", 8332)
    assert "unparseable" in caplog.text and "DUMMYPW" not in caplog.text


def test_fallback_precedence_per_field_env_then_conf_then_url(tmp_path):
    (tmp_path / "bitcoin.conf").write_text("rpcuser=confuser\nrpcpassword=DUMMYCONF\n")
    env = {
        "BITCOIN_RPC_USER": "envuser",
        "BITCOIN_RPC_URL": "http://urluser:DUMMYURL@127.0.0.1:1",
    }
    assert resolve(tmp_path, env=env).fallback == ("envuser", "DUMMYCONF")
    (tmp_path / "bitcoin.conf").write_text("")
    assert resolve(tmp_path, env=env).fallback == ("envuser", "DUMMYURL")


def test_fallback_never_appears_in_repr_or_log(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    target = resolve(tmp_path, "rpcuser=u\nrpcpassword=DUMMYPASS\n")
    assert target.fallback == ("u", "DUMMYPASS")
    assert "DUMMYPASS" not in repr(target) + caplog.text


# --- single resolver ----------------------------------------------------------------------

CONSUMER_SOURCES = [
    "live/backend/bitcoin_rpc.py",
    "live/backend/baseline_calculator.py",
    "scripts/sync_utxo_lifecycle.py",
    "scripts/daily_analysis.py",
]


@pytest.mark.parametrize("source", CONSUMER_SOURCES)
def test_no_consumer_resolves_conf_datadir_or_cookie_itself(source):
    tree = ast.parse((REPO / source).read_text(encoding="utf-8"))
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    owned = {"bitcoin.conf", ".cookie", "~/.bitcoin", "rpcport", "rpcconnect"}
    assert not owned & strings, f"{source} resolves the connection on its own"


def test_all_consumers_go_through_resolve_target(tmp_path, clean_env, monkeypatch):
    from scripts import daily_analysis, sync_utxo_lifecycle
    from scripts.utils import rpc_cookie

    calls = []
    real = rpc_cookie.resolve_target

    def spy(datadir=None, env=None):
        calls.append(datadir)
        return real(datadir, env)

    monkeypatch.setattr(rpc_cookie, "resolve_target", spy)
    (tmp_path / ".cookie").write_text("__cookie__:DUMMYCOOKIE0001")
    monkeypatch.setenv("BITCOIN_DATADIR", str(tmp_path))
    load_live_rpc()()
    sync_utxo_lifecycle.BitcoinRPC()
    daily_analysis.rpc_client({"BITCOIN_DATADIR": None})
    assert calls == [None, None, None]
