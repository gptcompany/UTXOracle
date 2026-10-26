"""Static checks of the utxoracle-daily-analysis units (F-419). Nothing is installed or started."""

from __future__ import annotations

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE = REPO_ROOT / "utxoracle-daily-analysis.service"
TIMER = REPO_ROOT / "utxoracle-daily-analysis.timer"
PRICES_TIMER = REPO_ROOT / "utxoracle-daily-prices-refresh.timer"


def _parse(path: Path) -> configparser.ConfigParser:
    # systemd allows repeated keys (Environment=); keep them all.
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(path.read_text())
    return parser


def _environment(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.startswith("Environment="):
            key, _, value = line.removeprefix("Environment=").strip('"').partition("=")
            env[key] = value
    return env


def test_timer_points_at_the_service_and_runs_after_prices_refresh():
    timer = _parse(TIMER)
    assert timer["Timer"]["Unit"] == SERVICE.name
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"
    assert timer["Timer"]["OnCalendar"] == "*-*-* 03:00:00 UTC"
    assert _parse(PRICES_TIMER)["Timer"]["OnCalendar"] == "*-*-* 01:00:00 UTC"


def test_service_runs_daily_analysis_against_the_live_questdb():
    service = _parse(SERVICE)
    assert service["Service"]["Type"] == "oneshot"
    assert "scripts.daily_analysis" in service["Service"]["ExecStart"]
    env = _environment(SERVICE)
    assert (env["QUESTDB_ILP_HOST"], env["QUESTDB_ILP_PORT"]) == ("127.0.0.1", "9909")
    assert (env["QUESTDB_PG_HOST"], env["QUESTDB_PG_PORT"]) == ("127.0.0.1", "9912")
    assert env["QUESTDB_HTTP_PORT"] == "9900"
    # The destination guard (exit 3 on mismatch) expects exactly what the unit configures.
    for key in ("ILP_HOST", "ILP_PORT", "PG_HOST", "PG_PORT"):
        assert env[f"UTXORACLE_EXPECTED_QUESTDB_{key}"] == env[f"QUESTDB_{key}"]
    assert "utxoracle-daily-prices-refresh.service" in service["Unit"]["After"]


@pytest.mark.skipif(
    shutil.which("systemd-analyze") is None, reason="systemd-analyze not present"
)
def test_units_pass_systemd_analyze_verify():
    result = subprocess.run(
        ["systemd-analyze", "verify", str(SERVICE), str(TIMER)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_job_schedule_is_defined_once_and_matches_the_timer():
    """The run window of daily_analysis is derived from the unit, not written twice."""
    env = _environment(SERVICE)
    scheduled = env["UTXORACLE_DAILY_SCHEDULE_UTC"]  # "HH:MM", read by the job
    on_calendar = _parse(TIMER)["Timer"]["OnCalendar"]
    assert on_calendar == f"*-*-* {scheduled}:00 UTC"
