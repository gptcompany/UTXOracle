"""Regola operatore del 13/11/2026: nessun job dipende dai runner GitHub hosted.

Repo pubblico: i job raggiungibili da una PR usano la guardia che lascia le PR da fork su
ubuntu-latest, cosi' il codice da fork non arriva mai ai runner self-hosted.
"""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
FORK_PR = (
    "(github.event_name == 'pull_request' || github.event_name == 'pull_request_review')"
    " && github.event.pull_request.head.repo.full_name != github.repository && 'ubuntu-latest'"
)
PR_EVENTS = {"pull_request", "pull_request_target", "pull_request_review"}
TRUSTED = "${{ vars.CI_RUNS_ON || 'sg-ci' }}"
GUARDED = {
    "${{ " + FORK_PR + " || vars.CI_RUNS_ON || 'sg-ci' }}",
    # Docker jobs (services) on the trusted Docker-capable runner.
    "${{ " + FORK_PR + " || 'sg-priv' }}",
}


def _runs_on(name: str) -> dict[str, object]:
    jobs = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]
    return {job: spec.get("runs-on") for job, spec in jobs.items() if "runs-on" in spec}


def _triggers(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    on = data.get("on", data.get(True))  # PyYAML reads a bare `on` key as True.
    if isinstance(on, dict):
        return on
    return {key: None for key in ([on] if isinstance(on, str) else on)}


def test_notify_pepers_runs_on_self_hosted():
    assert _runs_on("notify-pepers-integration.yml") == {"notify": TRUSTED}


def test_every_job_uses_a_self_hosted_selector():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        pr = bool(PR_EVENTS & set(_triggers(path.name)))
        allowed = GUARDED if pr else GUARDED | {TRUSTED}
        for job, runner in _runs_on(path.name).items():
            assert runner in allowed, f"{path.name}:{job} usa {runner}"


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
