"""Configuration regressions for UTXO lifecycle sync."""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.usefixtures("hermetic_rpc")


def test_encrypted_log_level_falls_back_to_info():
    """SOPS placeholder values must not crash logging.basicConfig."""
    from scripts import sync_utxo_lifecycle

    assert (
        sync_utxo_lifecycle._resolve_log_level("ENC[AES256_GCM,data:x]") is logging.INFO
    )


def test_encrypted_env_value_is_ignored():
    from scripts.utils.rpc_cookie import clean_env_value

    assert clean_env_value("ENC[AES256_GCM,data:x]") is None
    assert clean_env_value("encrypted:legacy") is None
    assert clean_env_value("http://127.0.0.1:8332") == ("http://127.0.0.1:8332")


def test_bitcoin_rpc_uses_credentials_from_bitcoin_conf(monkeypatch, tmp_path):
    from scripts import sync_utxo_lifecycle

    # No cookie in the datadir: user/password are the documented fallback.
    monkeypatch.setenv("BITCOIN_DATADIR", str(tmp_path))
    monkeypatch.delenv("BITCOIN_RPC_URL", raising=False)
    monkeypatch.delenv("BITCOIN_RPC_USER", raising=False)
    monkeypatch.delenv("BITCOIN_RPC_PASSWORD", raising=False)
    (tmp_path / "bitcoin.conf").write_text(
        "rpcuser=conf-user\nrpcpassword=conf-pass\nrpcport=18443\n"
    )

    rpc = sync_utxo_lifecycle.BitcoinRPC()

    assert rpc.host == "127.0.0.1"
    assert rpc.port == 18443
    assert rpc.rpc_user == "conf-user"
    assert rpc.rpc_pass == "conf-pass"
