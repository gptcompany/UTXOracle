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
            assert runner in {
                "${{ vars.CI_RUNS_ON || 'sg-ci' }}",
                "${{ vars.CI_RUNS_ON || 'sg-priv' }}",
            }, f"{path.name}:{job} uses non-approved runner {runner}"


def test_ci_pins_the_shared_workflows_with_self_hosted_scheduling():
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]
    for job in ("security", "lint", "test"):
        assert jobs[job]["uses"].endswith("@6ff270e89908aa2b6dd0dccc45db8ce55630e907")


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
