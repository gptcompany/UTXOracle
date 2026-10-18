"""Published ports must bind to an explicit address, never to every interface (F-236)."""

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WILDCARDS = {"", "0.0.0.0", "::", "[::]", "*"}
SUBSTITUTION = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::?-(?P<default>[^}]*))?\}")


def _compose_files() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.split(b"\0")
    return [
        ROOT / n.decode()
        for n in names
        if n and re.search(r"(^|/)(docker-)?compose[^/]*\.ya?ml$", n.decode())
    ]


def _split(spec: str) -> list[str]:
    """Split a short-syntax port on ':' outside ${...} and [...]."""
    parts, depth, current = [], 0, ""
    for char in spec:
        depth += (char in "{[") - (char in "}]")
        if char == ":" and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [*parts, current]


def _resolve(token: str) -> str | None:
    """Value of a bind address, using the ${VAR:-default} default; None when it cannot be known statically."""
    match = SUBSTITUTION.fullmatch(token)
    if match:
        return match.group("default")
    return None if "${" in token else token


def _host_ip(port) -> str | None:
    if isinstance(port, dict):
        return _resolve(str(port.get("host_ip", "")))
    parts = _split(str(port).split("/")[0])
    return _resolve(parts[0]) if len(parts) == 3 else ""


def _published(compose: Path):
    services = (yaml.safe_load(compose.read_text(encoding="utf-8")) or {}).get(
        "services"
    ) or {}
    for name, service in services.items():
        for port in service.get("ports") or []:
            if not isinstance(port, dict) or port.get("published") is not None:
                yield name, port


def test_every_published_port_binds_to_an_explicit_address():
    offenders, checked = [], 0
    for compose in _compose_files():
        for service, port in _published(compose):
            checked += 1
            if _host_ip(port) in WILDCARDS | {None}:
                offenders.append(f"{compose.name}:{service}")
    assert offenders == []
    assert checked >= 4


def test_live_api_is_published_on_loopback_only():
    live = yaml.safe_load(
        (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    )
    ports = live["services"]["utxoracle-live-api"]["ports"]
    assert [_host_ip(p) for p in ports] == ["127.0.0.1"]


def test_the_checker_rejects_wildcard_and_missing_binds():
    assert _host_ip("8011:8011") == ""
    assert _host_ip("0.0.0.0:8011:8011") == "0.0.0.0"
    assert _host_ip("[::]:8011:8011") == "[::]"
    assert _host_ip("${LIVE_API_PORT:-8011}:8011") == ""
    assert _host_ip("${BIND:-0.0.0.0}:${LIVE_API_PORT:-8011}:8011") == "0.0.0.0"
    assert _host_ip("${BIND}:8011:8011") is None
    assert _host_ip("127.0.0.1:${LIVE_API_PORT:-8011}:8011") == "127.0.0.1"
    assert _host_ip({"target": 8011, "published": 8011}) == ""
    assert (
        _host_ip({"target": 8011, "published": 8011, "host_ip": "127.0.0.1"})
        == "127.0.0.1"
    )
