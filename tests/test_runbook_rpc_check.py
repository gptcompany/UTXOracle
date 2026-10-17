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

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests.fake_bitcoind import FakeBitcoind, secrets_stub_path

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
COOKIE = "__cookie__:DUMMYCOOKIE0001"
OTHER = "__cookie__:DUMMYCOOKIE0002"
pytestmark = pytest.mark.usefixtures("hermetic_rpc")


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
        "TMPDIR": str(tmp_path / "tmp"),
    }
    (tmp_path / "tmp").mkdir()

    def run(call: str, stdin: str = "", **extra) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f"{_function()}\n{call}"],
            input=stdin,
            capture_output=True,
            text=True,
            env={**env, **extra},
            timeout=90,
            check=False,
        )

    def unit(name, exec_start, service=None, environment=(), env_files=(), **bus):
        """A systemd unit as the shims show it: fragment file, `systemctl show -P`
        values and the structured busctl properties."""
        service = {
            "User": "utxoracle",
            "WorkingDirectory": str(REPO),
            **(service or {}),
        }
        d = tmp_path / "units" / name
        (d / "bus").mkdir(parents=True)
        (d / "show").mkdir()
        fragment = d / name
        lines = ["[Unit]", "Description=test", "", "[Service]"]
        lines += [f"{key}={value}" for key, value in service.items()]
        lines += [f'Environment="{assignment}"' for assignment in environment]
        lines += [f"EnvironmentFile={'-' * ig}{p}" for p, ig in env_files]
        lines += ["ExecStart=" + " ".join(exec_start), bus.pop("extra", "")]
        lines += ["", "[Install]", "WantedBy=multi-user.target", ""]
        fragment.write_text("\n".join(lines))
        shown = {
            **service,
            "Environment": " ".join(environment),
            "EnvironmentFiles": "\n".join(
                f"{p} (ignore_errors={'yes' if ig else 'no'})" for p, ig in env_files
            ),
        }
        for key, value in shown.items():
            if value:
                (d / "show" / key).write_text(value + "\n")
        props = {
            "FragmentPath": ("s", str(fragment)),
            "DropInPaths": ("as", []),
            "ExecStartEx": (
                "a(sasasttttuii)",
                [[exec_start[0], list(exec_start), [], 0, 0, 0, 0, 0, 0, 0]],
            ),
            "Environment": ("as", list(environment)),
            "EnvironmentFiles": ("a(sb)", [[str(p), bool(ig)] for p, ig in env_files]),
            **bus,
        }
        for key, (kind, data) in props.items():
            (d / "bus" / f"{key}.json").write_text(
                json.dumps({"type": kind, "data": data})
            )

    def home(user: str) -> Path:
        """HOME that systemd gives User=<user>; starts without a .bitcoin."""
        path = tmp_path / f"home-{user}"
        path.mkdir()
        (tmp_path / "homes").mkdir(exist_ok=True)
        (tmp_path / "homes" / user).write_text(str(path))
        return path

    def replay_rc() -> int:
        """Exit code of the consumer's own code, run by the systemd-run shim in the
        very context (identity, cwd, environment, launcher) the check got."""
        return int((tmp_path / "systemd-run.args.replay").read_text())

    run.node, run.url = node, f"http://127.0.0.1:{node.port}/"
    run.cookie_file, run.datadir, run.uid_file = cookie_file, tmp_path, tmp_path / "uid"
    run.node_dir, run.unit, run.home, run.replay_rc = node_dir, unit, home, replay_rc
    run.uv_dir = tmp_path / "uvbin"
    run.run_args = tmp_path / "systemd-run.args"
    run.tmp = tmp_path / "tmp"
    yield run
    node.stop()


def _host_shims(bin_dir: Path, tmp_path: Path) -> None:
    shims = {
        "sudo": 'exec "$@"\n',
        "systemctl": textwrap.dedent(
            """\
            [ "$1 $2" = "show -P" ] || exit 99
            f="$SHIM_UNITS/$4/show/$3"; [ -f "$f" ] && cat "$f"; exit 0
            """
        ),
        "busctl": textwrap.dedent(
            """\
            [ "$1" = --json=short ] || exit 99
            shift
            case "$1" in
              call)
                [ "$5" = GetUnit ] || exit 99
                [ -d "$SHIM_UNITS/$7" ] || { echo "Unit $7 not loaded." >&2; exit 1; }
                printf '{"type":"o","data":["/unit/%s"]}\\n' "$7" ;;
              get-property) cat "$SHIM_UNITS/${3#/unit/}/bus/$5.json" ;;
              *) exit 99 ;;
            esac
            """
        ),
        "systemd-run": textwrap.dedent(
            """\
            printf '%s\\n' "$@" > "$SHIM_RUN"
            : > "$SHIM_RUN.modes"
            env=(); wd=/
            while [ $# -gt 0 ]; do
              case "$1" in
                --) shift; break ;;
                --*) shift ;;
                -p) case "$2" in
                      User=*) env+=("HOME=$(cat "$SHIM_HOMES/${2#User=}")") ;;
                      WorkingDirectory=*) wd=${2#WorkingDirectory=} ;;
                      Environment=*) read -ra words <<< "${2#Environment=}"
                        env+=("${words[@]}") ;;
                      EnvironmentFile=*) f=${2#EnvironmentFile=}; f=${f#-}
                        stat -c '%a' "$f" >> "$SHIM_RUN.modes" 2>/dev/null
                        [ -f "$f" ] && while IFS= read -r line; do env+=("$line"); done < "$f" ;;
                    esac; shift 2 ;;
                *) break ;;
              esac
            done
            # The consumer's production call, in the same context, for the tests.
            (cd "$wd" && env -i "${env[@]}" "${@:1:$(($# - 4))}" -c "$SHIM_REPLAY" \\
              >/dev/null 2>&1); echo $? > "$SHIM_RUN.replay"
            echo "chatter from the transient unit" >&2
            cd "$wd" && exec env -i "${env[@]}" "$@"
            """
        ),
    }
    for name, body in shims.items():
        (bin_dir / name).write_text("#!/bin/bash\n" + body)
        (bin_dir / name).chmod(0o755)
    stub = secrets_stub_path(tmp_path / "secrets-stub")  # never the real loader
    uv_body = textwrap.dedent(
        f"""\
        #!/bin/bash
        # uv run [options] python ... -> this test's interpreter
        [ "$1" = run ] && shift
        while [ "${{1#-}}" != "$1" ]; do
          case "$1" in --project|--directory|--python) shift 2 ;; *) shift ;; esac
        done
        [ "${{1#python}}" != "$1" ] && shift
        PYTHONPATH="{stub}" exec "{sys.executable}" "$@"
        """
    )
    (tmp_path / "uvbin").mkdir()
    for uv in (bin_dir / "uv", tmp_path / "uvbin" / "uv"):
        uv.write_text(uv_body)
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
UVICORN = [
    "/usr/bin/env",
    "uv",
    "run",
    "uvicorn",
    "live.backend.api:app",
    "--port",
    "1",
]


def _path(ctx) -> str:
    return f"PATH={ctx.uv_dir}:/usr/bin:/bin"


def _live_unit(ctx, exec_start=UVICORN, service=None, environment=None, **kw):
    environment = [_path(ctx)] if environment is None else environment
    ctx.unit(
        LIVE, exec_start, {"ProtectHome": "yes", **(service or {})}, environment, **kw
    )


def _check(ctx, consumer="live", unit=LIVE, **env):
    return ctx(
        f'rpc_check "utxoracle-{consumer}" host {consumer} {unit}',
        SHIM_REPLAY=CONSUMER_CODE[consumer],
        **env,
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

    check = _check(ctx, **operator)
    assert check.stdout == "utxoracle-live: FAIL HTTP 000\n"
    assert ctx.replay_rc() != 0, "the real live client fails in the same context"


@pytest.mark.parametrize(("consumer", "unit"), [("live", LIVE), ("sync", SYNC)])
def test_host_check_and_consumer_agree_in_the_unit_context(
    ctx, tmp_path, consumer, unit
):
    ctx.home("utxoracle")
    envfile = tmp_path / "service.env"
    envfile.write_text(f"BITCOIN_DATADIR={ctx.node_dir}\n")
    ctx.unit(unit, UVICORN, environment=[_path(ctx)], env_files=[(envfile, True)])
    operator = {"BITCOIN_DATADIR": str(tmp_path / "nonexistent")}  # must not leak in

    ok = _check(ctx, consumer, unit, **operator)
    assert ok.stdout == f"utxoracle-{consumer}: OK HTTP 200\n"
    assert ctx.replay_rc() == 0

    (ctx.node_dir / ".cookie").write_text(OTHER)  # bitcoind restarted, stale cookie
    ctx.node.accepted = ("__cookie__", "DUMMYCOOKIE0003")
    bad = _check(ctx, consumer, unit, **operator)
    assert bad.stdout == f"utxoracle-{consumer}: FAIL HTTP 401\n"
    assert ctx.replay_rc() != 0


def test_host_check_reads_the_cookie_of_the_unit_users_home(ctx):
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    _live_unit(ctx)
    assert _check(ctx).stdout == "utxoracle-live: OK HTTP 200\n"
    assert ctx.replay_rc() == 0


def test_host_check_runs_the_unit_launcher_in_the_unit_context(ctx, tmp_path):
    ctx.home("utxoracle")
    envfile = tmp_path / "service.env"
    envfile.write_text(f"BITCOIN_DATADIR={ctx.node_dir}\n")
    _live_unit(
        ctx,
        service={"Group": "utxoracle", "ProtectSystem": "strict", "PrivateTmp": "yes"},
        env_files=[(envfile, False)],
    )
    assert _check(ctx).stdout == "utxoracle-live: OK HTTP 200\n"
    args = ctx.run_args.read_text().splitlines()
    props = [args[i + 1] for i, a in enumerate(args) if a == "-p"]
    assert {
        "User=utxoracle",
        "Group=utxoracle",
        f"WorkingDirectory={REPO}",
        "ProtectHome=yes",
        "ProtectSystem=strict",
        "PrivateTmp=yes",
    } <= set(props)
    env_files = [
        p.removeprefix("EnvironmentFile=") for p in props if "Environment" in p
    ]
    assert env_files[1:] == [str(envfile)], "the unit's files after Environment="
    assert args[args.index("--") + 1 :] == [
        *("/usr/bin/env", "uv", "run", "--no-sync", "python"),
        *("-m", "scripts.utils.rpc_cookie", "utxoracle-live", "live"),
    ], "same launcher as ExecStart, only the module replaced"
    assert not any(str(ctx.node_dir) in a for a in args), "no datadir from the check"


def test_environment_values_never_reach_an_argv(ctx):
    """R5-M1-b: Environment= values travel in a 0600 file removed after the check."""
    ctx.home("utxoracle")
    _live_unit(
        ctx,
        environment=[
            _path(ctx),
            f"BITCOIN_DATADIR={ctx.node_dir}",
            "BITCOIN_RPC_PASSWORD=DUMMYENVSECRET",
        ],
    )
    result = _check(ctx)
    assert result.stdout == "utxoracle-live: OK HTTP 200\n", "the values do arrive"
    assert "DUMMYENVSECRET" not in ctx.run_args.read_text()
    assert ctx.run_args.with_suffix(".args.modes").read_text().split()[0] == "600"
    assert list(ctx.tmp.iterdir()) == [], "temporary environment file removed"


def test_check_output_is_one_line_without_consumer_or_unit_logs(ctx):
    """R5-M1-c: sync logs at import and systemd-run chatters on stderr."""
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    ctx.unit(SYNC, UVICORN, environment=[_path(ctx), "LOG_LEVEL=DEBUG"])
    result = _check(ctx, "sync", SYNC)
    assert (result.stdout, result.stderr) == ("utxoracle-sync: OK HTTP 200\n", "")


@pytest.mark.parametrize(
    ("exec_start", "extra", "reason"),
    [
        (
            ["/usr/bin/env", "BITCOIN_DATADIR=/x", "uv", "run", "uvicorn", "a:b"],
            "",
            "env",
        ),
        (["/bin/sh", "-c", "exec uv run uvicorn a:b"], "", "non riconosciuto"),
        (
            ["/usr/bin/env", "uv", "run", "--env-file", "/x", "uvicorn", "a:b"],
            "",
            "uv run",
        ),
        (["/usr/bin/env", "uv", "run", "uvicorn", "a:b", "--x=$HOME"], "", "variabili"),
        (UVICORN, "ExecStartPre=/bin/true", "ExecStartPre"),
        (UVICORN, "PassEnvironment=BITCOIN_DATADIR", "PassEnvironment"),
        (UVICORN, "BindPaths=/a:/b", "BindPaths"),
        (UVICORN, "DynamicUser=yes", "DynamicUser"),
        (UVICORN, "  Environment=BITCOIN_DATADIR=/x", "riga indentata"),
    ],
    ids=[
        "env-assignment",
        "shell",
        "uv-env-file",
        "dollar",
        "execstartpre",
        "passenvironment",
        "bindpaths",
        "dynamicuser",
        "hidden-indented-key",
    ],
)
def test_unreproducible_unit_fails_closed_without_running(
    ctx, exec_start, extra, reason
):
    """R5-M1-a: a context the check cannot copy exactly is a FAIL, never an OK."""
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)  # would say 200
    _live_unit(ctx, exec_start, extra=extra)
    result = ctx(f'rpc_check "utxoracle-live" host live {LIVE}')
    assert result.stdout.startswith("utxoracle-live: FAIL contesto non riproducibile")
    assert reason in result.stdout and result.returncode != 0
    assert not ctx.run_args.exists(), "systemd-run must not start"


def test_execstart_wrapper_environment_is_not_a_false_green(ctx):
    """R5-M1-a scenario: the unit's ExecStart sets BITCOIN_DATADIR through env(1);
    the consumer fails there, while HOME/.bitcoin would authenticate the check."""
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    wrapper = ["/usr/bin/env", "BITCOIN_DATADIR=/nonexistent", "uv", "run", "uvicorn"]
    _live_unit(ctx, [*wrapper, "live.backend.api:app"])
    result = ctx(f'rpc_check "utxoracle-live" host live {LIVE}')
    assert "OK" not in result.stdout


def test_multiple_or_prefixed_execstart_fails_closed(ctx):
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    entry = [UVICORN[0], UVICORN, [], 0, 0, 0, 0, 0, 0, 0]
    _live_unit(ctx, ExecStartEx=("a(sasasttttuii)", [entry, entry]))
    assert "non riproducibile" in ctx(f'rpc_check "l" host live {LIVE}').stdout
    _live_unit_dir = ctx.run_args.parent / "units" / LIVE / "bus" / "ExecStartEx.json"
    prefixed = [UVICORN[0], UVICORN, ["privileged"], 0, 0, 0, 0, 0, 0, 0]
    _live_unit_dir.write_text(json.dumps({"type": "x", "data": [prefixed]}))
    assert "non riproducibile" in ctx(f'rpc_check "l" host live {LIVE}').stdout


def test_direct_venv_python_launcher_is_kept(ctx):
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    python = str(ctx.uv_dir / "python")
    stub = ctx.run_args.parent / "secrets-stub"
    (ctx.uv_dir / "python").write_text(
        f'#!/bin/bash\nPYTHONPATH="{stub}" exec "{sys.executable}" "$@"\n'
    )
    (ctx.uv_dir / "python").chmod(0o755)
    _live_unit(ctx, [python, "-m", "live.backend.api"])
    assert _check(ctx).stdout == "utxoracle-live: OK HTTP 200\n"
    args = ctx.run_args.read_text().splitlines()
    assert args[args.index("--") + 1 :][:3] == [
        python,
        "-m",
        "scripts.utils.rpc_cookie",
    ]


def test_unknown_unit_or_consumer_fails(ctx):
    assert "non riproducibile" in ctx('rpc_check "x" host live nosuch.service').stdout
    assert "consumatore sconosciuto" in ctx('rpc_check "x" host /var/lib/b u').stdout


def test_consumer_processes_never_load_the_real_secrets(ctx):
    (ctx.home("utxoracle") / ".bitcoin").symlink_to(ctx.node_dir)
    _live_unit(ctx)
    probe = (
        "import sys, scripts.sync_utxo_lifecycle, scripts.daily_analysis;"
        " sys.exit(0 if sys.modules['secrets_loader'].__file__.endswith("
        "'secrets-stub/sitecustomize.py') else 3)"
    )
    ctx(f'rpc_check "utxoracle-live" host live {LIVE}', SHIM_REPLAY=probe)
    assert ctx.replay_rc() == 0


def test_cron_check_uses_the_crontab_user_directory_and_line_variables(ctx):
    ctx.home("sam")
    call = f'rpc_check "utxoracle-daily" cron daily sam "{REPO}" "{ctx.uv_dir / "uv"}"'
    replay = {"SHIM_REPLAY": CONSUMER_CODE["daily"]}
    operator = {"BITCOIN_DATADIR": str(ctx.node_dir)}  # the operator's, not cron's
    assert ctx(call, **operator, **replay).stdout == "utxoracle-daily: FAIL HTTP 000\n"
    assert ctx.replay_rc() != 0
    cron_env = {"CRON_ENV": f"BITCOIN_DATADIR={ctx.node_dir} X=DUMMYCRONVALUE"}
    assert ctx(call, **cron_env, **replay).stdout == "utxoracle-daily: OK HTTP 200\n"
    assert ctx.replay_rc() == 0
    assert "DUMMYCRONVALUE" not in ctx.run_args.read_text()


SAME_CODE = """
import inspect, asyncio, sys
from unittest import mock
assert sys.modules["secrets_loader"].__file__.startswith(sys.argv[1]), "real loader"
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
    stub = secrets_stub_path(tmp_path / "secrets-stub")
    result = subprocess.run(
        [sys.executable, "-c", SAME_CODE, str(stub)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**env, "HOME": str(tmp_path), "PYTHONPATH": str(stub)},
        timeout=120,
        check=False,
    )
    assert result.stdout.strip().endswith("same-code"), result.stderr[-2000:]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["/v/bin/python3", "-m", "m", "--x"], ["/v/bin/python3"]),
        (["/u/uv", "run", "--project", "/p", "python", "-m", "m"],
         ["/u/uv", "run", "--no-sync", "--project", "/p", "python"]),
        (["/u/uv", "run", "--no-sync", "uvicorn", "a:b"], ["/u/uv", "run", "--no-sync", "python"]),
        (["/v/bin/uvicorn", "a:b"], ["/v/bin/python"]),
        (["/usr/bin/env", "uv", "run", "python3", "-m", "m"],
         ["/usr/bin/env", "uv", "run", "--no-sync", "python3"]),
    ],
)  # fmt: skip
def test_launcher_keeps_the_execstart_interpreter(argv, expected):
    from scripts.utils.unit_context import launcher

    assert launcher(argv) == expected


@pytest.mark.parametrize(
    "argv",
    [
        ["/v/bin/python", "-X", "utf8", "-m", "m"],
        ["/usr/bin/env", "-i", "uv", "run", "python", "-m", "m"],
        ["/u/uv", "run", "python", "script.py"],
        ["/u/uv", "sync"],
        ["/usr/local/bin/wrapper", "python", "-m", "m"],
    ],
)
def test_launcher_rejects_anything_else(argv):
    from scripts.utils.unit_context import NotReproducible, launcher

    with pytest.raises(NotReproducible):
        launcher(argv)


@pytest.mark.parametrize(
    "assignment",
    [
        'A="quoted"',
        "A=back\\slash",
        "A=$OTHER",
        "A= padded",
        "1A=x",
        "A-B=x",
        "noequals",
    ],
)
def test_environment_that_a_file_would_alter_is_rejected(assignment):
    from scripts.utils.unit_context import NotReproducible, env_lines

    with pytest.raises(NotReproducible) as exc:
        env_lines([assignment], "Environment")
    assert "quoted" not in str(exc.value) and "OTHER" not in str(exc.value)
