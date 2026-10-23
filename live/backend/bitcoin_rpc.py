"""
Handles RPC communication with the Bitcoin Core node.
"""

import logging

from scripts.utils.rpc_cookie import RpcClient

logger = logging.getLogger("live.rpc")


class BitcoinRPC:
    def __init__(self, datadir: str = None):
        # Datadir, network, host, port and cookie come from the shared resolver
        # (scripts.utils.rpc_cookie.resolve_target); this wrapper reads no config.
        self._client = RpcClient(datadir, timeout=30, request_id="utxoracle-live")
        target = self._client.target
        self.data_dir = str(target.datadir)
        self.cookie_path = target.cookie_path
        self.rpc_host = target.host
        self.rpc_port = target.port

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
