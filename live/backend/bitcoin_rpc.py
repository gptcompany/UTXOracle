"""
Handles RPC communication with the Bitcoin Core node.
"""

import os
import platform
import json
import base64
import http.client
import logging

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

    def ask_node(self, method: str, params: list = None):
        """
        Sends a JSON-RPC request to the Bitcoin node.
        Based on Ask_Node from UTXOracle.py (lines 233-295).
        """
        params = params or []

        rpc_u = self.rpc_user
        rpc_p = self.rpc_password

        if not rpc_u or not rpc_p:
            try:
                with open(self.cookie_path, "r") as f:
                    cookie = f.read().strip()
                    rpc_u, rpc_p = cookie.split(":", 1)
            except Exception as e:
                logger.error(f"Error reading .cookie file for RPC auth: {e}")
                raise ConnectionError(
                    "Could not authenticate with Bitcoin Core. Check .cookie file or bitcoin.conf."
                )

        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "utxoracle-live",
                "method": method,
                "params": params,
            }
        )

        auth_header = base64.b64encode(f"{rpc_u}:{rpc_p}".encode()).decode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_header}",
        }

        try:
            conn = http.client.HTTPConnection(self.rpc_host, self.rpc_port, timeout=30)
            conn.request("POST", "/", payload, headers)
            response = conn.getresponse()

            if response.status != 200:
                raise ConnectionError(
                    f"RPC Error: HTTP {response.status} {response.reason}"
                )

            raw_data = response.read()
            conn.close()

            parsed = json.loads(raw_data)
            if parsed.get("error"):
                raise ConnectionError(f"RPC call failed: {parsed['error']}")

            return parsed["result"]

        except ConnectionRefusedError:
            logger.error(f"RPC connection to {self.rpc_host}:{self.rpc_port} refused.")
            raise ConnectionError(
                "Connection refused. Is bitcoind running with -server=1?"
            )
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during RPC call '{method}': {e}"
            )
            raise
