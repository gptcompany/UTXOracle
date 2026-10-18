"""No JWT secret may be committed as a default (F-231): compose and systemd files must require the variable."""

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


def _is_jwt_key(key: str) -> bool:
    return key.upper().startswith("JWT")


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


def test_compose_files_do_not_default_jwt_variables_to_a_secret_value():
    # Offenders are reported by file/service/key only: a failure must never echo a value.
    offenders, checked = [], 0
    for path in sorted(
        {f for f in _tracked(".yml", ".yaml") if "docker-compose" in f.name}
    ):
        for service, key, value in _compose_env(path):
            if _is_jwt_key(key):
                checked += 1
                if _looks_like_secret(value):
                    offenders.append(f"{path.name}:{service}:{key}")
    assert offenders == []
    assert checked >= 1


def test_live_compose_requires_jwt_secret():
    forms = [
        value.startswith("${JWT_SECRET:?")
        for _, key, value in _compose_env(ROOT / "docker-compose.live.yml")
        if key == "JWT_SECRET"
    ]
    assert forms != []
    assert all(forms)


def test_systemd_units_do_not_embed_jwt_values():
    offenders = []
    for path in _tracked(".service"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Environment="):
                for assignment in shlex.split(line.removeprefix("Environment=")):
                    key, _, value = assignment.partition("=")
                    if _is_jwt_key(key) and _looks_like_secret(value):
                        offenders.append(f"{path.name}:{key}")
    assert offenders == []


def test_no_compose_backup_files_are_tracked():
    offenders = [
        p.name
        for p in _tracked(".bak")
        if "docker-compose" in p.name or p.name.endswith(".service.bak")
    ]
    assert offenders == []
