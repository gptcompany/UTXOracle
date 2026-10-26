"""Startup of `python -m scripts.daily_analysis` (the unit's ExecStart), in a subprocess.

The guards must run BEFORE any import that reads os.environ: api.questdb_repository converts
QUESTDB_* with int() at import time, and a bad value there used to end in a traceback that
printed the value (F-419, review r3). The environment of the child is built by hand, so
nothing of the machine running the tests leaks in, and no value of a real .env is involved.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BAD = "not-a-port-9f3c71"  # synthetic; must never show up in stdout or stderr


def _run(
    tmp_path: Path, env_file: str | None, **env: str
) -> subprocess.CompletedProcess:
    child_env = {"PATH": os.defpath, "HOME": str(tmp_path), **env}
    if env_file is not None:
        path = tmp_path / ".env"
        path.write_text(env_file)
        child_env["UTXORACLE_ENV_FILE"] = str(path)
    else:
        child_env["UTXORACLE_ENV_FILE"] = str(tmp_path / "absent.env")
    return subprocess.run(
        [sys.executable, "-m", "scripts.daily_analysis", "--dry-run"],
        cwd=REPO,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_env_file_with_a_non_numeric_destination_port_exits_3_before_the_import(
    tmp_path,
):
    result = _run(
        tmp_path,
        f"QUESTDB_ILP_PORT={BAD}\n",
        QUESTDB_ILP_PORT=BAD,  # what systemd's EnvironmentFile= would have loaded
    )

    assert result.returncode == 3, result.stderr
    assert "QUESTDB_ILP_PORT" in result.stderr
    assert BAD not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_non_numeric_questdb_port_from_the_environment_exits_6_naming_only_the_variable(
    tmp_path,
):
    result = _run(tmp_path, None, QUESTDB_PG_PORT=BAD)

    assert result.returncode == 6, result.stderr
    assert "QUESTDB_PG_PORT" in result.stderr
    assert BAD not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_the_numeric_check_covers_every_int_conversion_of_the_repository_at_import():
    """If api/questdb_repository.py gains a new int(os.getenv("QUESTDB_...")) at module
    level, the early check must list it too: parsed with ast, not scanned."""
    import scripts.daily_analysis as daily

    tree = ast.parse((REPO / "api" / "questdb_repository.py").read_text())
    converted = set()
    for node in tree.body:  # module level only: what runs at import
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if getattr(call.func, "id", None) == "int" and call.args:
                inner = call.args[0]
                if (
                    isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", None) == "getenv"
                    and isinstance(inner.args[0], ast.Constant)
                ):
                    converted.add(inner.args[0].value)

    assert converted, "no int(os.getenv(...)) found: the check below would be vacuous"
    assert converted <= set(daily.NUMERIC_QUESTDB_ENV)
