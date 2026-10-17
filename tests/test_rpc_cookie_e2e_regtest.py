"""E2E: consumers against a real bitcoind (regtest) that has no rpcuser/rpcpassword.

bitcoind rewrites the cookie at every start, so the long-lived clients below must
survive a restart through the 401 -> cookie re-read -> retry path. The daemon runs
in a temporary datadir on a private port; skipped when bitcoind is not installed.
"""

from __future__ import annotations

import hashlib
import shutil
import socket
import subprocess
import time

import pytest

from tests.fake_bitcoind import load_live_rpc

pytestmark = pytest.mark.skipif(
    not (shutil.which("bitcoind") and shutil.which("bitcoin-cli")),
    reason="bitcoind not installed",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Regtest:
    def __init__(self, datadir, port):
        self.datadir, self.port = datadir, port
        self.cookie = datadir / "cookie"
        (datadir / "bitcoin.conf").write_text(
            f"regtest=1\nserver=1\nlisten=0\ndnsseed=0\n[regtest]\nrpcport={port}\n"
            f"rpccookiefile={self.cookie}\n"
        )

    def _cli(self, *args):
        return subprocess.run(
            ["bitcoin-cli", f"-datadir={self.datadir}", *args],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def start(self):
        subprocess.run(
            ["bitcoind", f"-datadir={self.datadir}", "-daemon", "-fallbackfee=0.0002"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        for _ in range(60):
            if self._cli("getblockcount").returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("regtest bitcoind did not become ready")

    def stop(self):
        self._cli("stop")
        for _ in range(60):
            if self._cli("getblockcount").returncode != 0:
                return
            time.sleep(0.5)

    def cookie_digest(self) -> str:
        return hashlib.sha256(self.cookie.read_bytes()).hexdigest()


@pytest.fixture
def regtest(tmp_path):
    node = Regtest(tmp_path, _free_port())
    node.start()
    yield node
    node.stop()


def test_consumers_survive_a_bitcoind_restart_with_cookie_only(regtest, monkeypatch):
    LiveRPC = load_live_rpc()
    from scripts import sync_utxo_lifecycle as sync_mod

    conf = (regtest.datadir / "bitcoin.conf").read_text()
    assert "rpcuser" not in conf and "rpcpassword" not in conf

    for var in ("BITCOIN_RPC_USER", "BITCOIN_RPC_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BITCOIN_RPC_URL", f"http://127.0.0.1:{regtest.port}")
    monkeypatch.setenv("BITCOIN_DATADIR", str(regtest.datadir))
    monkeypatch.setattr(sync_mod, "_load_bitcoin_conf", lambda: {})

    sync_client = sync_mod.BitcoinRPC()
    live_client = LiveRPC(datadir=str(regtest.datadir))
    assert sync_client.getblockcount() == 0
    assert live_client.ask_node("getblockcount") == 0

    before = regtest.cookie_digest()
    regtest.stop()
    regtest.start()
    assert regtest.cookie_digest() != before, "bitcoind must issue a new cookie"

    # Same client objects, stale cookie in memory: 401 -> re-read -> success.
    assert sync_client.getblockcount() == 0
    assert live_client.ask_node("getblockcount") == 0
