"""The live Wave 1 materializer bounds DuckDB memory (issue #98).

The unit climbed to 6.4 GB within ~40 minutes of a restart: wallet_waves and address_cohorts
GROUP BY address over the whole utxo_lifecycle_full, and DuckDB without memory_limit takes up
to 80% of the host RAM for that hash table. With a limit it spills to temp_directory.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb

from scripts.live import wave1_materializer_runtime as runtime

# A sort that needs the whole key set in memory (~30M rows * 8 B each, plus the payload).
_WORKLOAD = """
import json, resource, sys, duckdb
conn = duckdb.connect(":memory:", config=json.loads(sys.argv[1]))
conn.execute("SET threads TO 2")
conn.execute(
    "SELECT count(*) FROM (SELECT x FROM range(30000000) t(x) ORDER BY (x * 7919) % 1000003, x)"
).fetchall()
print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
"""


def _peak_rss_kib(config: dict[str, str]) -> int:
    done = subprocess.run(
        [sys.executable, "-I", "-c", _WORKLOAD, json.dumps(config)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(done.stdout.strip())


def test_connection_applies_the_declared_memory_limit(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    def fake_connect(path: str, *, read_only: bool, config: dict[str, str]):
        seen.update(path=path, read_only=read_only, config=config)
        return object()

    monkeypatch.setattr(runtime.duckdb, "connect", fake_connect)
    monkeypatch.setattr(runtime, "DUCKDB_MEMORY_LIMIT", "3GB")
    monkeypatch.setattr(runtime, "DUCKDB_TEMP_DIR", str(tmp_path))

    runtime._connect_duckdb()

    assert seen["read_only"] is True
    assert seen["config"] == {"memory_limit": "3GB", "temp_directory": str(tmp_path)}


def test_memory_limit_bounds_the_peak_rss(tmp_path: Path):
    unlimited = _peak_rss_kib({"temp_directory": str(tmp_path)})
    limited = _peak_rss_kib(
        {"memory_limit": "128MB", "temp_directory": str(tmp_path)}
    )
    assert limited < 0.75 * unlimited, (limited, unlimited)
    assert duckdb.__version__
