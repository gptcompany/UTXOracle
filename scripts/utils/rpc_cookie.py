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

Connection settings (network, datadir, host, port, cookie path, fallback) are
resolved only by :func:`resolve_target`; every UTXOracle RPC consumer goes through
it and none reads bitcoin.conf on its own.
"""

from __future__ import annotations

import base64
import configparser
import functools
import http.client
import json
import logging
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

COOKIE_USER = "__cookie__"

# chain name -> (config section, network datadir subdirectory, default RPC port);
# Bitcoin Core v28 src/chainparamsbase.cpp CreateBaseChainParams.
NETWORKS = {
    "main": ("main", "", 8332),
    "test": ("test", "testnet3", 18332),
    "testnet4": ("testnet4", "testnet4", 48332),
    "signet": ("signet", "signet", 38332),
    "regtest": ("regtest", "regtest", 18443),
}
# Boolean chain flags -> chain name (common/args.cpp GetChainArg).
CHAIN_FLAGS = {
    "regtest": "regtest",
    "signet": "signet",
    "testnet": "test",
    "testnet4": "testnet4",
}
# Options registered with ArgsManager::NETWORK_ONLY in v28 (init.cpp, bitcoin-cli.cpp,
# wallet/init.cpp): outside main they are read only from the network section.
NETWORK_ONLY = frozenset(
    {"addnode", "bind", "connect", "port", "rpcbind", "rpcport", "wallet", "walletdir"}
)
_TOP = "\x00"  # synthetic header for the options before the first [section]
_NEGATED = object()  # value of a -noX setting


class RpcHttpError(ConnectionError):
    """bitcoind answered with a non-200 status (0 = no request was sent)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class RpcAuthError(RpcHttpError):
    """No usable credential, or bitcoind rejected the one we have."""


class ConfigError(ValueError):
    """bitcoin.conf (or the connection environment) cannot be resolved safely."""


@dataclass(frozen=True)
class RpcTarget:
    """Where and how one consumer talks to bitcoind; never holds the cookie value."""

    network: str
    datadir: Path
    net_datadir: Path
    host: str
    port: int
    cookie_path: Path | None  # None: cookie disabled by -norpccookiefile
    fallback: tuple[str, str] | None = field(default=None, repr=False)


def is_encrypted_placeholder(value: str | None) -> bool:
    """True for undecrypted env placeholders from SOPS/legacy secrets."""
    return value is not None and value.startswith(("ENC[", "encrypted:"))


def clean_env_value(value: str | None) -> str | None:
    """Drop empty or encrypted-placeholder environment values."""
    if not value or is_encrypted_placeholder(value):
        return None
    return value


def default_datadir() -> Path:
    """Bitcoin Core's default data directory for this platform (common/args.cpp)."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Bitcoin"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", "")) / "Bitcoin"
    return Path.home() / ".bitcoin"


class _Assignments(dict):
    """configparser ``dict_type`` that logs every option assignment in file order.

    configparser stores ``option -> [value]`` and silently overwrites repeats
    (strict=False), while bitcoin.conf repeats options on purpose (rpcauth=, and
    Core reads the first rpcport=). The shared log keeps what configparser drops.
    """

    def __init__(self, log: list):
        super().__init__()
        self.section = None
        self._log = log

    def __setitem__(self, key, value):
        if isinstance(value, _Assignments):
            value.section = key  # configparser registering a [section]
        elif isinstance(value, list):
            self._log.append((self, key, value))  # one `key=value` line
        super().__setitem__(key, value)


def _interpret_bool(value: str) -> bool:
    """Core InterpretBool: empty is true, otherwise the leading integer is != 0."""
    digits = value.lstrip("+-")
    digits = digits[: len(digits) - len(digits.lstrip("0123456789"))]
    return value == "" or (bool(digits) and int(digits) != 0)


def parse_conf(path: Path) -> dict[str, dict[str, list]]:
    """Read bitcoin.conf as ``{section: {name: [value | _NEGATED, ...]}}``.

    The grammar is Bitcoin Core v28 common/config.cpp GetConfigOptions plus
    common/args.cpp InterpretKey/InterpretValue. Reuse: configparser (stdlib) does
    the line grammar with a synthetic header for the top section, ``=`` as the only
    delimiter, ``#`` comments, no interpolation and case kept; the token rules
    configparser does not share with Core are enforced on the parsed fields: ``#``
    truncates a value (and is rejected in rpcpassword lines, keys and sections), a
    leading ``-`` is rejected, and an indented continuation line, which Core would
    read as a separate option, is an error. Section values are keyed as Core flattens
    them: ``[regtest]`` + ``rpcport=`` and ``regtest.rpcport=`` are the same setting.
    A missing file is an empty configuration, as in Core.

    No maintained library implements these rules: python-bitcoinlib 0.12.2 (2023)
    reads bitcoin.conf as flat key=value with the last value winning and no sections,
    and python-bitcoinrpc/bitcoinlib do not read the network sections either.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"{path}: not readable ({exc.strerror})") from None
    log: list = []
    parser = configparser.ConfigParser(
        dict_type=functools.partial(_Assignments, log),
        delimiters=("=",),
        comment_prefixes=("#",),
        inline_comment_prefixes=None,
        strict=False,
        empty_lines_in_values=False,
        interpolation=None,
        default_section="\x01",
    )
    parser.optionxform = str  # option names are case-sensitive in Core
    try:
        parser.read_string(f"[{_TOP}]\n{text}", source=str(path))
    except configparser.Error as exc:
        # Line numbers only: a malformed line can be a credential.
        lines = [n - 1 for n, _ in getattr(exc, "errors", [])] or ["?"]
        raise ConfigError(f"{path}: parse error on line {lines[0]}") from None

    settings: dict[str, dict[str, list]] = {}
    for section_dict, key, lines in log:
        if len(lines) > 1:
            raise ConfigError(
                f"{path}: indented continuation of {key!r} is unsupported"
            )
        section = section_dict.section
        name = key if section == _TOP else f"{section}.{key}"
        value = lines[0]
        if "#" in name or key.startswith("-") or not key:
            raise ConfigError(f"{path}: invalid option name {name!r}")
        if "#" in value:
            if "rpcpassword" in name:
                raise ConfigError(f"{path}: '#' in rpcpassword is ambiguous")
            value = value.partition("#")[0].strip()
        section, _, name = name.partition(".") if "." in name else ("", "", name)
        if name.startswith("no"):  # -noX; a double negative -noX=0 sets X
            name = name[2:]
            value = _NEGATED if _interpret_bool(value) else "1"
        settings.setdefault(section, {}).setdefault(name, []).append(value)
    return settings


def _setting(settings: dict, section: str, name: str, *, chain_flag: bool = False):
    """common/settings.cpp GetSetting over the two config-file sources.

    The active network section is read before the default one, and NETWORK_ONLY
    options skip the default section outside main (a negation there still applies).
    Config files reverse the usual precedence: the first value after the last
    negation wins, except for chain flags, where the last one does.
    Returns None when unset and ``_NEGATED`` for a trailing ``-noX``.
    """
    for source in (section, "") if section else ("",):
        values = settings.get(source, {}).get(name)
        if not values:
            continue
        ignored = source == "" and section != "main" and name in NETWORK_ONLY
        if ignored and values[-1] is not _NEGATED:
            continue
        if values[-1] is _NEGATED:
            return _NEGATED
        last_negation = max(
            (i for i, value in enumerate(values) if value is _NEGATED), default=-1
        )
        span = values[last_negation + 1 :]
        return span[-1] if chain_flag else span[0]
    return None


def _network(settings: dict) -> str:
    """common/args.cpp GetChainArg: at most one of -chain and the chain flags."""
    chosen = []
    for flag, chain in CHAIN_FLAGS.items():
        value = _setting(settings, "", flag, chain_flag=True)
        if value not in (None, _NEGATED) and _interpret_bool(value):
            chosen.append(chain)
    chain = _setting(settings, "", "chain")
    if chain is not None:
        chosen.append("0" if chain is _NEGATED else chain)
    if len(chosen) > 1:
        raise ConfigError(
            "Invalid combination of -regtest, -signet, -testnet, -testnet4 and -chain"
        )
    network = chosen[0] if chosen else "main"
    if network not in NETWORKS:
        raise ConfigError(f"unknown chain {network!r}")
    return network


def _port(option: str, value: str) -> int:
    """Core ToIntegral<uint16_t>: plain decimal digits, 1-65535."""
    if value.isascii() and value.isdigit() and 0 < int(value) < 65536:
        return int(value)
    raise ConfigError(f"Invalid port provided in -{option}: {value!r}")


def _split_host_port(value: str) -> tuple[str, int | None]:
    """Core SplitHostPort: ``host``, ``host:port``, ``[v6]:port``; bare IPv6 has no port."""
    host, port = value, None
    colon = value.rfind(":")
    bracketed = colon > 0 and value[0] == "[" and value[colon - 1] == "]"
    multi_colon = colon > 0 and ":" in value[:colon]
    if colon != -1 and (colon == 0 or bracketed or not multi_colon):
        host, port = value[:colon], _port("rpcconnect", value[colon + 1 :])
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, port


def resolve_target(
    datadir: str | Path | None = None, env: Mapping[str, str] | None = None
) -> RpcTarget:
    """Resolve one consumer's connection to bitcoind with Bitcoin Core semantics.

    This is the only place that defines the precedence (the runbook points here):

    1. datadir: the ``datadir`` argument, else ``BITCOIN_DATADIR``, else ``datadir=``
       from ``<default datadir>/bitcoin.conf``, else the platform default. The first
       two act like ``-datadir``: bitcoin.conf is read from that directory and its
       own ``datadir=`` is ignored.
    2. network: ``chain=``/``regtest=``/``signet=``/``testnet=``/``testnet4=`` in the
       default section; main when none is set.
    3. host and port: ``BITCOIN_RPC_URL`` (its host, and its port when it has one),
       else ``rpcconnect=`` (``host[:port]``) and ``rpcport=`` (wins over the
       rpcconnect port), else 127.0.0.1 and the network's default port.
    4. cookie: ``rpccookiefile=``, relative to the network datadir (``regtest/``,
       ``testnet3/``, ...), else ``<network datadir>/.cookie``; ``norpccookiefile``
       disables it.
    5. fallback user and password, each on its own: ``BITCOIN_RPC_USER`` /
       ``BITCOIN_RPC_PASSWORD``, else ``rpcuser=``/``rpcpassword=``, else the userinfo
       of ``BITCOIN_RPC_URL``. Used only when the cookie is missing or rejected.

    bitcoin.conf values come from the active network section (``[regtest]`` or
    ``regtest.key=``) before the default section, NETWORK_ONLY options from the
    default section only on main, and the first assignment wins. ``includeconf=`` and
    ``conf=`` raise ConfigError rather than being ignored. Empty or undecrypted
    (``ENC[``) environment values count as unset.
    """
    env = os.environ if env is None else env
    explicit = datadir or clean_env_value(env.get("BITCOIN_DATADIR"))
    base = Path(explicit).expanduser() if explicit else default_datadir()
    conf_path = base / "bitcoin.conf"
    settings = parse_conf(conf_path)
    for name in ("includeconf", "conf"):
        if any(name in options for options in settings.values()):
            raise ConfigError(f"{conf_path}: {name}= is not supported")
    network = _network(settings)
    section, subdir, default_port = NETWORKS[network]

    def text(name: str) -> str | None:
        value = _setting(settings, section, name)
        return None if value is _NEGATED or not value else value

    if not explicit and text("datadir"):
        base = Path(text("datadir")).absolute()
    net_datadir = base / subdir
    cookie = _setting(settings, section, "rpccookiefile")
    cookie_path = None if cookie is _NEGATED else net_datadir / (cookie or ".cookie")

    host, port = "127.0.0.1", default_port
    if text("rpcconnect"):
        host, connect_port = _split_host_port(text("rpcconnect"))
        port = connect_port or port
    rpcport = _setting(settings, section, "rpcport")
    if rpcport is not None:
        port = _port("rpcport", "0" if rpcport is _NEGATED else rpcport)

    url_user = url_password = None
    url = clean_env_value(env.get("BITCOIN_RPC_URL"))
    if url:
        try:
            parts = urlsplit(url if "://" in url else f"http://{url}")
            url_port = parts.port
            if not parts.hostname:
                raise ValueError("no host")
        except ValueError:
            # Never log the value: it may embed a password.
            logger.warning("BITCOIN_RPC_URL is unparseable; using bitcoin.conf")
        else:
            host, port = parts.hostname, url_port or port
            url_user, url_password = parts.username, parts.password

    user = clean_env_value(env.get("BITCOIN_RPC_USER")) or text("rpcuser") or url_user
    password = (
        clean_env_value(env.get("BITCOIN_RPC_PASSWORD"))
        or text("rpcpassword")
        or url_password
    )
    target = RpcTarget(
        network=network,
        datadir=base,
        net_datadir=net_datadir,
        host=host,
        port=port,
        cookie_path=cookie_path,
        fallback=(user, password) if user and password else None,
    )
    logger.info(
        "RPC target: network=%s host=%s port=%d cookie=%s conf=%s fallback=%s",
        network,
        host,
        port,
        cookie_path,
        conf_path if settings else "none",
        target.fallback is not None,
    )
    return target


def read_cookie(datadir: str | Path | None = None, conf: RpcTarget | None = None):
    """Return ``(user, password)`` from the cookie file, or None if absent/malformed.

    ``conf`` is a resolved target; without it the target of ``datadir`` is resolved.
    """
    path = (resolve_target(datadir) if conf is None else conf).cookie_path
    if path is None:
        logger.debug("RPC cookie disabled by norpccookiefile")
        return None
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
    """JSON-RPC over HTTP; cookie first, optional user/password fallback.

    Every connection setting comes from :func:`resolve_target`.
    """

    def __init__(
        self,
        datadir: str | Path | None = None,
        *,
        timeout: float = 60,
        request_id: str = "utxoracle",
    ):
        self.target = resolve_target(datadir)
        self._conf = self.target  # read_cookie(self.datadir, self._conf) re-reads it
        self.datadir = self.target.datadir
        self.host = self.target.host
        self.port = self.target.port
        self._fallback = self.target.fallback
        self._timeout = timeout
        self._id = request_id
        self._cookie = read_cookie(self.datadir, self._conf)

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
