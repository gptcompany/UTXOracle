"""All jobs use the approved self-hosted pools; hosted minutes are unavailable."""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _runs_on(name: str) -> dict[str, object]:
    jobs = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]
    return {job: spec.get("runs-on") for job, spec in jobs.items() if "runs-on" in spec}


def test_every_job_runs_on_the_self_hosted_pool():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job, runner in _runs_on(path.name).items():
            approved = (
                "${{ vars.CI_RUNS_ON || 'sg-ci' }}",
                ["self-hosted", "Linux", "X64", "gbg-ci"],
            )
            if path.name == "live-image-publish.yml":
                approved += (["self-hosted", "Linux", "X64", "deploy"],)
            assert runner in approved, (
                f"{path.name}:{job} uses non-approved runner {runner}"
            )


def test_no_job_selects_the_private_sg_priv_pool():
    """The repository is public: the ci-priv runner group is closed to it, so a job that
    selects sg-priv waits in the queue forever (B5, 14/11)."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job, runner in _runs_on(path.name).items():
            assert "sg-priv" not in str(runner), f"{path.name}:{job} selects sg-priv"


def test_the_dell_deploy_runner_is_only_for_the_main_push_publish_workflow():
    """Docker image publication needs the Dell daemon; nothing else may select that runner."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job, runner in _runs_on(path.name).items():
            if path.name != "live-image-publish.yml":
                assert "deploy" not in str(runner), f"{path.name}:{job} selects deploy"


def test_ci_is_local_and_rejects_fork_code_on_self_hosted_runners():
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]
    assert set(jobs) == {"checks", "security"}
    for job in jobs.values():
        assert "uses" not in job
        expected_guard = (
            "github.event_name != 'pull_request' || "
            "github.event.pull_request.head.repo.full_name == github.repository"
        )
        if job is jobs["checks"]:
            expected_guard = f"github.event_name != 'schedule' && ({expected_guard})"
        assert job["if"] == expected_guard
        checkout = job["steps"][0]
        assert checkout["with"]["persist-credentials"] is False


def test_ci_preserves_blocking_gates():
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]
    commands = {
        entry["command"] for entry in jobs["checks"]["strategy"]["matrix"]["include"]
    }
    assert "uv run ruff check ." in commands
    assert "uv run ruff format --check ." in commands
    assert (
        "uv run pytest tests/ --ignore=tests/e2e --cov=. --cov-fail-under=68 --tb=short"
        in commands
    )
    security = jobs["security"]
    assert security["steps"][0]["with"]["fetch-depth"] == 0
    bandit, gitleaks = security["steps"][-2:]
    assert bandit["run"] == "uv tool run bandit -r . -lll -ii -q"
    assert gitleaks["if"] == "${{ !cancelled() }}"
    assert '"gitleaks_8.18.4_linux_x64.tar.gz"' in gitleaks["run"]
    assert '"detect", "--source", ".", "--redact"' in gitleaks["run"]
    assert "raise SystemExit(result.returncode)" in gitleaks["run"]
    assert '"--log-opts", f"{base}..{head}"' in gitleaks["run"]
    assert 'if os.environ["GITHUB_EVENT_NAME"] == "pull_request":' in gitleaks["run"]
    assert gitleaks["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert gitleaks["env"]["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    workflow = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    events = workflow.get("on", workflow.get(True))
    assert events["schedule"] == [{"cron": "0 2 * * *"}]
    assert "main" in events["push"]["branches"]
    assert "github.event_name != 'schedule'" in jobs["checks"]["if"]
    assert security["timeout-minutes"] == 10
    for job in jobs.values():
        assert not job.get("continue-on-error", False)
        for step in job["steps"]:
            assert not step.get("continue-on-error", False)


def _notify_steps() -> list[dict]:
    jobs = yaml.safe_load(
        (WORKFLOWS / "notify-pepers-integration.yml").read_text(encoding="utf-8")
    )["jobs"]
    return jobs["notify"]["steps"]


def test_dispatch_is_fail_closed_and_does_not_read_a_host_env_file():
    steps = _notify_steps()
    text = (WORKFLOWS / "notify-pepers-integration.yml").read_text(encoding="utf-8")
    assert "dotenvx" not in text and ".env" not in text
    dispatch = next(s for s in steps if s.get("id") == "progressive_dispatch")
    assert "if" not in dispatch and "continue-on-error" not in dispatch
    assert steps.index(
        next(s for s in steps if "PD_TOKEN" in s.get("env", {}))
    ) < steps.index(dispatch)


def test_guard_step_fails_loudly_without_the_secret_and_passes_with_it():
    import subprocess

    guard = next(s for s in _notify_steps() if "PD_TOKEN" in s.get("env", {}))
    missing = subprocess.run(
        ["bash", "-c", guard["run"]],
        env={"PD_TOKEN": ""},
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 1
    assert "::error title=Dispatch token missing::" in missing.stdout
    present = subprocess.run(
        ["bash", "-c", guard["run"]],
        env={"PD_TOKEN": "x"},
        capture_output=True,
        text=True,
    )
    assert present.returncode == 0
