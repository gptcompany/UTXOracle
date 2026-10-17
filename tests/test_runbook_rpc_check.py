"""R4-M3 / R5-M1: the runbook's rpc_check queries RPC through the consumer's container.

The function is extracted from docs/BRK_COOKIE_MIGRATION_RUNBOOK.md and run for
real. `docker exec` is a shim that runs the in-container script locally and
records the -u it was given; bitcoind is a fake JSON-RPC server. Dummy credentials
only; the output must be label, outcome and HTTP code.

Host consumers (live, sync, daily) are not certified here: rebuilding a service's
context from the operator shell gave false greens (R5-M1), so the runbook points to
UTXOracle#16 instead and these tests keep any host check from coming back.
"""

from __future__ import annotations

import ast
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from tests.fake_bitcoind import FakeBitcoind

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
COOKIE = "__cookie__:DUMMYCOOKIE0001"
OTHER = "__cookie__:DUMMYCOOKIE0002"
CHECK_MODULES = {"scripts.utils.rpc_cookie", "scripts.utils.unit_context"}
pytestmark = pytest.mark.usefixtures("hermetic_rpc")


def _function() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("rpc_check() {")
    return text[start : text.index("\n}\n", start) + 3]


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
    for name in ("sudo", "systemd-run", "uv", "systemctl", "busctl"):
        # Any host-side launch is recorded: no rpc_check branch may reach one.
        (bin_dir / name).write_text(f'#!/bin/bash\necho {name} >> "$SHIM_HOST"\n')
        (bin_dir / name).chmod(0o755)
    node = FakeBitcoind(tuple(COOKIE.split(":")), {"getblockcount": lambda p: 900_000})
    cookie_file = tmp_path / "container.cookie"
    cookie_file.write_text(COOKIE)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_UID": str(tmp_path / "uid"),
        "SHIM_HOST": str(tmp_path / "host-launches"),
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
    run.cookie_file, run.uid_file = cookie_file, tmp_path / "uid"
    run.host_launches = tmp_path / "host-launches"
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


# --- R5-M1 class: no host certification of a UTXOracle consumer ---------------------


def _runbook_code() -> list[str]:
    """Every fenced block and inline code span of the runbook, parsed as Markdown."""
    code = []
    for token in MarkdownIt("commonmark").parse(RUNBOOK.read_text(encoding="utf-8")):
        if token.type in ("fence", "code_block"):
            code.append(token.content)
        for child in token.children or []:
            if child.type == "code_inline":
                code.append(child.content)
    return code


def _commands(code: str) -> list[list[str]]:
    words = []
    for line in code.splitlines():
        try:
            words.append(shlex.split(line, comments=True))
        except ValueError:  # an unbalanced quote inside the docker exec script
            words.append(line.split())
    return [w for w in words if w]


def test_runbook_has_no_host_consumer_check_and_points_to_issue_16():
    for code in _runbook_code():
        for words in _commands(code):
            assert not (
                words[0] == "rpc_check" and len(words) > 2 and words[2] != "ctr"
            ), f"host check in the runbook: {words[:3]}"
            assert words[0] not in ("host)", "cron)", "host|cron)"), "host branch"
            modules = {words[i + 1] for i, w in enumerate(words[:-1]) if w == "-m"}
            assert not modules & CHECK_MODULES, f"check entrypoint invoked: {modules}"
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "la certificazione del consumatore host è in UTXOracle#16" in text


@pytest.mark.parametrize(
    "call",
    [
        'rpc_check "utxoracle" host /var/lib/bitcoind',
        'rpc_check "utxoracle-live" host live utxoracle-live.service',
        'rpc_check "utxoracle-daily" cron daily sam /srv /usr/bin/uv',
    ],
    ids=["datadir", "unit", "cron"],
)
def test_rpc_check_has_no_branch_that_can_green_a_host_consumer(ctx, call):
    result = ctx(call)
    assert "200" not in result.stdout and "OK" not in result.stdout
    assert not ctx.host_launches.exists(), "a host-side launcher was started"


def test_rpc_cookie_exposes_no_certification_entrypoint(tmp_path):
    tree = ast.parse((REPO / "scripts/utils/rpc_cookie.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    main_guards = [
        n
        for n in tree.body
        if isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)
    ]
    assert "main" not in names and not main_guards
    run = subprocess.run(
        [sys.executable, "-m", "scripts.utils.rpc_cookie", "chk", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=60,
        check=False,
    )
    assert run.stdout == "", "the module printed a check outcome"
