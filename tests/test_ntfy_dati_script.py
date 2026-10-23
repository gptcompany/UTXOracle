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
BASE = "https://ntfy.example.test"
FAKE_CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$CAPTURE/argv"
cat > "$CAPTURE/config"
if [ -n "${FAKE_CURL_ERROR:-}" ]; then
  # Like curl's own diagnostics (bad URL, glob, TLS): they quote the URL read from -K.
  printf 'curl: (3) URL rejected: %s\\n' "$(cat "$CAPTURE/config")" >&2
  exit 3
fi
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
            "NTFY_BASE_URL": BASE,
            **extra,
        }
        env = {k: v for k, v in env.items() if v is not None}  # None removes a variable
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
        f'url = "{BASE}/{TOPIC}"\n'
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
    assert "dati priority 3 failed with HTTP 429" in rejected.stderr
    for value in ("", "ENC[abc]", "encrypted:abc"):
        missing = run("3", "warning", "e", "b", NTFY_TOPIC_DATI=value)
        assert missing.returncode == 1
        assert "NTFY_TOPIC_DATI not set" in missing.stderr


def test_curl_diagnostics_never_reach_the_log(run):
    result = run("3", "warning", "e", "b", FAKE_CURL_ERROR="1")
    assert result.returncode == 1
    assert "dati priority 3 failed with HTTP 000 (curl exit 3)" in result.stderr
    argv = (run.capture / "argv").read_text(encoding="utf-8")
    for text in (argv, result.stdout, result.stderr):
        assert TOPIC not in text
        assert BASE not in text


@pytest.mark.parametrize(
    ("given", "sent"),
    [
        ("0", "1"),
        ("-1", "3"),
        ("9", "3"),
        ("abc", "3"),
        ("", "3"),
        ("1", "1"),
        ("2", "2"),
    ],
)
def test_priority_is_clamped_to_1_3(run, given, sent):
    assert run(given, "warning", "e", "b").returncode == 0
    assert (
        f"Priority: {sent}"
        in (run.capture / "argv").read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.parametrize(
    "base", [None, "", "ntfy.example.test", "ftp://ntfy.example.test", "https://"]
)
def test_no_default_destination_without_a_valid_base_url(run, base):
    result = run("3", "warning", "e", "b", NTFY_BASE_URL=base)
    assert result.returncode == 1
    assert "NTFY_BASE_URL" in result.stderr
    assert not (run.capture / "argv").exists(), "curl must not be invoked"
    assert TOPIC not in result.stderr + result.stdout
