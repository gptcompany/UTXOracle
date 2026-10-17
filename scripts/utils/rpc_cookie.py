"""Bitcoin Core RPC client with cookie authentication.

Cookie format (Bitcoin Core ``GenerateAuthCookie``): a single line
``__cookie__:<random hex>`` in ``<datadir>/.cookie`` (or ``-rpccookiefile``),
regenerated at every bitcoind start. A long-lived client therefore re-reads the
file once on HTTP 401 and retries once. The cookie wins over rpcuser/rpcpassword;
those stay as a fallback only because the coordinated rollback of
docs/BRK_COOKIE_MIGRATION_RUNBOOK.md reinstates them in bitcoin.conf.

Why not python-bitcoinlib: it reads the cookie once in ``Proxy.__init__`` and has
no 401 re-read, so it would not survive a bitcoind restart. Credential values are
never logged or placed in exception messages.
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

COOKIE_USER = "__cookie__"


class RpcHttpError(ConnectionError):
    """bitcoind answered with a non-200 status (0 = no request was sent)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class RpcAuthError(RpcHttpError):
    """No usable credential, or bitcoind rejected the one we have."""


def load_conf(datadir: str | Path) -> dict[str, str]:
    """Read key=value pairs from ``<datadir>/bitcoin.conf`` (missing file -> {})."""
    path = Path(datadir) / "bitcoin.conf"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith(("#", "[")) and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def read_cookie(datadir: str | Path, conf: dict[str, str] | None = None):
    """Return ``(user, password)`` from the cookie file, or None if absent/malformed."""
    conf = load_conf(datadir) if conf is None else conf
    path = Path(datadir) / conf.get(
        "rpccookiefile", ".cookie"
    )  # absolute stays absolute
    try:
        user, sep, password = path.read_text().strip().partition(":")
    except OSError as exc:
        logger.debug("RPC cookie not readable at %s: %s", path, exc.strerror)
        return None
    if not sep or user != COOKIE_USER or not password:
        logger.warning("RPC cookie at %s is malformed", path)
        return None
    return user, password


class RpcClient:
    """JSON-RPC over HTTP; cookie first, optional user/password fallback."""

    def __init__(
        self,
        datadir: str | Path,
        *,
        host: str | None = None,
        port: int | None = None,
        fallback: tuple[str, str] | None = None,
        timeout: float = 60,
        request_id: str = "utxoracle",
    ):
        self.datadir = Path(datadir)
        conf = load_conf(self.datadir)
        self._conf = conf
        self.host = host or conf.get("rpcconnect", "127.0.0.1")
        self.port = port or int(conf.get("rpcport", "8332"))
        if fallback is None and conf.get("rpcuser") and conf.get("rpcpassword"):
            fallback = (conf["rpcuser"], conf["rpcpassword"])
        self._fallback = fallback
        self._timeout = timeout
        self._id = request_id
        self._cookie = read_cookie(self.datadir, conf)

    def _credentials(self) -> tuple[str, str]:
        if self._cookie:
            return self._cookie
        if self._fallback:
            return self._fallback
        raise RpcAuthError(
            f"no RPC credential: cookie missing or malformed under {self.datadir}"
            " and no rpcuser/rpcpassword fallback"
        )

    def _post(self, payload: str) -> tuple[int, bytes]:
        user, password = self._credentials()
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self._timeout)
        try:
            conn.request(
                "POST",
                "/",
                payload,
                {"Content-Type": "application/json", "Authorization": f"Basic {token}"},
            )
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def call(self, method: str, params: list | None = None) -> Any:
        payload = json.dumps(
            {"jsonrpc": "1.0", "id": self._id, "method": method, "params": params or []}
        )
        status, body = self._post(payload)
        if status == 401:
            # bitcoind regenerates the cookie at each restart, and a client started
            # before the migration only has the legacy password: re-read the cookie
            # once and retry once.
            self._cookie = read_cookie(self.datadir, self._conf)
            logger.info(
                "RPC %s: HTTP 401, cookie re-read (found=%s)",
                method,
                bool(self._cookie),
            )
            if self._cookie:
                status, body = self._post(payload)
        if status == 401:
            raise RpcAuthError(f"RPC {method}: HTTP 401 Unauthorized", 401)
        if status != 200:
            raise RpcHttpError(f"RPC {method}: HTTP {status}", status)
        data = json.loads(body)
        if data.get("error"):
            raise ConnectionError(f"RPC {method} failed: {data['error']}")
        return data["result"]


def main(argv: list[str] | None = None) -> int:
    """Runbook check: ``python -m scripts.utils.rpc_cookie <label> <datadir>``.

    Prints only the label, the outcome and the HTTP code, never a value.
    """
    import sys

    label, datadir = (argv if argv is not None else sys.argv[1:])[:2]
    try:
        RpcClient(datadir, timeout=10).call("getblockcount")
    except RpcHttpError as exc:
        print(f"{label}: FAIL HTTP {exc.status:03d}")
        return 1
    except OSError:
        print(f"{label}: FAIL HTTP 000")
        return 1
    print(f"{label}: OK HTTP 200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
