"""Systemd smoke tests for spec-061 Phase 1 units."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CREATION_CATCHUP_SERVICE = REPO_ROOT / "utxoracle-utxo-creation-catchup.service"

_HAS_SYSTEMD_ANALYZE = shutil.which("systemd-analyze") is not None


def _verify(*units: Path) -> subprocess.CompletedProcess:
    cmd = ["systemd-analyze", "verify"] + [str(unit) for unit in units]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


@pytest.mark.skipif(
    not _HAS_SYSTEMD_ANALYZE, reason="systemd-analyze not present"
)
def test_utxo_creation_catchup_service_valid():
    assert CREATION_CATCHUP_SERVICE.exists()
    result = _verify(CREATION_CATCHUP_SERVICE)
    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_utxo_creation_catchup_service_contract():
    content = CREATION_CATCHUP_SERVICE.read_text()

    assert "Already at tip" in content
    assert "utxo_lifecycle_supervisor.sh creation" in content
    assert "EnvironmentFile=-/media/sam/1TB/UTXOracle/.env" in content
    assert "Restart=on-failure" in content
    assert "RestartSec=60s" in content
    assert "ExecStopPost=" in content
    assert "DISCORD_WEBHOOK_URL" in content
