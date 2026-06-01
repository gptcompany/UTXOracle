"""Systemd unit smoke test for utxoracle-daily-aggregator (spec-061 US2 T021).

Verifies that the .service and .timer files at the repo root pass
`systemd-analyze verify`. Skipped on hosts without systemd.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE = REPO_ROOT / "utxoracle-daily-aggregator.service"
TIMER = REPO_ROOT / "utxoracle-daily-aggregator.timer"
BACKTEST_SERVICE = REPO_ROOT / "utxoracle-backtest-mirror.service"
BACKTEST_TIMER = REPO_ROOT / "utxoracle-backtest-mirror.timer"

_HAS_SYSTEMD = shutil.which("systemd-analyze") is not None


def _verify(*units: Path) -> subprocess.CompletedProcess:
    """Run systemd-analyze verify against the given unit files.

    Each unit is a relative path to repo root; we pass absolute paths so
    systemd-analyze does not look in /etc/systemd/system/.
    """
    cmd = ["systemd-analyze", "verify"] + [str(u) for u in units]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


@pytest.mark.skipif(not _HAS_SYSTEMD, reason="systemd-analyze not present")
def test_daily_aggregator_unit_files_valid():
    """T021: daily-aggregator .service + .timer must be parseable by systemd."""
    assert SERVICE.exists(), f"missing {SERVICE}"
    assert TIMER.exists(), f"missing {TIMER}"
    result = _verify(SERVICE, TIMER)
    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.skipif(not _HAS_SYSTEMD, reason="systemd-analyze not present")
def test_backtest_mirror_unit_files_valid():
    """T026c: backtest-mirror .service + .timer must be parseable by systemd."""
    assert BACKTEST_SERVICE.exists(), f"missing {BACKTEST_SERVICE}"
    assert BACKTEST_TIMER.exists(), f"missing {BACKTEST_TIMER}"
    result = _verify(BACKTEST_SERVICE, BACKTEST_TIMER)
    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_timer_calls_correct_service():
    """The daily timer file must reference the matching .service Unit."""
    if not TIMER.exists():
        pytest.skip("timer not authored yet (RED)")
    content = TIMER.read_text()
    assert "Unit=utxoracle-daily-aggregator.service" in content
    assert "OnCalendar=" in content
