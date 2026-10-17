"""scripts/alerts/ntfy_dati.sh: UTXOracle events on the ntfy dati topic (#709).

A fake curl on PATH records argv and the config read from stdin: no network.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/alerts/ntfy_dati.sh"
TOPIC = "dati-topic-fixture"
FAKE_CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$CAPTURE/argv"
cat > "$CAPTURE/config"
printf '%s' "${FAKE_HTTP_CODE:-200}"
"""


@pytest.fixture
def run(tmp_path):
    (tmp_path / "curl").write_text(FAKE_CURL, encoding="utf-8")
    (tmp_path / "curl").chmod(0o755)

    def _run(*args, **extra):
        env = {
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CAPTURE": str(tmp_path),
            "NTFY_TOPIC_DATI": TOPIC,
            **extra,
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    _run.capture = tmp_path
    return _run


def test_publishes_on_dati_with_the_topic_only_on_stdin(run):
    result = run(
        "3", "warning", "unit.service failed", "result=exit-code exit=exited/1"
    )
    assert result.returncode == 0, result.stderr
    argv = (run.capture / "argv").read_text(encoding="utf-8").splitlines()
    assert (run.capture / "config").read_text(encoding="utf-8") == (
        f'url = "https://ntfy.sh/{TOPIC}"\n'
    )
    assert not any(TOPIC in a for a in argv)
    assert "Priority: 3" in argv
    assert any(
        a.startswith("Title: dati/utxoracle: unit.service failed su ") for a in argv
    )
    assert argv[-1] == "result=exit-code exit=exited/1"
    assert TOPIC not in result.stderr


def test_priority_is_capped_at_3_on_the_dell(run):
    assert run("5", "rotating_light", "e", "b").returncode == 0
    assert (
        "Priority: 3" in (run.capture / "argv").read_text(encoding="utf-8").splitlines()
    )


def test_rejected_or_unconfigured_publish_exits_1_with_the_reason(run):
    rejected = run("3", "warning", "e", "b", FAKE_HTTP_CODE="429")
    assert rejected.returncode == 1
    assert "failed with HTTP 429" in rejected.stderr
    missing = run("3", "warning", "e", "b", NTFY_TOPIC_DATI="")
    assert missing.returncode == 1
    assert "NTFY_TOPIC_DATI not set" in missing.stderr
