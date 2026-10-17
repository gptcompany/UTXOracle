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
