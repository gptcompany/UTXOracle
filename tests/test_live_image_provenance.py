"""CI-only production image provenance contract, no services started."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_live_services_accept_one_digest_without_code_overlays():
    compose = yaml.safe_load((ROOT / "docker-compose.live.yml").read_text())
    for name in ("utxoracle-live-api", "utxoracle-live-worker", "utxoracle-data-updater"):
        service = compose["services"][name]
        assert service["image"] == "${UTXORACLE_LIVE_IMAGE:-utxoracle-live:local}"
        assert not any(":/app/scripts" in v or ":/app/api" in v for v in service.get("volumes", []))
    assert "org.opencontainers.image.revision" in (ROOT / "Dockerfile.live").read_text()


def test_live_image_publish_is_self_hosted_and_has_no_deploy():
    workflow = yaml.safe_load((ROOT / ".github/workflows/live-image.yml").read_text())
    build = workflow["jobs"]["publish"]
    assert build["runs-on"] == ["self-hosted", "sg-priv"]
    assert "refs/heads/main" in build["if"]
    assert set(workflow["jobs"]) == {"contract", "publish"}
    push = next(step for step in build["steps"] if step.get("id") == "build")
    assert push["with"]["file"] == "Dockerfile.live"
    assert push["with"]["push"] is True
