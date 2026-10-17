"""R4-M3 / R5-M1: the runbook's rpc_check queries RPC through the consumer itself.

The function is extracted from docs/BRK_COOKIE_MIGRATION_RUNBOOK.md and run for
real. `docker exec` is a shim that runs the in-container script locally and
records the -u it was given; `sudo`, `systemctl show -P` and `systemd-run` are
shims too (systemd-run runs the command with a clean environment, the HOME of
User=, Environment=, EnvironmentFile= and WorkingDirectory=, like the transient
unit would): nothing touches the host's systemd. bitcoind is a fake JSON-RPC
server. Dummy credentials only; the output must be label, outcome and HTTP code.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
    _host_shims(bin_dir, tmp_path)
    node = FakeBitcoind(tuple(COOKIE.split(":")), {"getblockcount": lambda p: 900_000})
    cookie_file = tmp_path / "container.cookie"
    cookie_file.write_text(COOKIE)
    (tmp_path / ".cookie").write_text(COOKIE)
    (tmp_path / "bitcoin.conf").write_text(f"rpcport={node.port}\n")
    node_dir = tmp_path / "node"  # bitcoind datadir for the host consumers
    node_dir.mkdir()
    (node_dir / ".cookie").write_text(COOKIE)
    (node_dir / "bitcoin.conf").write_text(f"rpcport={node.port}\n")
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("BITCOIN_")},
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_UID": str(tmp_path / "uid"),
        "SHIM_UNITS": str(tmp_path / "units"),
        "SHIM_HOMES": str(tmp_path / "homes"),
        "SHIM_RUN": str(tmp_path / "systemd-run.args"),
    }

    def run(call: str, stdin: str = "", **extra) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f"{_function()}\n{call}"],
            input=stdin,
            capture_output=True,
            text=True,
            env={**env, **extra},
            timeout=60,
            check=False,
        )

    def unit(name: str, **props: str) -> None:
        """Define what `systemctl show -P <prop> <name>` prints."""
        (tmp_path / "units" / name).mkdir(parents=True)
        for prop, value in props.items():
            (tmp_path / "units" / name / prop).write_text(value + "\n")

    def home(user: str) -> Path:
        """HOME that systemd gives User=<user>; starts without a .bitcoin."""
        path = tmp_path / f"home-{user}"
        path.mkdir()
        (tmp_path / "homes").mkdir(exist_ok=True)
        (tmp_path / "homes" / user).write_text(str(path))
        return path

    def replay(code: str, **extra) -> subprocess.CompletedProcess:
        """Run consumer code in the exact transient-unit context of the last check."""
        args = (tmp_path / "systemd-run.args").read_text().splitlines()
        i = 0
        while args[i].startswith("--") or args[i] == "-p":
            i += 2 if args[i] == "-p" else 1
        options, command = args[:i], args[i:]
        launcher = command[: command.index("run")]
        return subprocess.run(
            [
                str(bin_dir / "systemd-run"),
                *options,
                *launcher,
                "run",
                "python",
                "-c",
                code,
            ],
            capture_output=True,
            text=True,
            env={**env, **extra},
            timeout=60,
            check=False,
        )

    run.node, run.url = node, f"http://127.0.0.1:{node.port}/"
    run.cookie_file, run.datadir, run.uid_file = cookie_file, tmp_path, tmp_path / "uid"
    run.node_dir, run.unit, run.home, run.replay = node_dir, unit, home, replay
    run.uv, run.unit_path = (
        tmp_path / "uvbin" / "uv",
        f"PATH={tmp_path / 'uvbin'}:/usr/bin:/bin",
    )
    run.run_args = tmp_path / "systemd-run.args"
    yield run
    node.stop()


def _host_shims(bin_dir: Path, tmp_path: Path) -> None:
    shims = {
        "sudo": 'exec "$@"\n',
        "systemctl": textwrap.dedent(
            """\
            [ "$1 $2" = "show -P" ] || exit 99
            f="$SHIM_UNITS/$4/$3"; [ -f "$f" ] && cat "$f"; exit 0
            """
        ),
        "systemd-run": textwrap.dedent(
            """\
            printf '%s\\n' "$@" > "$SHIM_RUN"
            env=(); wd=/
            while [ $# -gt 0 ]; do
              case "$1" in
                --quiet|--wait|--pipe|--collect) shift ;;
                -p) case "$2" in
                      User=*) env+=("HOME=$(cat "$SHIM_HOMES/${2#User=}")") ;;
                      WorkingDirectory=*) wd=${2#WorkingDirectory=} ;;
                      Environment=*) read -ra words <<< "${2#Environment=}"; env+=("${words[@]}") ;;
                      EnvironmentFile=*) f=${2#EnvironmentFile=}; f=${f#-}
                        [ -f "$f" ] && while IFS= read -r line; do env+=("$line"); done < "$f" ;;
                    esac; shift 2 ;;
                *) break ;;
              esac
            done
            cd "$wd" && exec env -i "${env[@]}" "$@"
            """
        ),
    }
    for name, body in shims.items():
        (bin_dir / name).write_text("#!/bin/bash\n" + body)
        (bin_dir / name).chmod(0o755)
    uv = tmp_path / "uvbin" / "uv"  # uv run python ... -> this test's interpreter
    uv.parent.mkdir()
    uv.write_text(
        f'#!/bin/bash\n[ "$1" = run ] && shift; [ "$1" = python ] && shift\n'
        f'exec "{sys.executable}" "$@"\n'
    )
    uv.chmod(0o755)


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


LIVE = "utxoracle-live.service"
SYNC = "utxoracle-api.service"
CONSUMER_CODE = {  # each consumer's production call, as the service makes it
    "live": "from live.backend.bitcoin_rpc import BitcoinRPC;"
    " BitcoinRPC().ask_node('getblockcount')",
    "sync": "from scripts.sync_utxo_lifecycle import BitcoinRPC;"
    " BitcoinRPC().getblockcount()",
    "daily": "from scripts import daily_analysis as d;"
    " d.rpc_client(d.load_config()).call('getblockcount')",
}


def _live_unit(ctx, **extra):
    ctx.unit(
        LIVE,
        User="utxoracle",
        WorkingDirectory=str(REPO),
        Environment=ctx.unit_path,
        ProtectHome="yes",
        **extra,
    )


def test_r5_m1_operator_datadir_does_not_certify_a_consumer_without_cookie(ctx):
    """R5-M1: cookie valid in the node datadir, the consumer's HOME has none and
    BITCOIN_DATADIR is set only where the check is launched. The old host check
    built its own client from that datadir and said 200; live cannot authenticate."""
    ctx.home("utxoracle")
    _live_unit(ctx)
    operator = {"BITCOIN_DATADIR": str(ctx.node_dir)}

    old_form = ctx(f'rpc_check "utxoracle-live" host "{ctx.node_dir}"', **operator)
    assert "OK" not in old_form.stdout, "a datadir argument certified nothing"

    check = ctx(f'rpc_check "utxoracle-live" host live {LIVE}', **operator)
    assert check.stdout == "utxoracle-live: FAIL HTTP 000\n"
    consumer = ctx.replay(CONSUMER_CODE["live"], **operator)
    assert consumer.returncode != 0, "the real live client fails in the same context"
    assert "DUMMY" not in check.stdout + check.stderr


@pytest.mark.parametrize(("consumer", "unit"), [("live", LIVE), ("sync", SYNC)])
def test_host_check_and_consumer_agree_in_the_unit_context(
    ctx, tmp_path, consumer, unit
):
    ctx.home("utxoracle")
    envfile = tmp_path / "service.env"
    envfile.write_text(f"BITCOIN_DATADIR={ctx.node_dir}\n")
    ctx.unit(
        unit,
        User="utxoracle",
        WorkingDirectory=str(REPO),
        Environment=ctx.unit_path,
        EnvironmentFiles=f"{envfile} (ignore_errors=yes)",
    )
    operator = {"BITCOIN_DATADIR": str(tmp_path / "nonexistent")}  # must not leak in

    ok = ctx(f'rpc_check "utxoracle-{consumer}" host {consumer} {unit}', **operator)
    assert ok.stdout == f"utxoracle-{consumer}: OK HTTP 200\n"
    assert ctx.replay(CONSUMER_CODE[consumer], **operator).returncode == 0

    (ctx.node_dir / ".cookie").write_text(OTHER)  # bitcoind restarted, stale cookie
    ctx.node.accepted = ("__cookie__", "DUMMYCOOKIE0003")
    bad = ctx(f'rpc_check "utxoracle-{consumer}" host {consumer} {unit}', **operator)
    assert bad.stdout == f"utxoracle-{consumer}: FAIL HTTP 401\n"
    assert ctx.replay(CONSUMER_CODE[consumer], **operator).returncode != 0
    assert "DUMMY" not in ok.stdout + ok.stderr + bad.stdout + bad.stderr


def test_host_check_reads_the_cookie_of_the_unit_users_home(ctx):
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    _live_unit(ctx)
    result = ctx(f'rpc_check "utxoracle-live" host live {LIVE}')
    assert result.stdout == "utxoracle-live: OK HTTP 200\n"


def test_host_check_carries_the_unit_context_and_no_connection_argument(ctx, tmp_path):
    ctx.home("utxoracle")
    envfile = tmp_path / "service.env"
    envfile.write_text(f"BITCOIN_DATADIR={ctx.node_dir}\n")
    _live_unit(
        ctx,
        Group="utxoracle",
        ProtectSystem="strict",
        PrivateTmp="yes",
        ReadWritePaths="/opt/UTXOracle/logs",
        EnvironmentFiles=f"{envfile} (ignore_errors=no)",
    )
    ctx(f'rpc_check "utxoracle-live" host live {LIVE}')
    args = ctx.run_args.read_text().splitlines()
    props = {args[i + 1] for i, a in enumerate(args) if a == "-p"}
    assert {
        "User=utxoracle",
        "Group=utxoracle",
        f"WorkingDirectory={REPO}",
        f"Environment={ctx.unit_path}",
        "ProtectHome=yes",
        "ProtectSystem=strict",
        "PrivateTmp=yes",
        "ReadWritePaths=/opt/UTXOracle/logs",
        f"EnvironmentFile={envfile}",
    } <= props
    assert args[-8:] == [
        *("/usr/bin/env", "uv", "run", "python", "-m", "scripts.utils.rpc_cookie"),
        *("utxoracle-live", "live"),
    ]
    assert not any(str(ctx.node_dir) in a for a in args), "no datadir from the check"


def test_unit_with_passenvironment_is_not_reproducible(ctx):
    _live_unit(ctx, PassEnvironment="BITCOIN_DATADIR")
    result = ctx(f'rpc_check "utxoracle-live" host live {LIVE}')
    assert result.stdout == "utxoracle-live: FAIL PassEnvironment non riproducibile\n"
    assert not ctx.run_args.exists(), "systemd-run must not start"


def test_cron_check_uses_the_crontab_user_and_directory(ctx):
    sam = ctx.home("sam")
    call = f'rpc_check "utxoracle-daily" cron daily sam "{REPO}" "{ctx.uv}"'
    operator = {"BITCOIN_DATADIR": str(ctx.node_dir)}
    assert ctx(call, **operator).stdout == "utxoracle-daily: FAIL HTTP 000\n"
    assert ctx.replay(CONSUMER_CODE["daily"], **operator).returncode != 0
    (sam / ".bitcoin").symlink_to(ctx.node_dir)
    assert ctx(call).stdout == "utxoracle-daily: OK HTTP 200\n"
    assert ctx.replay(CONSUMER_CODE["daily"]).returncode == 0


SAME_CODE = """
import inspect, asyncio
from unittest import mock
from scripts.utils import rpc_cookie
import live.backend.bitcoin_rpc as live_rpc
import live.backend.baseline_calculator as baseline
import scripts.sync_utxo_lifecycle as sync
import scripts.daily_analysis as daily
import api.routes.streams as streams

# The check calls the very objects the consumers' own code calls.
assert rpc_cookie.consumer_factory("live") is live_rpc.BitcoinRPC is baseline.BitcoinRPC
assert rpc_cookie.consumer_factory("sync") is sync.BitcoinRPC
assert rpc_cookie.consumer_factory("daily") is daily.rpc_client
assert not inspect.signature(sync.BitcoinRPC).parameters

calls = []
def spy(name):
    def factory(*args, **kwargs):
        calls.append((name, args, kwargs))
        raise RuntimeError("stop")
    return factory

for target, name in ((live_rpc, "BitcoinRPC"), (sync, "BitcoinRPC"), (daily, "rpc_client")):
    consumer = {live_rpc: "live", sync: "sync", daily: "daily"}[target]
    with mock.patch.object(target, name, spy("check:" + consumer)):
        assert rpc_cookie.main(["chk", consumer]) == 1
# Production construction sites, through the same objects.
with mock.patch.object(baseline, "BitcoinRPC", spy("live")):
    baseline.BaselineCalculator()
with mock.patch.object(sync, "BitcoinRPC", spy("sync")), mock.patch.object(
    streams, "_get_current_tip_with_bitcoin_cli", side_effect=OSError
):
    streams._TIP_CACHE.clear()
    try:
        asyncio.run(streams.get_current_tip())
    except RuntimeError:
        pass
with mock.patch.object(daily, "rpc_client", spy("daily")):
    for path in (lambda: daily._fetch_from_bitcoin_core(None),
                 lambda: daily.fetch_historical_transactions("2024-01-01", {})):
        try:
            path()
        except RuntimeError:
            pass
assert calls == [
    ("check:live", (), {}), ("check:sync", (), {}), ("check:daily", (), {}),
    ("live", (), {"datadir": None}), ("sync", (), {}),
    ("daily", ({"BITCOIN_DATADIR": None},), {"timeout": 120}), ("daily", ({},), {}),
], calls
print("same-code")
"""


def test_check_and_consumers_share_the_construction_code(tmp_path):
    """Not two parallel paths: the check's factory is the object each consumer's
    production code calls, and neither passes connection parameters."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("BITCOIN_")}
    result = subprocess.run(
        [sys.executable, "-c", SAME_CODE],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**env, "HOME": str(tmp_path)},
        timeout=120,
        check=False,
    )
    assert result.stdout.strip().endswith("same-code"), result.stderr[-2000:]
