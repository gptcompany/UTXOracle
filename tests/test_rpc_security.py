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
    line_no: int | None = None,
) -> list[str]:
    """Check a compose service's command or entrypoint for rpcpassword arguments."""
    violations: list[str] = []
    location = f"{filename}:{line_no}" if line_no is not None else filename

    if isinstance(value, str):
        if ARGV_RPCPASSWORD_PATTERN.search(value):
            violations.append(
                f"{location}: service '{service_name}' passes flag '--rpcpassword' in '{field_name}'"
            )
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            item_str = str(item)
            if ARGV_RPCPASSWORD_PATTERN.search(item_str) or item_str.lower().startswith(
                ("--rpcpassword", "-rpcpassword")
            ):
                violations.append(
                    f"{location}: service '{service_name}' passes flag '--rpcpassword' in '{field_name}[{idx}]'"
                )
    return violations


def find_line_number_in_content(content: str, pattern: re.Pattern) -> int | None:
    """Find the 1-based line number of the first line matching pattern."""
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        if pattern.search(raw_line):
            return line_no
    return None


def check_compose_content(content: str, filename: str = "compose.yml") -> list[str]:
    """Inspect Compose YAML content and return violations."""
    violations: list[str] = []
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return [f"{filename}: failed to parse YAML: {e}"]

    if not isinstance(data, dict):
        return violations

    line_no = find_line_number_in_content(content, ARGV_RPCPASSWORD_PATTERN)

    services = data.get("services")
    if isinstance(services, dict):
        for svc_name, svc_conf in services.items():
            if not isinstance(svc_conf, dict):
                continue
            for field in ("command", "entrypoint"):
                if field in svc_conf:
                    violations.extend(
                        check_compose_service_command(
                            svc_name, field, svc_conf[field], filename, line_no=line_no
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
        for directive in (
            "ExecStart",
            "ExecStop",
            "ExecReload",
            "ExecStartPre",
            "ExecStartPost",
        ):
            prefix = f"{directive}="
            if line.startswith(prefix):
                cmd = line[len(prefix):]
                if ARGV_RPCPASSWORD_PATTERN.search(cmd):
                    violations.append(
                        f"{filename}:{line_no}: directive '{directive}' passes flag '--rpcpassword' as argument"
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
        assert "--rpcpassword" in violations[0]
        assert "secret123" not in violations[0]

    def test_detector_catches_unit_execstart_arg(self):
        sample = """
[Unit]
Description=Test Service

[Service]
ExecStart=/usr/local/bin/brk --bitcoindir /bitcoin --rpcpassword secret123
"""
        violations = check_unit_content(sample, "test.service")
        assert len(violations) == 1
        assert "--rpcpassword" in violations[0]
        assert "secret123" not in violations[0]

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

    def test_detector_diagnostics_never_contain_credential_value(self):
        """H1 regression: ensure diagnostics and assert messages never leak credentials."""
        dummy_secret = "DUMMY_SECRET_TO_NOT_LEAK_987654"
        compose_sample = f"""
services:
  brk:
    image: brk:latest
    command: "brk --rpcpassword={dummy_secret}"
"""
        compose_violations = check_compose_content(compose_sample, "docker-compose.yml")
        assert len(compose_violations) >= 1
        for v in compose_violations:
            assert dummy_secret not in v, f"Violation leaked secret: {v}"
            assert "--rpcpassword" in v or "rpcpassword" in v

        unit_sample = f"""
[Service]
ExecStart=/usr/bin/brk --rpcpassword {dummy_secret}
"""
        unit_violations = check_unit_content(unit_sample, "brk.service")
        assert len(unit_violations) >= 1
        for v in unit_violations:
            assert dummy_secret not in v, f"Violation leaked secret: {v}"
            assert "--rpcpassword" in v or "rpcpassword" in v



if __name__ == "__main__":
    exit_code = pytest.main([str(Path(__file__)), "-v"])
    sys.exit(exit_code)
