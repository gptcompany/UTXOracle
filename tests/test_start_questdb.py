"""Native QuestDB for CI jobs on runners without a Docker daemon (sg-ci)."""

import hashlib
import io
import tarfile
import urllib.error
from pathlib import Path

import pytest

from scripts.ci import start_questdb


def _archive(tmp_path: Path) -> Path:
    path = tmp_path / "questdb.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        payload = b"#!/bin/sh\n"
        info = tarfile.TarInfo("questdb-test/bin/questdb.sh")
        info.size = len(payload)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(payload))
    return path


def test_the_release_is_pinned_to_a_full_sha256():
    assert len(start_questdb.SHA256) == 64
    assert start_questdb.RELEASE in start_questdb.URL
    assert start_questdb.URL.startswith("https://github.com/questdb/questdb/releases/")


def test_verify_accepts_the_pinned_digest_and_rejects_any_other(tmp_path):
    archive = _archive(tmp_path)
    start_questdb.verify(archive, hashlib.sha256(archive.read_bytes()).hexdigest())
    with pytest.raises(SystemExit, match="sha256"):
        start_questdb.verify(archive, "0" * 64)


def test_extract_returns_the_launcher_of_the_single_top_directory(tmp_path):
    home = start_questdb.extract(_archive(tmp_path), tmp_path / "out")
    assert (home / "bin" / "questdb.sh").is_file()


def test_wait_ready_retries_until_the_http_endpoint_answers():
    calls = []

    def opener(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(b"{}")

    start_questdb.wait_ready(opener, attempts=5, interval=0, sleep=lambda _: None)
    assert len(calls) == 3
    assert calls[0] == start_questdb.READY_URL


def test_wait_ready_fails_visibly_when_questdb_never_starts():
    def opener(url, timeout):
        raise urllib.error.URLError("connection refused")

    with pytest.raises(SystemExit, match="never became ready"):
        start_questdb.wait_ready(opener, attempts=3, interval=0, sleep=lambda _: None)


def test_a_questdb_that_never_starts_reports_every_server_log(
    tmp_path, monkeypatch, capsys
):
    """The failure path must show stdout-*.txt as well as the *.log files (rv-utxo97)."""
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(start_questdb, "download", lambda url, destination: None)
    monkeypatch.setattr(start_questdb, "verify", lambda archive, expected: None)
    monkeypatch.setattr(start_questdb, "extract", lambda archive, destination: tmp_path)

    def start(argv, **kwargs):
        log = tmp_path / "questdb-native" / "data" / "log"
        log.mkdir(parents=True)
        (log / "questdb-2026-11-14.log").write_text("server log: bind failed\n")
        (log / "stdout-2026-11-14T14-00-00.txt").write_text(
            "jvm stdout: cannot allocate\n"
        )

    def never_ready(opener):
        raise SystemExit("QuestDB never became ready")

    monkeypatch.setattr(start_questdb.subprocess, "run", start)
    monkeypatch.setattr(start_questdb, "wait_ready", never_ready)

    with pytest.raises(SystemExit, match="never became ready"):
        start_questdb.main()

    err = capsys.readouterr().err
    assert "server log: bind failed" in err
    assert "jvm stdout: cannot allocate" in err
