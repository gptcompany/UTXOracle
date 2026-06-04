"""Systemd smoke tests for spec-061 Phase 1.5 source freshness units."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCK_HEIGHTS_SERVICE = REPO_ROOT / "utxoracle-block-heights-catchup.service"
BLOCK_HEIGHTS_TIMER = REPO_ROOT / "utxoracle-block-heights-catchup.timer"
DAILY_PRICES_SERVICE = REPO_ROOT / "utxoracle-daily-prices-refresh.service"
DAILY_PRICES_TIMER = REPO_ROOT / "utxoracle-daily-prices-refresh.timer"

_HAS_SYSTEMD_ANALYZE = shutil.which("systemd-analyze") is not None


def _verify(*units: Path) -> subprocess.CompletedProcess:
    cmd = ["systemd-analyze", "verify"] + [str(unit) for unit in units]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


@pytest.mark.skipif(
    not _HAS_SYSTEMD_ANALYZE, reason="systemd-analyze not present"
)
def test_block_heights_catchup_units_valid():
    assert BLOCK_HEIGHTS_SERVICE.exists()
    assert BLOCK_HEIGHTS_TIMER.exists()
    result = _verify(BLOCK_HEIGHTS_SERVICE, BLOCK_HEIGHTS_TIMER)
    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_block_heights_catchup_unit_contract():
    service = BLOCK_HEIGHTS_SERVICE.read_text()
    timer = BLOCK_HEIGHTS_TIMER.read_text()

    assert "Type=oneshot" in service
    assert "Restart=" not in service
    assert "EnvironmentFile=-/media/sam/1TB/UTXOracle/.env" in service
    assert (
        "ExecStart=/usr/bin/env uv run python -m "
        "scripts.bootstrap.build_block_heights_questdb"
    ) in service
    assert "scripts.bootstrap.build_block_heights --use-rpc" not in service
    assert "After=questdb.service" in service
    assert "OnCalendar=hourly" in timer
    assert "Persistent=true" in timer
    assert "AccuracySec=5min" in timer
    assert "Unit=utxoracle-block-heights-catchup.service" in timer


@pytest.mark.skipif(
    not _HAS_SYSTEMD_ANALYZE, reason="systemd-analyze not present"
)
def test_daily_prices_refresh_units_valid():
    assert DAILY_PRICES_SERVICE.exists()
    assert DAILY_PRICES_TIMER.exists()
    result = _verify(DAILY_PRICES_SERVICE, DAILY_PRICES_TIMER)
    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_daily_prices_refresh_unit_contract():
    service = DAILY_PRICES_SERVICE.read_text()
    timer = DAILY_PRICES_TIMER.read_text()

    assert "Type=oneshot" in service
    assert "Restart=" not in service
    assert "EnvironmentFile=-/media/sam/1TB/UTXOracle/.env" in service
    assert (
        "ExecStart=/usr/bin/env uv run python -m "
        "scripts.bootstrap.build_price_table_questdb"
    ) in service
    assert "scripts.bootstrap.build_price_table\n" not in service
    assert "After=questdb.service docker-api-1.service" in service
    assert "OnCalendar=*-*-* 01:00:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "Unit=utxoracle-daily-prices-refresh.service" in timer
