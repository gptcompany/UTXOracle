"""R4-M3: the runbook's rpc_check queries RPC through the consumer's own context.

The function is extracted from docs/BRK_COOKIE_MIGRATION_RUNBOOK.md and run for
real. `docker exec` is a shim that runs the in-container script locally and
records the -u it was given; bitcoind is a fake JSON-RPC server. Dummy
credentials only; the output must be label, outcome and HTTP code.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from tests.fake_bitcoind import FakeBitcoind

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
COOKIE = "__cookie__:DUMMYCOOKIE0001"
OTHER = "__cookie__:DUMMYCOOKIE0002"


def _function() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("rpc_check() {")
    body = text[start : text.index("\n}\n", start) + 3]
    # The runbook names the production checkout; run the repo under test instead.
    return body.replace("/media/sam/1TB/UTXOracle", str(REPO))


@pytest.fixture
def ctx(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "docker"
    shim.write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            [ "$1" = exec ] || exit 99
            shift
            [ "$1" = -i ] && shift
            [ "$1" = -u ] && { echo "$2" > "$SHIM_UID"; shift 2; }
            shift  # container name
            exec "$@"
            """
        )
    )
    shim.chmod(0o755)
    node = FakeBitcoind(tuple(COOKIE.split(":")), {"getblockcount": lambda p: 900_000})
    cookie_file = tmp_path / "container.cookie"
    cookie_file.write_text(COOKIE)
    (tmp_path / ".cookie").write_text(COOKIE)
    (tmp_path / "bitcoin.conf").write_text(f"rpcport={node.port}\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_UID": str(tmp_path / "uid"),
    }

    def run(call: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f"{_function()}\n{call}"],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )

    run.node, run.url = node, f"http://127.0.0.1:{node.port}/"
    run.cookie_file, run.datadir, run.uid_file = cookie_file, tmp_path, tmp_path / "uid"
    yield run
    node.stop()


def test_container_context_reports_label_and_code_only(ctx):
    result = ctx(f'rpc_check "brk" ctr brk 1000:1000 "{ctx.cookie_file}" "{ctx.url}"')
    assert result.stdout == "brk: HTTP 200\n"
    assert ctx.uid_file.read_text().strip() == "1000:1000", "runs as the consumer UID"
    assert "DUMMY" not in result.stdout + result.stderr


def test_stale_credential_in_the_consumer_is_a_401_not_a_green_host_check(ctx):
    ctx.cookie_file.write_text(OTHER)  # consumer mounts an old cookie
    result = ctx(f'rpc_check "brk" ctr brk 1000:1000 "{ctx.cookie_file}" "{ctx.url}"')
    assert result.stdout == "brk: HTTP 401\n"
    assert "DUMMY" not in result.stdout + result.stderr


def test_credential_from_stdin_for_the_rollback_check(ctx):
    result = ctx(
        f'rpc_check "brk (legacy)" ctr brk 1000:1000 - "{ctx.url}"', stdin=COOKIE
    )
    assert result.stdout == "brk (legacy): HTTP 200\n"


def test_unreachable_bitcoind_is_http_000(ctx):
    ctx.node.stop()
    result = ctx(f'rpc_check "brk" ctr brk 1000:1000 "{ctx.cookie_file}" "{ctx.url}"')
    assert result.stdout == "brk: HTTP 000\n"


def test_host_entrypoint_context_ok_and_401(ctx):
    ok = ctx(f'rpc_check "utxoracle" host "{ctx.datadir}"')
    assert ok.stdout == "utxoracle: OK HTTP 200\n"
    (ctx.datadir / ".cookie").write_text(OTHER)
    bad = ctx(f'rpc_check "utxoracle" host "{ctx.datadir}"')
    assert bad.stdout == "utxoracle: FAIL HTTP 401\n"
    assert "DUMMY" not in ok.stdout + bad.stdout + bad.stderr
