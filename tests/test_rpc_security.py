"""Security tests: BRK authenticates to bitcoind with the cookie, never with argv credentials.

The gate itself (fail-closed allowlist, invariants 1-3) lives in rpc_argv_gate.py;
this module runs it over the repository and holds its regressions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve the sibling library even when this file is loaded outside pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.rpc_argv_gate import (  # noqa: E402
    EXCLUDED_DIRS,  # noqa: F401  (re-exported: reviewers adjust it in probes)
    check_compose_content,
    check_compose_file,
    check_env_file,
    check_unit_content,
    check_unit_file,
    find_repo_files,
    scan_repo,
)

# RPC_GATE_REPO_ROOT lets a regression run the real gate on a synthetic tree.
REPO_ROOT = Path(
    os.environ.get("RPC_GATE_REPO_ROOT") or Path(__file__).resolve().parent.parent
)


class TestRpcArgvSecurity:
    """Ensure no Compose or Systemd unit file passes rpcpassword as a CLI argument."""

    def test_repo_compose_files_do_not_pass_rpcpassword_arg(self):
        compose_files = find_repo_files(REPO_ROOT, kind="compose")
        assert compose_files, "Expected at least one Compose file in the repository"

        all_violations: list[str] = []
        for file_path in compose_files:
            all_violations.extend(check_compose_file(file_path, REPO_ROOT))

        assert not all_violations, (
            "Compose files violate the BRK cookie-auth allowlist:\n"
            + "\n".join(all_violations)
        )

    def test_repo_unit_files_do_not_pass_rpcpassword_arg(self):
        unit_files = find_repo_files(REPO_ROOT, kind="unit")
        assert unit_files, "Expected at least one systemd unit file in the repository"

        all_violations: list[str] = []
        for file_path in unit_files:
            all_violations.extend(check_unit_file(file_path, REPO_ROOT))

        assert not all_violations, (
            "systemd units violate the BRK cookie-auth allowlist:\n"
            + "\n".join(all_violations)
        )

    def test_repo_env_files_do_not_hold_rpc_credentials(self):
        env_files = find_repo_files(REPO_ROOT, kind="env")
        all_violations: list[str] = []
        for file_path in env_files:
            all_violations.extend(check_env_file(file_path, REPO_ROOT))

        assert not all_violations, (
            "Env files hold forbidden rpc credential keys:\n"
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
        assert any("'rpcpassword'" in v for v in violations)
        assert not any("secret123" in v for v in violations)

    def test_detector_catches_compose_inline_arg(self):
        sample = """
services:
  brk:
    image: brk:latest
    command: "brk --bitcoindir /bitcoin --rpcpassword=secret123"
"""
        violations = check_compose_content(sample, "test-compose.yml")
        assert any("'rpcpassword'" in v for v in violations)
        assert not any("secret123" in v for v in violations)

    def test_detector_catches_unit_execstart_arg(self):
        sample = """
[Unit]
Description=Test Service

[Service]
ExecStart=/usr/local/bin/brk --bitcoindir /bitcoin --rpcpassword secret123
"""
        violations = check_unit_content(sample, "test.service")
        assert any("'rpcpassword'" in v for v in violations)
        assert not any("secret123" in v for v in violations)

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
    volumes:
      - /data/cold/Bitcoin:/bitcoin:ro
"""
        violations = check_compose_content(sample_compose, "safe-compose.yml")
        assert not violations

        sample_unit = """
[Unit]
Description=Safe Service

[Service]
Environment="RPC_PASSWORD=secret_in_env"
ReadOnlyPaths=/bitcoin
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
        assert any("rpcpassword" in v for v in compose_violations)

        unit_sample = f"""
[Service]
ExecStart=/usr/bin/brk --rpcpassword {dummy_secret}
"""
        unit_violations = check_unit_content(unit_sample, "brk.service")
        assert len(unit_violations) >= 1
        for v in unit_violations:
            assert dummy_secret not in v, f"Violation leaked secret: {v}"
        assert any("rpcpassword" in v for v in unit_violations)

    def test_detector_catches_unit_continuation(self):
        """M1 regression: detect rpcpassword on continued ExecStart lines."""
        sample = """
[Service]
ExecStart=/usr/bin/brk \\
    --rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL
"""
        violations = check_unit_content(sample, "brk.service")
        assert len(violations) >= 1
        assert any("rpcpassword" in v for v in violations)

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
        assert any("rpcpassword" in v for v in violations)

    def test_detector_catches_unit_expanded_args(self):
        """M1 regression: detect rpcpassword expanded from Environment in ExecStart."""
        sample = """
[Service]
Environment="BRK_ARGS=--rpcpassword REVIEW_DUMMY_NOT_A_CREDENTIAL"
ExecStart=/usr/bin/brk $BRK_ARGS
"""
        violations = check_unit_content(sample, "brk.service")
        assert len(violations) >= 1
        assert any("rpcpassword" in v for v in violations)

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
        assert any("schema" in v.lower() or "rpcpassword" in v for v in violations)

    @pytest.mark.parametrize(
        "broken_yaml",
        [
            "services:\n  brk:\n    command: [--{flag}={dummy}\n",
            'services:\n  brk:\n    command: "--{flag}={dummy}\n',
            "services:\n  brk:\n\tcommand: --{flag}={dummy}\n",
        ],
        ids=["unclosed-flow", "unclosed-quote", "tab-indent"],
    )
    def test_invalid_yaml_failure_never_leaks_value(self, broken_yaml, tmp_path):
        """R2-H1 regression: a real gate failure on invalid YAML must not echo the value."""
        # Short enough for PyYAML's snippet window (<=36 chars) to show it whole.
        dummy = "R3_DUMMY_424242"
        content = broken_yaml.format(flag="rpcpassword", dummy=dummy)

        # Unit level: diagnostics carry only file, error type and numeric position.
        violations = check_compose_content(content, "docker-compose.yml")
        assert violations, "invalid YAML must fail closed"
        for v in violations:
            # PyYAML truncates long snippets: a value prefix is a leak too.
            assert dummy[:6] not in v
        assert any(re.search(r"line \d+, column \d+", v) for v in violations)

        # End to end: run the real gate under pytest and read its captured output.
        (tmp_path / "docker-compose.yml").write_text(content, encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(Path(__file__)),
                "-k",
                "test_repo_compose_files_do_not_pass_rpcpassword_arg",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(tmp_path),
                "-c",
                os.devnull,
                "--basetemp",
                str(tmp_path / "pytest-inner"),
                "--tb=long",
                "-l",
            ],
            env={**os.environ, "RPC_GATE_REPO_ROOT": str(tmp_path)},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 1, "the inner gate run must genuinely fail"
        assert "docker-compose.yml" in result.stdout
        assert dummy[:6] not in result.stdout + result.stderr

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
        assert (
            "world-readable" in content.lower() or "world readable" in content.lower()
        )

        # M2: Must instruct removal of rpcuser/rpcpassword to generate .cookie in v28
        assert "rpcpassword" in content
        assert "rpcuser" in content

        # M3: 5 ordered steps
        step_keywords = ["Passo 1", "Passo 2", "Passo 3", "Passo 4", "Passo 5"]
        last_pos = -1
        for kw in step_keywords:
            pos = content.find(f"### {kw}")
            assert pos != -1, f"Missing step heading: ### {kw}"
            assert pos > last_pos, (
                f"Steps not in order: ### {kw} appeared out of sequence"
            )
            last_pos = pos

        # M3: Rollback for each step
        assert "Rollback" in content
        for kw in step_keywords:
            assert (
                f"Rollback {kw}" in content
                or f"Rollback del {kw}" in content
                or f"Rollback - {kw}" in content
            )

        # M3: Downtime window
        assert "interruzione" in content.lower() or "downtime" in content.lower()

        # M3: Other bitcoind RPC consumers (Dell & repo)
        assert "mempool-electrs" in content
        assert "mempool-api" in content
        assert "bitcoin_rpc.py" in content
        assert "rpcauth" in content

        # H1/H2 & M3: process inspection prints flag names only, never values
        assert "grep -oE" in content
        assert "REDACTED" not in content


DUMMY = "R3_DUMMY_ONLY"
COMPOSE_NAME = "docker-compose.yml"
UNIT_NAME = "brk.service"


def _compose(body: str, *, volumes: str = "") -> str:
    """Compose document with one BRK service; `body` is its indented fields."""
    return f"services:\n  brk:\n    image: dummy-review-image\n{body}{volumes}"


COOKIE_RO_VOLUME = "    volumes:\n      - /data/cold/Bitcoin:/bitcoin:ro\n"

# name -> {relative path: content}. Every entry must be rejected (R2 probes.py,
# the seven R2 bypasses and the extra spellings found while closing H3).
REJECTED_TREES: dict[str, dict[str, str]] = {
    # R1 literal and expansion forms
    "compose_string_equals": {
        COMPOSE_NAME: _compose(f'    command: "brk --rpcpassword={DUMMY}"\n')
    },
    "compose_list_separate": {
        COMPOSE_NAME: _compose(f'    command: ["brk", "--rpcpassword", "{DUMMY}"]\n')
    },
    "compose_list_equals": {
        COMPOSE_NAME: _compose(f'    command: ["brk", "--rpcpassword={DUMMY}"]\n')
    },
    "compose_multiline_folded": {
        COMPOSE_NAME: _compose(
            f"    command: >\n      brk\n      --rpcpassword {DUMMY}\n"
        )
    },
    "compose_multiline_literal": {
        COMPOSE_NAME: _compose(
            f"    command: |\n      brk\n      --rpcpassword {DUMMY}\n"
        )
    },
    "compose_env_value": {
        COMPOSE_NAME: _compose(
            f'    command: "brk --rpcpassword=${{BTC_RPC_PASSWORD}}"\n    environment:\n      BTC_RPC_PASSWORD: {DUMMY}\n'
        )
    },
    "compose_expanded_args": {
        COMPOSE_NAME: _compose(
            f'    command: ["/bin/sh", "-c", "exec brk $$BRK_ARGS"]\n    environment:\n      BRK_ARGS: "--rpcpassword {DUMMY}"\n'
        )
    },
    "unit_separate": {
        UNIT_NAME: f"[Service]\nExecStart=/usr/bin/brk --rpcpassword {DUMMY}\n"
    },
    "unit_equals": {
        UNIT_NAME: f"[Service]\nExecStart=/usr/bin/brk --rpcpassword={DUMMY}\n"
    },
    "unit_continuation": {
        UNIT_NAME: f"[Service]\nExecStart=/usr/bin/brk \\\n    --rpcpassword {DUMMY}\n"
    },
    "unit_expanded_args": {
        UNIT_NAME: f'[Service]\nEnvironment="BRK_ARGS=--rpcpassword {DUMMY}"\nExecStart=/usr/bin/brk $BRK_ARGS\n'
    },
    "invalid_command_schema": {
        COMPOSE_NAME: _compose(
            f'    command: {{unexpected: "--rpcpassword {DUMMY}"}}\n'
        )
    },
    # R2 bypasses
    "unit_space_before_equals": {
        UNIT_NAME: f"[Service]\nExecStart = /usr/bin/brk --rpcpassword {DUMMY}\n"
    },
    "unit_quoted_flag": {
        UNIT_NAME: f'[Service]\nExecStart=/usr/bin/brk "--rpcpassword" {DUMMY}\n'
    },
    "unit_environment_spacing": {
        UNIT_NAME: f'[Service]\nEnvironment = "BRK_ARGS=--rpcpassword {DUMMY}"\nExecStart=/usr/bin/brk $BRK_ARGS\n'
    },
    "unit_comment_in_continuation": {
        UNIT_NAME: f"[Service]\nExecStart=/usr/bin/brk \\\n# allowed comment inside continuation\n --rpcpassword {DUMMY}\n"
    },
    "unit_environment_file": {
        UNIT_NAME: "[Service]\nEnvironmentFile=/unused/scratch-only.env\nExecStart=/usr/bin/brk $BRK_ARGS\n"
    },
    "compose_quoted_flag": {
        COMPOSE_NAME: _compose(f"    command: 'brk \"--rpcpassword\" {DUMMY}'\n")
    },
    "compose_env_file": {
        COMPOSE_NAME: _compose(
            '    command: ["/bin/sh", "-c", "exec brk $$BRK_ARGS"]\n    env_file: ./brk.env\n'
        ),
        "brk.env": f"BRK_ARGS=--rpcpassword {DUMMY}\n",
    },
    "compose_malformed_yaml": {
        COMPOSE_NAME: f"services:\n  brk:\n    command: [--rpcpassword={DUMMY}\n"
    },
    **{
        f"writer_compose_env_{tag}": {
            COMPOSE_NAME: _compose(
                f'    command: ["/bin/sh", "-c", "exec brk {spelling}"]\n    environment:\n      - "BRK_ARGS=--rpcpassword {DUMMY}"\n'
            )
        }
        for tag, spelling in {
            "plain": "$BRK_ARGS",
            "braces": "${BRK_ARGS}",
            "dollar2": "$$BRK_ARGS",
            "dollar2_braces": "$${BRK_ARGS}",
        }.items()
    },
    **{
        f"writer_unit_env_{tag}": {
            UNIT_NAME: f'[Service]\nEnvironment="BRK_ARGS=--rpcpassword {DUMMY}"\nExecStart=/usr/bin/brk {spelling}\n'
        }
        for tag, spelling in {
            "plain": "$BRK_ARGS",
            "braces": "${BRK_ARGS}",
            "dollar2": "$$BRK_ARGS",
            "dollar2_braces": "$${BRK_ARGS}",
        }.items()
    },
    # Spellings beyond the R2 probes: the substring or the argv is rebuilt by the parser.
    "compose_split_quotes": {
        COMPOSE_NAME: _compose(f"    command: \"brk --rpc''password {DUMMY}\"\n")
    },
    "compose_yaml_hex_escape": {
        COMPOSE_NAME: _compose(
            f'    command: ["brk", "--\\x72pcpassword", "{DUMMY}"]\n'
        )
    },
    "compose_yaml_escaped_newline": {
        COMPOSE_NAME: _compose('    command: ["brk", "--rpcpass\\\n      word", "X"]\n')
    },
    "unit_split_quotes": {
        UNIT_NAME: f'[Service]\nExecStart=/usr/bin/brk --rpc""password {DUMMY}\n'
    },
    "unit_c_escape": {
        UNIT_NAME: f"[Service]\nExecStart=/usr/bin/brk --\\x72pcpassword {DUMMY}\n"
    },
    "unit_mixed_case_comment": {
        UNIT_NAME: "[Service]\n; RpcUser was here\nExecStart=/usr/bin/brk --rpccookiefile /bitcoin/.cookie\n"
    },
    "compose_comment_only": {
        COMPOSE_NAME: "services:\n  web:\n    image: nginx\n    # rpcpassword goes here\n"
    },
    "env_file_in_repo_with_rpcuser": {".env": "RPCUSER=somebody\n"},
    "env_file_utf16": {
        "brk.env": "RPCPASSWORD=x\n".encode("utf-16-le").decode("latin-1")
    },
    "compose_env_file_missing": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--rpccookiefile", "/bitcoin/.cookie"]\n    env_file: ./absent.env\n',
            volumes=COOKIE_RO_VOLUME,
        )
    },
    "compose_env_passthrough": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--rpccookiefile", "/bitcoin/.cookie"]\n    environment:\n      - BRK_ARGS\n',
            volumes=COOKIE_RO_VOLUME,
        )
    },
    "compose_cookie_mount_rw": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--rpccookiefile", "/bitcoin/.cookie"]\n',
            volumes="    volumes:\n      - /data/cold/Bitcoin:/bitcoin\n",
        )
    },
    "compose_cookie_mount_missing": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--rpccookiefile", "/bitcoin/.cookie"]\n'
        )
    },
    "compose_cookie_flag_missing": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--bitcoindir", "/bitcoin"]\n',
            volumes=COOKIE_RO_VOLUME,
        )
    },
    "compose_cookie_value_expanded": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--rpccookiefile", "$COOKIE"]\n',
            volumes=COOKIE_RO_VOLUME,
        )
    },
    "unit_cookie_flag_missing": {
        UNIT_NAME: "[Service]\nReadOnlyPaths=/bitcoin\nExecStart=/usr/bin/brk --bitcoindir /bitcoin\n"
    },
    "unit_cookie_dir_not_read_only": {
        UNIT_NAME: "[Service]\nExecStart=/usr/bin/brk --rpccookiefile /bitcoin/.cookie\n"
    },
    "unit_brk_by_name_without_command": {
        "brk-stack.service": "[Service]\nExecStart=/usr/bin/docker compose up -d\n"
    },
    "unit_environment_file_in_repo_no_cookie": {
        UNIT_NAME: "[Service]\nEnvironmentFile=brk.env\nExecStart=/usr/bin/brk --bitcoindir /bitcoin\n",
        "brk.env": "FOO=bar\n",
    },
}

# The correct cookie configuration must keep passing.
ACCEPTED_TREES: dict[str, dict[str, str]] = {
    "compose_cookie_ro_mount": {
        COMPOSE_NAME: _compose(
            '    command: ["brk", "--bitcoindir", "/bitcoin", "--rpccookiefile", "/bitcoin/.cookie"]\n'
            "    env_file: ./brk.env\n"
            "    environment:\n      BTC_RPC_PASSWORD_FILE_NOT_USED: nothing\n",
            volumes=COOKIE_RO_VOLUME,
        ),
        "brk.env": "BRK_LOG=info\n",
    },
    "compose_cookie_string_command_long_ro_syntax": {
        COMPOSE_NAME: _compose(
            '    command: "brk --rpccookiefile=/bitcoin/.cookie"\n',
            volumes="    volumes:\n      - type: bind\n        source: /data/cold/Bitcoin\n        target: /bitcoin\n        read_only: true\n",
        )
    },
    "unit_cookie_read_only_paths": {
        UNIT_NAME: "[Service]\nReadOnlyPaths=/bitcoin\nExecStart=/usr/bin/brk --bitcoindir /bitcoin --rpccookiefile /bitcoin/.cookie\n"
    },
    "unit_cookie_bind_read_only_paths": {
        UNIT_NAME: "[Service]\nBindReadOnlyPaths=/data/cold/Bitcoin:/bitcoin\nExecStart=/usr/bin/brk --rpccookiefile=/bitcoin/.cookie\n"
    },
    "unrelated_services_untouched": {
        COMPOSE_NAME: "services:\n  web:\n    image: nginx\n    command: [nginx, -g, daemon off;]\n    env_file: /outside/the/repo.env\n    environment:\n      - FROM_HOST\n      - API_URL=http://x/$$y\n",
        "worker.service": "[Service]\nEnvironmentFile=-/outside/the/repo/.env\nExecStart=/usr/bin/python -m worker --url=${URL}\n",
    },
}


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            content.encode("latin-1")
            if rel == "brk.env" and "\x00" in content
            else content.encode("utf-8")
        )


class TestRpcArgvAllowlistGate:
    """R2-H3 regression: fail-closed allowlist (substring, unverifiable env, cookie positive)."""

    @pytest.mark.parametrize("name", sorted(REJECTED_TREES))
    def test_rejected(self, name, tmp_path):
        _write_tree(tmp_path, REJECTED_TREES[name])
        violations = scan_repo(tmp_path)
        assert violations, f"{name}: gate accepted a forbidden configuration"
        for v in violations:
            assert DUMMY not in v and DUMMY[:6] not in v, (
                f"{name}: diagnostic leaked the value"
            )

    @pytest.mark.parametrize("name", sorted(ACCEPTED_TREES))
    def test_accepted(self, name, tmp_path):
        _write_tree(tmp_path, ACCEPTED_TREES[name])
        assert scan_repo(tmp_path) == []


RUNBOOK_PATH = REPO_ROOT / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
# First pipeline stages that can carry a credential value from the runtime.
VALUE_SOURCES = re.compile(r"^(ps|docker logs|journalctl)\b")
# A source pipeline must end in a stage that emits names or counts, never lines.
COUNTING_LAST_STAGE = re.compile(r"^(grep\s+-\w*[co]\w*\b|uniq -c|wc -l)")
SYNTHETIC_RUNTIME_LINES = "\n".join(
    [
        f"1234 sam brk --rpcuser {DUMMY} --rpcpassword {DUMMY}",
        f"1235 sam brk --rpcuser={DUMMY} --rpcpassword={DUMMY}",
        f"1236 sam brk -rpcpassword {DUMMY} -rpcuser={DUMMY}",
        f"2026-10-12 brk auth failed: rpcpassword={DUMMY} 401 unauthorized",
        f"2026-10-12 Using random cookie authentication. rpcuser {DUMMY}",
    ]
)


def runbook_commands(text: str) -> list[str]:
    """Logical shell commands of every fenced code block (continuations joined)."""
    commands: list[str] = []
    in_fence = False
    pending = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            pending = ""
            continue
        if not in_fence or not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        commands.append((pending + stripped).strip())
        pending = ""
    return commands


class TestRunbookNeverPrintsValues:
    """R2-H2 regression: no operator command may print a credential value."""

    def test_source_pipelines_hide_values_in_every_syntax(self, tmp_path):
        synthetic = tmp_path / "runtime.txt"
        synthetic.write_text(SYNTHETIC_RUNTIME_LINES + "\n", encoding="utf-8")
        executed = 0
        for command in runbook_commands(RUNBOOK_PATH.read_text(encoding="utf-8")):
            stages = [stage.strip() for stage in command.split(" | ")]
            if not VALUE_SOURCES.match(stages[0]):
                continue
            assert COUNTING_LAST_STAGE.match(stages[-1]), (
                f"source pipeline must end in names/counts only: {stages[-1]}"
            )
            stages[0] = f"cat {synthetic}"
            result = subprocess.run(
                ["bash", "-o", "pipefail", "-c", " | ".join(stages)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert DUMMY not in result.stdout + result.stderr, (
                f"command leaks the value on synthetic input: {command}"
            )
            assert DUMMY[:6] not in result.stdout + result.stderr
            executed += 1
        assert executed >= 1, "runbook must contain at least one process/log check"

    def test_no_command_reads_secrets_to_the_terminal(self):
        forbidden = re.compile(
            r"(^|[;&|]\s*)(cat|head|tail|less|more|printenv|env|set)\b|docker inspect|docker exec"
        )
        for command in runbook_commands(RUNBOOK_PATH.read_text(encoding="utf-8")):
            # Command substitution feeding printf/curl never reaches the terminal.
            outside_substitution = re.sub(r"\$\([^)]*\)", "", command)
            assert not forbidden.search(outside_substitution), command


if __name__ == "__main__":
    exit_code = pytest.main([str(Path(__file__)), "-v"])
    sys.exit(exit_code)
