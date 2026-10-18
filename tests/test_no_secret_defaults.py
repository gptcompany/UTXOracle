"""No secret may be committed as a default (F-231): compose and systemd files must not embed secret-shaped values.

Generalised after JWT_SECRET was removed (F-236): the check covers every variable whose name marks a credential."""

import re
import shlex
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# A signing secret looks like base64url of 32+ bytes. Only values inside already-parsed fields are inspected.
SECRET_SHAPE = re.compile(r"[A-Za-z0-9_-]{43,}")
SUBSTITUTION = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=](?P<default>[^}]*)\}")


def _tracked(*suffixes: str) -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.split(b"\0")
    return [ROOT / n.decode() for n in names if n and n.decode().endswith(suffixes)]


def _looks_like_secret(value: str) -> bool:
    candidates = [m.group("default") for m in SUBSTITUTION.finditer(value)] or [value]
    return any(SECRET_SHAPE.fullmatch(c.strip("'\"")) for c in candidates)


SECRET_KEY_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "API_KEY",
    "JWT",
)


def _is_secret_key(key: str) -> bool:
    return any(marker in key.upper() for marker in SECRET_KEY_MARKERS)


def _compose_env(path: Path):
    services = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(
        "services"
    ) or {}
    for name, service in services.items():
        env = service.get("environment") or {}
        items = (
            env.items()
            if isinstance(env, dict)
            else [e.split("=", 1) + [""] for e in env]
        )
        for item in items:
            key, value = item[0], str(item[1] if item[1] is not None else "")
            yield name, key, value


def test_compose_files_do_not_default_secret_variables_to_a_secret_value():
    # Offenders are reported by file/service/key only: a failure must never echo a value.
    offenders, inspected = [], 0
    for path in sorted(
        {f for f in _tracked(".yml", ".yaml") if "docker-compose" in f.name}
    ):
        for service, key, value in _compose_env(path):
            inspected += 1
            if _is_secret_key(key) and _looks_like_secret(value):
                offenders.append(f"{path.name}:{service}:{key}")
    assert offenders == []
    assert (
        inspected >= 1
    )  # the compose files were actually parsed: the check is not vacuous


def test_secret_check_flags_a_secret_shaped_default():
    # Synthetic values only: 43 characters of base64url shape, and the `${VAR:-default}` form.
    shaped = "A" * 43
    assert _looks_like_secret(shaped)
    assert _looks_like_secret("${SOME_TOKEN:-" + shaped + "}")
    assert not _looks_like_secret("${SOME_TOKEN:?SOME_TOKEN non impostato}")
    assert not _looks_like_secret("info")
    assert (
        _is_secret_key("API_TOKEN")
        and _is_secret_key("DB_PASSWORD")
        and not _is_secret_key("LOG_LEVEL")
    )


def test_systemd_units_do_not_embed_secret_values():
    offenders = []
    for path in _tracked(".service"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Environment="):
                for assignment in shlex.split(line.removeprefix("Environment=")):
                    key, _, value = assignment.partition("=")
                    if _is_secret_key(key) and _looks_like_secret(value):
                        offenders.append(f"{path.name}:{key}")
    assert offenders == []


def test_no_compose_backup_files_are_tracked():
    offenders = [
        p.name
        for p in _tracked(".bak")
        if "docker-compose" in p.name or p.name.endswith(".service.bak")
    ]
    assert offenders == []
