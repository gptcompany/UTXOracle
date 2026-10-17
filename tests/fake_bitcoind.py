"""Fake bitcoind JSON-RPC server for the RPC auth tests (dummy credentials only)."""

from __future__ import annotations

import base64
import importlib.util
import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeBitcoind:
    """Accepts one credential pair; answers 401 to everything else."""

    def __init__(self, accepted: tuple[str, str], methods: dict):
        self.accepted = accepted
        self.methods = methods
        self.force_status = 0  # answer every authenticated call with this status
        self.requests: list[tuple[str, str]] = []  # (method, auth user)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                header = self.headers.get("Authorization", "")
                user, _, pw = (
                    base64.b64decode(header.removeprefix("Basic "))
                    .decode()
                    .partition(":")
                    if header.startswith("Basic ")
                    else ("", "", "")
                )
                outer.requests.append((body["method"], user))
                if (user, pw) != outer.accepted:
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer.force_status:
                    self.send_response(outer.force_status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                method = outer.methods.get(body["method"])
                result = method(body.get("params", [])) if method else None
                error = None if method else {"code": -32601, "message": "not found"}
                data = json.dumps({"result": result, "error": error, "id": body["id"]})
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data.encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def load_live_rpc():
    """live/backend/bitcoin_rpc.BitcoinRPC by path: `live` is a namespace package that
    other test modules shadow in a full run."""
    path = (
        Path(__file__).resolve().parent.parent / "live" / "backend" / "bitcoin_rpc.py"
    )
    spec = importlib.util.spec_from_file_location("live_backend_bitcoin_rpc", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BitcoinRPC
