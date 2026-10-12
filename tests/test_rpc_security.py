"""Security tests: verify no Compose or Systemd unit file passes rpcpassword as an argument.

Bitcoin Core credentials should be supplied via bitcoind cookie file (.cookie)
or via protected environment/config files with 0600 permissions, never as CLI
arguments (argv) which are exposed in `ps` and `docker inspect`.
"""

from __future__ import annotations

import re
import shlex
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


def expand_env_vars(text: str, env_vars: dict[str, str]) -> str:
    """Expand $VAR, ${VAR}, $$VAR, $${VAR} using environment dictionary."""
    if not text or not env_vars:
        return text

    def _replace(match: re.Match) -> str:
        var_name = match.group(1) or match.group(2)
        return env_vars.get(var_name, match.group(0))

    return re.sub(
        r"\${1,2}(?:\{([a-zA-Z_][a-zA-Z0-9_]*)\}|([a-zA-Z_][a-zA-Z0-9_]*))",
        _replace,
        text,
    )


def extract_compose_env(service_conf: dict[str, Any]) -> dict[str, str]:
    """Extract environment variables defined in a compose service."""
    env = service_conf.get("environment")
    env_vars: dict[str, str] = {}
    if isinstance(env, dict):
        for k, v in env.items():
            env_vars[str(k)] = str(v) if v is not None else ""
    elif isinstance(env, list):
        for item in env:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def check_compose_service_command(
    service_name: str,
    field_name: str,
    value: Any,
    filename: str,
    env_vars: dict[str, str] | None = None,
    line_no: int | None = None,
) -> list[str]:
    """Check a compose service's command or entrypoint for rpcpassword arguments."""
    violations: list[str] = []
    location = f"{filename}:{line_no}" if line_no is not None else filename
    env_vars = env_vars or {}

    # Validate schema: command/entrypoint must be str or list of scalar values
    if value is not None and not isinstance(value, (str, list)):
        return [
            f"{location}: service '{service_name}' has invalid schema for '{field_name}'"
        ]

    if isinstance(value, list):
        for idx, item in enumerate(value):
            if not isinstance(item, (str, int, float, bool)):
                return [
                    f"{location}: service '{service_name}' has invalid schema for '{field_name}[{idx}]'"
                ]

    if isinstance(value, str):
        expanded = expand_env_vars(value, env_vars)
        if ARGV_RPCPASSWORD_PATTERN.search(value) or ARGV_RPCPASSWORD_PATTERN.search(expanded):
            violations.append(
                f"{location}: service '{service_name}' passes flag '--rpcpassword' in '{field_name}'"
            )
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            item_str = str(item)
            expanded_item = expand_env_vars(item_str, env_vars)
            if (
                ARGV_RPCPASSWORD_PATTERN.search(item_str)
                or ARGV_RPCPASSWORD_PATTERN.search(expanded_item)
                or item_str.lower().startswith(("--rpcpassword", "-rpcpassword"))
                or expanded_item.lower().startswith(("--rpcpassword", "-rpcpassword"))
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
            svc_env = extract_compose_env(svc_conf)
            for field in ("command", "entrypoint"):
                if field in svc_conf:
                    violations.extend(
                        check_compose_service_command(
                            svc_name,
                            field,
                            svc_conf[field],
                            filename,
                            env_vars=svc_env,
                            line_no=line_no,
                        )
                    )
    return violations


def parse_systemd_lines(content: str) -> list[tuple[int, str]]:
    """Parse systemd unit lines, joining trailing backslash continuations."""
    logical_lines: list[tuple[int, str]] = []
    current_line = ""
    start_line_no = 1
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.rstrip()
        if not current_line:
            start_line_no = line_no
        if line.endswith("\\"):
            current_line += line[:-1].strip() + " "
        else:
            current_line += line.strip()
            if current_line and not current_line.startswith(("#", ";")):
                logical_lines.append((start_line_no, current_line))
            current_line = ""
    if current_line and not current_line.startswith(("#", ";")):
        logical_lines.append((start_line_no, current_line))
    return logical_lines


def parse_systemd_environment(logical_lines: list[tuple[int, str]]) -> dict[str, str]:
    """Extract environment variable assignments from Environment= directives."""
    env_vars: dict[str, str] = {}
    for _, line in logical_lines:
        if line.startswith("Environment="):
            env_str = line[len("Environment="):].strip()
            try:
                parts = shlex.split(env_str, posix=True)
            except ValueError:
                parts = env_str.split()
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars


def check_unit_content(content: str, filename: str = "unit.service") -> list[str]:
    """Inspect Systemd unit file content and return violations."""
    violations: list[str] = []
    logical_lines = parse_systemd_lines(content)
    env_vars = parse_systemd_environment(logical_lines)

    for line_no, line in logical_lines:
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
                expanded_cmd = expand_env_vars(cmd, env_vars)
                if ARGV_RPCPASSWORD_PATTERN.search(cmd) or ARGV_RPCPASSWORD_PATTERN.search(expanded_cmd):
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

    def test_detector_catches_unit_continuation(self):
        """M1 regression: detect rpcpassword on continued ExecStart lines."""
        sample = """
[Service]
ExecStart=/usr/bin/brk \\
    --rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL
"""
        violations = check_unit_content(sample, "brk.service")
        assert len(violations) >= 1
        assert any("--rpcpassword" in v for v in violations)

    def test_detector_catches_compose_expanded_args(self):
        """M1 regression: detect rpcpassword passed via compose environment into command."""
        sample = """
services:
  brk:
    image: dummy-review-image
    command: ["/bin/sh", "-c", "exec brk $$BRK_ARGS"]
    environment:
      BRK_ARGS: "--rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL"
"""
        violations = check_compose_content(sample, "docker-compose.yml")
        assert len(violations) >= 1
        assert any("--rpcpassword" in v for v in violations)

    def test_detector_catches_unit_expanded_args(self):
        """M1 regression: detect rpcpassword expanded from Environment in ExecStart."""
        sample = """
[Service]
Environment="BRK_ARGS=--rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL"
ExecStart=/usr/bin/brk $BRK_ARGS
"""
        violations = check_unit_content(sample, "brk.service")
        assert len(violations) >= 1
        assert any("--rpcpassword" in v for v in violations)

    def test_detector_catches_invalid_command_schema(self):
        """M1 regression: detect invalid compose command schema."""
        sample = """
services:
  brk:
    image: dummy-review-image
    command:
      unexpected: "--rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL"
"""
        violations = check_compose_content(sample, "docker-compose.yml")
        assert len(violations) >= 1
        assert any("schema" in v.lower() or "--rpcpassword" in v for v in violations)

    def test_production_roadmap_has_no_residual_7071_references(self):
        """L1 regression: ensure docs/PRODUCTION_ROADMAP.md has no unaligned :7071 references."""
        roadmap_path = REPO_ROOT / "docs" / "PRODUCTION_ROADMAP.md"
        assert roadmap_path.is_file(), f"Expected {roadmap_path} to exist"
        content = roadmap_path.read_text(encoding="utf-8")
        matches = [
            f"line {idx}: {line.strip()}"
            for idx, line in enumerate(content.splitlines(), start=1)
            if re.search(r":7071\b", line)
        ]
        assert not matches, (
            "Found residual :7071 references in docs/PRODUCTION_ROADMAP.md:\n"
            + "\n".join(matches)
        )

    def test_operator_migration_runbook_requirements(self):
        """M2 & M3 regression: verify operator procedure covers cookie auth, 5 steps, rollback, consumers."""
        runbook_path = REPO_ROOT / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
        assert runbook_path.is_file(), f"Expected {runbook_path} to exist"
        content = runbook_path.read_text(encoding="utf-8")

        # M2: Source citation and cookie permissions
        assert "httprpc.cpp" in content
        assert "InitRPCAuthentication" in content
        assert "-rpccookieperms" in content
        assert "world-readable" in content.lower() or "world readable" in content.lower()

        # M2: Must instruct removal of rpcuser/rpcpassword to generate .cookie in v28
        assert "rpcpassword" in content
        assert "rpcuser" in content

        # M3: 5 ordered steps
        step_keywords = ["Passo 1", "Passo 2", "Passo 3", "Passo 4", "Passo 5"]
        last_pos = -1
        for kw in step_keywords:
            pos = content.find(f"### {kw}")
            assert pos != -1, f"Missing step heading: ### {kw}"
            assert pos > last_pos, f"Steps not in order: ### {kw} appeared out of sequence"
            last_pos = pos

        # M3: Rollback for each step
        assert "Rollback" in content
        for kw in step_keywords:
            assert f"Rollback {kw}" in content or f"Rollback del {kw}" in content or f"Rollback - {kw}" in content

        # M3: Downtime window
        assert "interruzione" in content.lower() or "downtime" in content.lower()

        # M3: Other bitcoind RPC consumers (Dell & repo)
        assert "mempool-electrs" in content
        assert "mempool-api" in content
        assert "bitcoin_rpc.py" in content
        assert "rpcauth" in content

        # H1 & M3: Process inspection must mask credentials
        assert "sed" in content or "REDACTED" in content






if __name__ == "__main__":
    exit_code = pytest.main([str(Path(__file__)), "-v"])
    sys.exit(exit_code)
