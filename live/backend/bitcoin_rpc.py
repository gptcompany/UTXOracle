"""
Handles RPC communication with the Bitcoin Core node.
"""

import os
import platform
import logging

from scripts.utils.rpc_cookie import RpcClient

logger = logging.getLogger("live.rpc")


class BitcoinRPC:
    def __init__(self, datadir: str = None):
        self.data_dir = datadir or self._get_default_datadir()
        self.rpc_user = None
        self.rpc_password = None
        self.cookie_path = None
        self.rpc_host = "127.0.0.1"
        self.rpc_port = 8332
        self._load_config()

    def _get_default_datadir(self):
        system = platform.system()
        if system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Bitcoin")
        elif system == "Windows":
            return os.path.join(os.environ.get("APPDATA", ""), "Bitcoin")
        else:
            return os.path.expanduser("~/.bitcoin")

    def _load_config(self):
        conf_path = os.path.join(self.data_dir, "bitcoin.conf")
        if not os.path.exists(conf_path):
            logger.warning(
                f"bitcoin.conf not found at {conf_path}. Relying on .cookie file."
            )
        else:
            conf_settings = {}
            with open(conf_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        conf_settings[key.strip()] = value.strip().strip('"')

            self.rpc_user = conf_settings.get("rpcuser")
            self.rpc_password = conf_settings.get("rpcpassword")
            self.rpc_host = conf_settings.get("rpcconnect", "127.0.0.1")
            self.rpc_port = int(conf_settings.get("rpcport", "8332"))

        self.cookie_path = os.path.join(self.data_dir, ".cookie")
        # rpcuser/rpcpassword from bitcoin.conf are only the fallback; the cookie wins.
        fallback = (
            (self.rpc_user, self.rpc_password)
            if self.rpc_user and self.rpc_password
            else None
        )
        self._client = RpcClient(
            self.data_dir,
            host=self.rpc_host,
            port=self.rpc_port,
            fallback=fallback,
            timeout=30,
            request_id="utxoracle-live",
        )

    def ask_node(self, method: str, params: list = None):
        """Send a JSON-RPC request; the cookie wins and is re-read once on HTTP 401.

        Based on Ask_Node from UTXOracle.py (lines 233-295).
        """
        try:
            return self._client.call(method, params)
        except ConnectionRefusedError:
            logger.error(f"RPC connection to {self.rpc_host}:{self.rpc_port} refused.")
            raise ConnectionError(
                "Connection refused. Is bitcoind running with -server=1?"
            )
        except Exception as e:
            logger.error(f"RPC call '{method}' failed: {e}")
            raise
