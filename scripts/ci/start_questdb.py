"""Start the pinned QuestDB natively in a CI job: the sg-ci runners have no Docker daemon.

The release tarball is verified against a pinned sha256 before it is unpacked, QuestDB runs with the
defaults of the image the job used before (pg 8812, http 9000, ILP 9009, admin/quest) and the step
fails visibly, with every server log, if the HTTP endpoint does not answer within the same 30 x 2 s
window as the workflow's readiness step.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

RELEASE = "9.4.3"
URL = (
    f"https://github.com/questdb/questdb/releases/download/{RELEASE}/"
    f"questdb-{RELEASE}-rt-linux-x86-64.tar.gz"
)
SHA256 = "2324f5920d6476843df6c35ad975bed18bba10f3459f67fd243f48f15e438cd5"
READY_URL = "http://localhost:9000/exec?query=SELECT%201"
ATTEMPTS = 30
INTERVAL_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 10
CHUNK_BYTES = 1 << 20
LOG_TAIL_CHARS = 4000


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        with destination.open("wb") as out:
            while chunk := response.read(CHUNK_BYTES):
                out.write(chunk)


def verify(archive: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise SystemExit(f"sha256 mismatch for {archive.name}: refusing to unpack")


def extract(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")
    (home,) = [path for path in destination.iterdir() if path.is_dir()]
    return home


def wait_ready(
    opener: Callable[..., object],
    *,
    attempts: int = ATTEMPTS,
    interval: float = INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    for attempt in range(1, attempts + 1):
        try:
            opener(READY_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        except (urllib.error.URLError, OSError):
            sleep(interval)
        else:
            print(f"QuestDB ready after {attempt} attempt(s)")
            return
    raise SystemExit("QuestDB never became ready")


def report_logs(directory: Path) -> None:
    """Tail of every file QuestDB wrote (questdb-*.log and stdout-*.txt): the only diagnosis."""
    for log in sorted(path for path in directory.rglob("*") if path.is_file()):
        sys.stderr.write(
            f"--- {log.name}\n{log.read_text(errors='replace')[-LOG_TAIL_CHARS:]}\n"
        )


def main() -> int:
    work = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "questdb-native"
    work.mkdir(parents=True, exist_ok=True)
    archive = work / f"questdb-{RELEASE}.tar.gz"
    download(URL, archive)
    verify(archive, SHA256)
    home = extract(archive, work / "release")
    data = work / "data"
    subprocess.run(  # noqa: S603
        [str(home / "bin" / "questdb.sh"), "start", "-d", str(data)], check=True
    )
    try:
        wait_ready(urllib.request.urlopen)
    except SystemExit:
        report_logs(data / "log")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
