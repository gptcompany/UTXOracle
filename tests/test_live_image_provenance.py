"""CI-only production image provenance contract, no services started."""

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_live_services_accept_one_digest_without_code_overlays():
    compose = yaml.safe_load((ROOT / "docker-compose.live.yml").read_text())
    for name in (
        "utxoracle-live-api",
        "utxoracle-live-worker",
        "utxoracle-data-updater",
    ):
        service = compose["services"][name]
        assert service["image"] == "${UTXORACLE_LIVE_IMAGE:-utxoracle-live:local}"
        assert not any(
            ":/app/scripts" in v or ":/app/api" in v for v in service.get("volumes", [])
        )
    assert "org.opencontainers.image.revision" in (ROOT / "Dockerfile.live").read_text()


PUBLISH = ROOT / ".github/workflows/live-image-publish.yml"
DEPLOY_RUNNER = ["self-hosted", "Linux", "X64", "deploy"]


def test_publish_has_its_own_workflow_triggered_only_by_a_push_to_main():
    workflow = yaml.safe_load(PUBLISH.read_text())
    assert workflow["on"] == {"push": {"branches": ["main"]}}
    assert set(workflow["jobs"]) == {"publish"}
    raw = PUBLISH.read_text()
    for trigger in (
        "pull_request",
        "pull_request_target",
        "workflow_run",
        "workflow_dispatch",
    ):
        assert trigger not in raw


def test_publish_runs_on_the_dell_docker_runner_with_minimal_permissions():
    workflow = yaml.safe_load(PUBLISH.read_text())
    job = workflow["jobs"]["publish"]
    assert job["runs-on"] == DEPLOY_RUNNER
    assert job["if"] == "github.repository == 'gptcompany/UTXOracle'"
    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    push = next(step for step in job["steps"] if step.get("id") == "build")
    assert push["with"]["file"] == "Dockerfile.live"
    assert push["with"]["push"] is True


def test_the_pull_request_workflow_only_checks_the_contract_and_never_publishes():
    workflow = yaml.safe_load((ROOT / ".github/workflows/live-image.yml").read_text())
    assert set(workflow["jobs"]) == {"contract"}
    assert workflow["permissions"] == {"contents": "read"}
    assert "packages" not in (ROOT / ".github/workflows/live-image.yml").read_text()
