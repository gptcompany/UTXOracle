"""Run the RPC consumer check inside a consumer's own launch context (R5-M1).

``python -m scripts.utils.unit_context <label> host <consumer> <unit>`` and
``python -m scripts.utils.unit_context <label> cron <consumer> <user> <dir> <uv>``
start ``python -m scripts.utils.rpc_cookie <label> <consumer>`` as a transient
unit (``sudo systemd-run --wait --pipe --collect``) with the consumer's user,
working directory, environment and sandbox, launched by the same interpreter or
launcher as the unit's ExecStart. Used by the runbook's ``rpc_check``.

Fail-closed: the context is copied only when every assignment of the unit's
fragment and drop-ins is either transported (``CARRIED``) or known not to change
how the check's process resolves, authenticates or reaches bitcoind (``INERT``),
and ExecStart is one direct launch this module recognises. Anything else prints
``FAIL contesto non riproducibile`` with the property name, never its value.

Values never reach an argv: Environment= entries go to a 0600 temporary file passed
as the first EnvironmentFile= (systemd reads it as root; the unit's own
EnvironmentFile= entries follow, so they still override Environment= as in the
unit) and removed when the check ends. The only output is one line: label,
outcome and HTTP code.

Unit properties are read in structured form with ``busctl --json=short`` (argv as a
JSON array); the sandbox values passed with ``-p`` come from ``systemctl show -P``,
whose output systemd accepts back as an assignment. Unit files are parsed with
configparser for their key names only.
"""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CONSUMERS = ("live", "sync", "daily")
CARRIED = (  # sandbox and identity properties passed to the transient unit as-is
    "User",
    "Group",
    "SupplementaryGroups",
    "WorkingDirectory",
    "UMask",
    "ProtectHome",
    "ProtectSystem",
    "PrivateTmp",
    "PrivateNetwork",
    "PrivateDevices",
    "NoNewPrivileges",
    "ReadWritePaths",
    "ReadOnlyPaths",
    "InaccessiblePaths",
    "IPAddressAllow",
    "IPAddressDeny",
    "RestrictAddressFamilies",
)
# Transported by other means: Environment (0600 file), EnvironmentFile (paths),
# ExecStart (launcher, shape-checked).
SERVICE_KEYS = set(CARRIED) | {"Environment", "EnvironmentFile", "ExecStart"}
INERT = {  # lifecycle, logging and resources: no effect on one getblockcount call
    "Type",
    "Restart",
    "RestartSec",
    "RemainAfterExit",
    "SuccessExitStatus",
    "TimeoutSec",
    "TimeoutStartSec",
    "TimeoutStopSec",
    "StartLimitInterval",
    "StartLimitIntervalSec",
    "StartLimitBurst",
    "WatchdogSec",
    "PIDFile",
    "ExecReload",
    "ExecStop",
    "ExecStopPost",
    "KillMode",
    "KillSignal",
    "StandardOutput",
    "StandardError",
    "SyslogIdentifier",
    "MemoryMax",
    "MemoryHigh",
    "CPUQuota",
    "CPUWeight",
    "IOWeight",
    "TasksMax",
    "LimitNOFILE",
    "Nice",
    "OOMScoreAdjust",
}
UNIT_KEYS = {
    "Description",
    "Documentation",
    "After",
    "Before",
    "Wants",
    "Requires",
    "Requisite",
    "BindsTo",
    "PartOf",
    "Conflicts",
    "OnFailure",
    "StartLimitInterval",
    "StartLimitIntervalSec",
    "StartLimitBurst",
    "RequiresMountsFor",
}
UV_FLAGS = {
    "--no-sync",
    "--frozen",
    "--locked",
    "--no-dev",
    "--offline",
    "-q",
    "--quiet",
}
UV_VALUE_OPTIONS = {"--project", "--directory", "--python"}
SYSTEMD = "org.freedesktop.systemd1"


class NotReproducible(Exception):
    """The consumer's context cannot be copied exactly; the message names a property."""


def _busctl(*args: str) -> object:
    out = subprocess.run(
        ["busctl", "--json=short", *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise NotReproducible("unità non caricata")
    return json.loads(out.stdout)["data"]


def _show(unit: str, prop: str) -> str:
    out = subprocess.run(
        ["systemctl", "show", "-P", prop, unit],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def declared_keys(paths: list[str]) -> set[tuple[str, str]]:
    """(section, key) assigned in a unit fragment and its drop-ins; values unused."""
    keys: set[tuple[str, str]] = set()
    for path in paths:
        parser = configparser.ConfigParser(
            delimiters=("=",),
            comment_prefixes=("#", ";"),
            strict=False,
            interpolation=None,
            default_section="\x01",
        )
        parser.optionxform = str
        try:
            parser.read_string(Path(path).read_text(encoding="utf-8"), source=path)
        except (OSError, UnicodeDecodeError, configparser.Error):
            raise NotReproducible(f"file di unità non leggibile: {path}") from None
        for section in parser.sections():
            for key, value in parser.items(section):
                lines = value.split("\n")
                # A configparser continuation is a systemd line continuation only
                # after a trailing backslash; otherwise it hides a real assignment.
                if any(not line.rstrip().endswith("\\") for line in lines[:-1]):
                    raise NotReproducible(f"riga indentata in {section}/{key}")
                keys.add((section, key))
    return keys


def check_declared(keys: set[tuple[str, str]]) -> None:
    for section, key in sorted(keys):
        if section == "Install":
            continue
        if section == "Unit" and (
            key in UNIT_KEYS or key.startswith(("Condition", "Assert"))
        ):
            continue
        if section == "Service" and (key in SERVICE_KEYS or key in INERT):
            continue
        raise NotReproducible(f"{section}/{key}")


def env_lines(assignments: list[str], source: str) -> list[str]:
    """Environment= entries that an EnvironmentFile reproduces byte for byte."""
    lines = []
    for assignment in assignments:
        name, sep, value = assignment.partition("=")
        bare = name.replace("_", "")
        valid_name = name.isascii() and not name[:1].isdigit()
        valid_name = valid_name and (bare.isalnum() or (name and not bare))
        literal = not any(c in value for c in "\\'\"$\n\r") and value == value.strip()
        if not (sep and valid_name and literal):
            raise NotReproducible(f"{source} {name or '?'}")
        lines.append(f"{name}={value}")
    return lines


def launcher(argv: list[str]) -> list[str]:
    """The ExecStart interpreter or launcher, ready to take ``-m <module> ...``."""
    if any("$" in arg for arg in argv):
        raise NotReproducible("ExecStart con variabili")
    prefix, rest = [], list(argv)
    if Path(rest[0]).name == "env":
        if len(rest) < 2 or rest[1].startswith("-") or "=" in rest[1]:
            raise NotReproducible("ExecStart env con opzioni o assegnazioni")
        prefix, rest = [rest[0]], rest[1:]
    name = Path(rest[0]).name
    if name == "uv" and rest[1:2] == ["run"]:
        options, i = [], 2
        while i < len(rest) and rest[i].startswith("-"):
            if rest[i] in UV_FLAGS:
                options.append(rest[i])
                i += 1
            elif rest[i] in UV_VALUE_OPTIONS and i + 1 < len(rest):
                options += rest[i : i + 2]
                i += 2
            else:
                raise NotReproducible(f"ExecStart uv run {rest[i]}")
        if "--no-sync" not in options:
            # Same interpreter (.venv/bin/python); only skips re-syncing the
            # service's venv, which the check must not modify.
            options.insert(0, "--no-sync")
        command = rest[i : i + 2]
        if command[:1] == ["uvicorn"] or (
            command[:1] in (["python"], ["python3"]) and command[1:] == ["-m"]
        ):
            python = "python" if command[0] == "uvicorn" else command[0]
            return [*prefix, rest[0], "run", *options, python]
    elif name.startswith("python") and rest[1:2] == ["-m"]:
        return [*prefix, rest[0]]
    elif name == "uvicorn" and not prefix:
        return [str(Path(rest[0]).with_name("python"))]
    raise NotReproducible("ExecStart non riconosciuto")


def host_plan(unit: str) -> tuple[list[str], list[str], list[str]]:
    """(systemd-run -p options, Environment lines, launcher) of a systemd unit."""
    manager = ("/org/freedesktop/systemd1", f"{SYSTEMD}.Manager")
    path = _busctl("call", SYSTEMD, *manager, "GetUnit", "s", unit)[0]
    unit_iface, service_iface = f"{SYSTEMD}.Unit", f"{SYSTEMD}.Service"
    fragment = _busctl("get-property", SYSTEMD, path, unit_iface, "FragmentPath")
    dropins = _busctl("get-property", SYSTEMD, path, unit_iface, "DropInPaths")
    if not fragment:
        raise NotReproducible("unità senza file (transitoria o generata)")
    check_declared(declared_keys([fragment, *dropins]))
    exec_start = _busctl("get-property", SYSTEMD, path, service_iface, "ExecStartEx")
    if len(exec_start) != 1 or exec_start[0][2]:
        raise NotReproducible("ExecStart multiplo o con prefissi")
    exe, argv = exec_start[0][0], exec_start[0][1]
    if not argv or argv[0] != exe:
        raise NotReproducible("ExecStart con argv[0] diverso")
    env = env_lines(
        _busctl("get-property", SYSTEMD, path, service_iface, "Environment"),
        "Environment",
    )
    files = _busctl("get-property", SYSTEMD, path, service_iface, "EnvironmentFiles")
    props = []
    for prop in CARRIED:
        value = _show(unit, prop)
        if value:
            props += ["-p", f"{prop}={value}"]
    for file, ignore_errors in files:
        props += ["-p", f"EnvironmentFile={'-' if ignore_errors else ''}{file}"]
    return props, env, launcher(argv)


def cron_plan(user: str, directory: str, uv: str) -> tuple[list[str], ...]:
    """A system crontab line: its user and ``cd``, cron's minimal environment plus
    the variables of the line, given in CRON_ENV (space-separated NAME=value)."""
    cron_env = os.environ.get("CRON_ENV", "").split()
    env = env_lines(["PATH=/usr/bin:/bin", "SHELL=/bin/sh", *cron_env], "CRON_ENV")
    props = ["-p", f"User={user}", "-p", f"WorkingDirectory={directory}"]
    return props, env, [uv, "run", "--no-sync", "python"]


def run(label: str, consumer: str, props, env, launch) -> int:
    fd, env_file = tempfile.mkstemp(prefix="rpc-check-", suffix=".env")
    try:
        with os.fdopen(fd, "w") as handle:  # mkstemp: 0600, owner only
            handle.write("".join(f"{line}\n" for line in env))
        command = [
            "sudo",
            *("systemd-run", "--quiet", "--wait", "--pipe", "--collect"),
            "--expand-environment=no",
            *("-p", f"EnvironmentFile={env_file}"),
            *props,
            "--",
            *launch,
            *("-m", "scripts.utils.rpc_cookie", label, consumer),
        ]
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # transient-unit and launcher chatter
            text=True,
            check=False,
        )
    finally:
        os.unlink(env_file)
    lines = result.stdout.splitlines()
    outcome = lines[-1].removeprefix(f"{label}: ") if lines else ""
    code = outcome.removeprefix("FAIL HTTP ")
    if outcome == "OK HTTP 200" and result.returncode == 0:
        print(f"{label}: OK HTTP 200")
        return 0
    if not (outcome.startswith("FAIL HTTP ") and len(code) == 3 and code.isdigit()):
        code = "000"  # no check line: the launcher or the transient unit failed
    print(f"{label}: FAIL HTTP {code}")
    return result.returncode or 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    label = args[0] if args else "?"
    try:
        if len(args) == 4 and args[1] == "host" and args[2] in CONSUMERS:
            plan = host_plan(args[3])
        elif len(args) == 6 and args[1] == "cron" and args[2] in CONSUMERS:
            plan = cron_plan(*args[3:6])
        else:
            print(f"{label}: FAIL consumatore sconosciuto o argomenti errati")
            return 2
    except NotReproducible as exc:
        print(f"{label}: FAIL contesto non riproducibile ({exc})")
        return 2
    return run(label, args[2], *plan)


if __name__ == "__main__":
    raise SystemExit(main())
