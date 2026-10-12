"""Security tests: verify no Compose or Systemd unit file passes rpcpassword as an argument.

Bitcoin Core credentials should be supplied via bitcoind cookie file (.cookie)
or via protected environment/config files with 0600 permissions, never as CLI
arguments (argv) which are exposed in `ps` and `docker inspect`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Regex matching rpcpassword passed as a command-line argument:
# Matches `--rpcpassword`, `-rpcpassword`, `--rpcpassword=...`, `-rpcpassword=...`
ARGV_RPCPASSWORD_PATTERN = re.compile(
    r"(?:^|\s)(?:--|-)?rpcpassword(?:=|\s|$)",
    re.IGNORECASE,
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    ".tox",
}


def find_repo_files(repo_root: Path, pattern: str) -> list[Path]:
    """Find files matching a glob pattern, skipping virtualenv and VCS dirs."""
    matches: list[Path] = []
    for p in repo_root.rglob(pattern):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        if p.is_file():
            matches.append(p)
    return sorted(matches)


def check_compose_service_command(
    service_name: str,
    field_name: str,
    value: Any,
    filename: str,
) -> list[str]:
    """Check a compose service's command or entrypoint for rpcpassword arguments."""
    violations: list[str] = []

    if isinstance(value, str):
        if ARGV_RPCPASSWORD_PATTERN.search(value):
            violations.append(
                f"{filename}: service '{service_name}' passes rpcpassword in {field_name}: {value}"
            )
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            item_str = str(item)
            if ARGV_RPCPASSWORD_PATTERN.search(item_str) or item_str.lower().startswith(
                ("--rpcpassword", "-rpcpassword")
            ):
                violations.append(
                    f"{filename}: service '{service_name}' passes rpcpassword in {field_name}[{idx}]: {item_str}"
                )
    return violations


def check_compose_content(content: str, filename: str = "compose.yml") -> list[str]:
    """Inspect Compose YAML content and return violations."""
    violations: list[str] = []
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return [f"{filename}: failed to parse YAML: {e}"]

    if not isinstance(data, dict):
        return violations

    services = data.get("services")
    if isinstance(services, dict):
        for svc_name, svc_conf in services.items():
            if not isinstance(svc_conf, dict):
                continue
            for field in ("command", "entrypoint"):
                if field in svc_conf:
                    violations.extend(
                        check_compose_service_command(
                            svc_name, field, svc_conf[field], filename
                        )
                    )
    return violations


def check_unit_content(content: str, filename: str = "unit.service") -> list[str]:
    """Inspect Systemd unit file content and return violations."""
    violations: list[str] = []
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith(
            (
                "ExecStart=",
                "ExecStop=",
                "ExecReload=",
                "ExecStartPre=",
                "ExecStartPost=",
            )
        ):
            _, cmd = line.split("=", 1)
            if ARGV_RPCPASSWORD_PATTERN.search(cmd):
                violations.append(
                    f"{filename}:{line_no}: Exec directive passes rpcpassword as argument: {line}"
                )
    return violations


def check_compose_file(path: Path) -> list[str]:
    """Check a compose file on disk."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [f"{path}: could not read file: {e}"]
    rel_path = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    return check_compose_content(content, str(rel_path))


def check_unit_file(path: Path) -> list[str]:
    """Check a Systemd unit file on disk."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [f"{path}: could not read file: {e}"]
    rel_path = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    return check_unit_content(content, str(rel_path))


class TestRpcArgvSecurity:
    """Ensure no Compose or Systemd unit file passes rpcpassword as a CLI argument."""

    def test_repo_compose_files_do_not_pass_rpcpassword_arg(self):
        compose_files = (
            find_repo_files(REPO_ROOT, "*compose*.yml")
            + find_repo_files(REPO_ROOT, "*compose*.yaml")
            + find_repo_files(REPO_ROOT, "docker-compose*.yml")
            + find_repo_files(REPO_ROOT, "docker-compose*.yaml")
        )
        unique_compose_files = sorted(set(compose_files))
        assert unique_compose_files, "Expected at least one Compose file in the repository"

        all_violations: list[str] = []
        for file_path in unique_compose_files:
            violations = check_compose_file(file_path)
            all_violations.extend(violations)

        assert not all_violations, (
            "Found rpcpassword passed as argument in Compose files:\n"
            + "\n".join(all_violations)
        )

    def test_repo_unit_files_do_not_pass_rpcpassword_arg(self):
        unit_files = find_repo_files(REPO_ROOT, "*.service")
        assert unit_files, "Expected at least one systemd .service file in the repository"

        all_violations: list[str] = []
        for file_path in unit_files:
            violations = check_unit_file(file_path)
            all_violations.extend(violations)

        assert not all_violations, (
            "Found rpcpassword passed as argument in Systemd unit files:\n"
            + "\n".join(all_violations)
        )

    def test_detector_catches_compose_list_arg(self):
        sample = """
services:
  brk:
    image: brk:latest
    command:
      - --bitcoindir
      - /bitcoin
      - --rpcuser
      - bitcoin
      - --rpcpassword
      - secret123
"""
        violations = check_compose_content(sample, "test-compose.yml")
        assert len(violations) == 1
        assert "--rpcpassword" in violations[0]

    def test_detector_catches_compose_inline_arg(self):
        sample = """
services:
  brk:
    image: brk:latest
    command: "brk --bitcoindir /bitcoin --rpcpassword=secret123"
"""
        violations = check_compose_content(sample, "test-compose.yml")
        assert len(violations) == 1
        assert "rpcpassword=secret123" in violations[0]

    def test_detector_catches_unit_execstart_arg(self):
        sample = """
[Unit]
Description=Test Service

[Service]
ExecStart=/usr/local/bin/brk --bitcoindir /bitcoin --rpcpassword secret123
"""
        violations = check_unit_content(sample, "test.service")
        assert len(violations) == 1
        assert "Exec directive passes rpcpassword" in violations[0]

    def test_detector_allows_safe_cookie_and_env(self):
        sample_compose = """
services:
  brk:
    image: brk:latest
    environment:
      BTC_RPC_PASSWORD: secret_in_env
    command:
      - --bitcoindir
      - /bitcoin
      - --rpccookiefile
      - /bitcoin/.cookie
"""
        violations = check_compose_content(sample_compose, "safe-compose.yml")
        assert not violations

        sample_unit = """
[Unit]
Description=Safe Service

[Service]
Environment="RPC_PASSWORD=secret_in_env"
ExecStart=/usr/local/bin/brk --bitcoindir /bitcoin --rpccookiefile /bitcoin/.cookie
"""
        violations = check_unit_content(sample_unit, "safe.service")
        assert not violations


if __name__ == "__main__":
    exit_code = pytest.main([str(Path(__file__)), "-v"])
    sys.exit(exit_code)
