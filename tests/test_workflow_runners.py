"""Fuori dal Dell: il repo e' pubblico, quindi solo il gate live opt-in resta su un runner self-hosted."""
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _runs_on(name: str) -> dict[str, object]:
    jobs = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]
    return {job: spec.get("runs-on") for job, spec in jobs.items() if "runs-on" in spec}


def test_notify_pepers_runs_on_github_hosted():
    assert _runs_on("notify-pepers-integration.yml") == {"notify": "ubuntu-latest"}


def test_only_the_opt_in_streams_health_gate_needs_the_dell():
    # Il gate raggiunge QuestDB su :8812 (rete privata): non puo' girare su un runner pubblico.
    assert _runs_on("ci.yml") == {
        "streams-health-contract": ["self-hosted", "Linux", "X64", "dell-runner"],
    }


def _notify_steps() -> list[dict]:
    jobs = yaml.safe_load((WORKFLOWS / "notify-pepers-integration.yml").read_text(encoding="utf-8"))["jobs"]
    return jobs["notify"]["steps"]


def test_dispatch_is_fail_closed_and_does_not_read_a_host_env_file():
    steps = _notify_steps()
    text = (WORKFLOWS / "notify-pepers-integration.yml").read_text(encoding="utf-8")
    assert "dotenvx" not in text and ".env" not in text
    dispatch = next(s for s in steps if s.get("id") == "progressive_dispatch")
    assert "if" not in dispatch and "continue-on-error" not in dispatch
    assert steps.index(next(s for s in steps if "PD_TOKEN" in s.get("env", {}))) < steps.index(dispatch)


def test_guard_step_fails_loudly_without_the_secret_and_passes_with_it():
    import subprocess

    guard = next(s for s in _notify_steps() if "PD_TOKEN" in s.get("env", {}))
    missing = subprocess.run(["bash", "-c", guard["run"]], env={"PD_TOKEN": ""}, capture_output=True, text=True)
    assert missing.returncode == 1
    assert "::error title=Dispatch token missing::" in missing.stdout
    present = subprocess.run(["bash", "-c", guard["run"]], env={"PD_TOKEN": "x"}, capture_output=True, text=True)
    assert present.returncode == 0
