"""Security tests: BRK authenticates to bitcoind with the cookie, never with argv credentials.

Runbook and roadmap regressions. The runtime check of the effective BRK
configuration is tracked in issue #16; there is no static discovery gate.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DUMMY = "R3_DUMMY_ONLY"


class TestRpcArgvSecurity:
    """Operator runbook and roadmap."""

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


class TestRunbookCoordinatedRollback:
    """R2-M1 regression: backups first, ordered rollback, real RPC checks."""

    @staticmethod
    def _text() -> str:
        return RUNBOOK_PATH.read_text(encoding="utf-8")

    @staticmethod
    def _section(text: str, start: str, end: str | None = None) -> str:
        begin = text.index(start)
        stop = text.index(end, begin + len(start)) if end else len(text)
        return text[begin:stop]

    def test_backups_precede_the_first_change(self):
        text = self._text()
        prep = self._section(text, "### Preparazione", "### Passo 1")
        for needle in (
            "bitcoin.conf",
            "brk-v0.3.6/docker/docker-compose.yml",
            "brk-v0.3.6/.env",
            "mempool-stack",
            "UTXOracle/.env",
        ):
            assert needle in prep, f"backup list misses {needle}"
        assert "cp -p" in prep

    def test_rollback_order_is_bitcoind_then_consumers_then_brk(self):
        text = self._text()
        rollback = self._section(text, "## 5. Rollback Coordinato")
        labels = [
            "**R1 — bitcoind**",
            "**R2 — consumatori**",
            "**R3 — BRK**",
            "**R4 — verifica**",
        ]
        positions = [rollback.find(label) for label in labels]
        assert all(p != -1 for p in positions), positions
        assert positions == sorted(positions)
        # Every per-step rollback delegates to the coordinated sequence.
        for n in range(2, 6):
            block = self._section(text, f"- **Rollback Passo {n}:**", "---")
            assert "Rollback Coordinato" in block, f"Rollback Passo {n}"

    def test_rollback_declares_the_reactivated_credential_as_compromised(self):
        rollback = self._section(self._text(), "## 5. Rollback Coordinato").lower()
        assert "compromess" in rollback
        assert "rotazione" in rollback
        assert "temporane" in rollback

    def test_real_rpc_check_per_client_after_migration_and_rollback(self):
        text = self._text()
        assert "getblockcount" in text
        migration = self._section(text, "### Passo 5", "## 5. Rollback Coordinato")
        rollback = self._section(text, "## 5. Rollback Coordinato")
        clients = ("brk", "utxoracle", "mempool-electrs", "mempool-api")
        for label, section in (("migrazione", migration), ("rollback", rollback)):
            calls = [line for line in section.splitlines() if "rpc_check " in line]
            for client in clients:
                assert any(client in call for call in calls), f"{label}: {client}"
        # /health is local to BRK and says nothing about bitcoind authentication.
        assert "/health" in migration and "non certifica" in migration

    def test_rpc_check_prints_only_label_and_http_code(self):
        text = self._text()
        definition = self._section(text, "rpc_check() {", "\n}\n")
        assert "-o /dev/null" in definition
        assert "-w '%{http_code}'" in definition
        assert "-K -" in definition, "credential must not be in curl argv"
        for command in runbook_commands(text):
            if re.search(r"\bcurl\b", command):
                assert "-o /dev/null" in command and "-w " in command, command

    def test_rpcauth_output_is_redirected_never_printed(self):
        text = self._text()
        assert "rpcauth.py" in text
        invocations = [c for c in runbook_commands(text) if "rpcauth.py" in c]
        assert invocations and all("> " in c for c in invocations)


if __name__ == "__main__":
    exit_code = pytest.main([str(Path(__file__)), "-v"])
    sys.exit(exit_code)
